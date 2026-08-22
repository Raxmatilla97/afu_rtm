import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select

from afu_shared.db import session_scope
from afu_shared.enums import HEMIS_ACTIVE_EMPLOYEE_STATUS_CODE, HemisSyncStatus
from afu_shared.models import Department, Employee, HemisSyncRun
from afu_shared.settings import settings
from app.hemis_client import HemisClient

logger = logging.getLogger(__name__)


def _image_extension(url: str) -> str:
    suffix = Path(url.split("?")[0]).suffix
    return suffix if suffix else ".jpg"


async def _sync_departments(session, dept_items: list[dict[str, Any]]) -> tuple[dict[int, int], int, int, set[int]]:
    """Returns (hemis_id -> local_id map, created_count, updated_count, active_hemis_ids_seen)."""
    existing = {d.hemis_id: d for d in (await session.execute(select(Department))).scalars()}

    created = 0
    updated = 0
    hemis_id_to_local: dict[int, int] = {}
    active_seen: set[int] = set()
    all_seen: set[int] = set()

    for item in dept_items:
        hemis_id = item["id"]
        is_active = bool(item.get("active"))
        all_seen.add(hemis_id)

        row = existing.get(hemis_id)
        if is_active:
            active_seen.add(hemis_id)
            if row is None:
                row = Department(
                    hemis_id=hemis_id,
                    name=item["name"],
                    code=item.get("code"),
                    is_active=True,
                )
                session.add(row)
                await session.flush()
                existing[hemis_id] = row
                created += 1
            else:
                row.name = item["name"]
                row.code = item.get("code")
                row.is_active = True
                updated += 1
        elif row is not None and row.is_active:
            row.is_active = False
            updated += 1

    # Departments entirely absent from the response (deleted in HEMIS) get soft-deactivated too.
    for hemis_id, row in existing.items():
        if hemis_id not in all_seen and row.is_active:
            row.is_active = False
            updated += 1

    await session.flush()
    for hemis_id, row in existing.items():
        hemis_id_to_local[hemis_id] = row.id

    # Pass 2: resolve parents now that every department has a local id.
    for item in dept_items:
        row = existing.get(item["id"])
        if row is None:
            continue
        parent_hemis_id = item.get("parent")
        row.parent_department_id = hemis_id_to_local.get(parent_hemis_id) if parent_hemis_id else None

    return hemis_id_to_local, created, updated, active_seen


IMAGE_DOWNLOAD_CONCURRENCY = 15
IMAGE_DOWNLOAD_TIMEOUT = 15.0


async def _download_employee_image(
    client: httpx.AsyncClient, semaphore: asyncio.Semaphore, employee_id_number: str, image_url: str
) -> tuple[str, str | None]:
    dest_dir = Path(settings.storage_root) / "employees"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"{employee_id_number}{_image_extension(image_url)}"

    async with semaphore:
        try:
            resp = await client.get(image_url)
            resp.raise_for_status()
            dest_path.write_bytes(resp.content)
        except Exception:
            logger.warning("Failed to download image for %s from %s", employee_id_number, image_url)
            return employee_id_number, None

    return employee_id_number, f"employees/{dest_path.name}"


async def _download_pending_images(pending: dict[str, str]) -> dict[str, str]:
    """pending: employee_id_number -> image_url. Returns employee_id_number -> local_path for successes."""
    if not pending:
        return {}

    semaphore = asyncio.Semaphore(IMAGE_DOWNLOAD_CONCURRENCY)
    limits = httpx.Limits(max_connections=IMAGE_DOWNLOAD_CONCURRENCY, max_keepalive_connections=IMAGE_DOWNLOAD_CONCURRENCY)
    results: dict[str, str] = {}

    async with httpx.AsyncClient(timeout=IMAGE_DOWNLOAD_TIMEOUT, follow_redirects=True, limits=limits) as client:
        tasks = [
            _download_employee_image(client, semaphore, employee_id_number, image_url)
            for employee_id_number, image_url in pending.items()
        ]
        for employee_id_number, local_path in await asyncio.gather(*tasks):
            if local_path:
                results[employee_id_number] = local_path

    return results


async def _sync_employees(session, emp_items: list[dict[str, Any]], dept_map: dict[int, int], run_start: datetime) -> tuple[int, int, int]:
    existing = {e.employee_id_number: e for e in (await session.execute(select(Employee))).scalars()}

    created = 0
    updated = 0
    revoked = 0
    pending_images: dict[str, str] = {}

    for item in emp_items:
        employee_id_number = item["employee_id_number"]
        is_active = bool(item.get("active"))
        status_code = (item.get("employeeStatus") or {}).get("code")
        qualifies = is_active and status_code == HEMIS_ACTIVE_EMPLOYEE_STATUS_CODE

        row = existing.get(employee_id_number)
        if row is None and not qualifies:
            continue

        department_hemis_id = (item.get("department") or {}).get("id")
        local_department_id = dept_map.get(department_hemis_id) if department_hemis_id else None
        image_url = item.get("image_full")

        if row is None:
            row = Employee(
                employee_id_number=employee_id_number,
                full_name=item["full_name"],
                hemis_id=item.get("id"),
                department_id=local_department_id,
                employee_status_code=status_code,
                is_active=is_active,
                year_of_enter=item.get("year_of_enter"),
                access_revoked=False,
                last_synced_at=run_start,
            )
            session.add(row)
            await session.flush()
            existing[employee_id_number] = row
            created += 1
        else:
            row.full_name = item["full_name"]
            row.hemis_id = item.get("id")
            row.department_id = local_department_id
            row.employee_status_code = status_code
            row.is_active = is_active
            row.year_of_enter = item.get("year_of_enter")
            row.last_synced_at = run_start
            updated += 1

        if qualifies:
            if row.access_revoked:
                row.access_revoked = False
                row.access_revoked_at = None
            if image_url and image_url != row.image_source_url:
                pending_images[employee_id_number] = image_url
        elif not row.access_revoked:
            row.access_revoked = True
            row.access_revoked_at = datetime.now(timezone.utc)
            revoked += 1

    await session.flush()

    downloaded = await _download_pending_images(pending_images)
    for employee_id_number, local_path in downloaded.items():
        row = existing[employee_id_number]
        row.image_source_url = pending_images[employee_id_number]
        row.image_local_path = local_path
    await session.flush()

    # Employees entirely absent from this run's response (disappeared from HEMIS) get revoked too.
    for row in existing.values():
        if row.last_synced_at is not None and row.last_synced_at < run_start and not row.access_revoked:
            row.access_revoked = True
            row.access_revoked_at = datetime.now(timezone.utc)
            revoked += 1

    return created, updated, revoked


async def hemis_sync_task(ctx: dict, run_id: int) -> None:
    run_start = datetime.now(timezone.utc)

    async with session_scope() as session:
        run = await session.get(HemisSyncRun, run_id)
        if run is None:
            logger.error("hemis_sync_task: run %s not found", run_id)
            return

        try:
            client = HemisClient()
            dept_items = await client.fetch_departments()
            emp_items = await client.fetch_employees()

            dept_map, dept_created, dept_updated, _ = await _sync_departments(session, dept_items)
            emp_created, emp_updated, emp_revoked = await _sync_employees(session, emp_items, dept_map, run_start)

            run.status = HemisSyncStatus.SUCCESS.value
            run.departments_created = dept_created
            run.departments_updated = dept_updated
            run.employees_created = emp_created
            run.employees_updated = emp_updated
            run.employees_revoked = emp_revoked
            run.finished_at = datetime.now(timezone.utc)
        except Exception as exc:
            logger.exception("hemis_sync_task failed for run %s", run_id)
            run.status = HemisSyncStatus.FAILED.value
            run.error_message = str(exc)[:2000]
            run.finished_at = datetime.now(timezone.utc)

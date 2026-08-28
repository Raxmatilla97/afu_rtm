import asyncio
import logging
from collections import Counter
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
    # A query-string-only URL, or one ending in a path segment, has no usable suffix.
    return suffix if suffix and len(suffix) <= 5 else ".jpg"


#: HEMIS installs do not agree on what the photo field is called, and reading only one of
#: them is indistinguishable from an employee having no photo. Preference order, not a
#: search: every one of these that carries a URL is tried in turn until a download actually
#: succeeds, because a field being present says nothing about it being served.
IMAGE_KEYS = ("image_full", "image", "picture", "photo", "avatar")


def _image_candidates(item: dict[str, Any]) -> list[tuple[str, str]]:
    """Every photo URL this employee item offers, as ``(url, key)``, best first.

    All of them, not the first one found. HEMIS at Alfraganus returns two: ``image_full``,
    the original upload, and ``image``, a 320px crop. Every ``image_full`` answers 404
    there — the originals are not on the static host — while every ``image`` answers 200.
    Committing to the first field that had a value therefore meant a sync across the whole
    staff list downloaded nothing, and the interface showed initials for everybody with no
    sign that anything had failed.

    Relative paths are resolved against the HEMIS base URL: some installs return
    ``/uploads/…`` rather than a full address, and httpx cannot fetch that on its own.
    """
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key in IMAGE_KEYS:
        raw = item.get(key)
        if isinstance(raw, dict):
            raw = raw.get("url") or raw.get("src")
        if not raw or not isinstance(raw, str):
            continue
        url = raw.strip()
        if not url:
            continue
        if url.startswith("//"):
            url = f"https:{url}"
        elif url.startswith("/"):
            url = f"{settings.api_hemis_url.rstrip('/')}{url}"
        if url in seen:
            continue
        seen.add(url)
        candidates.append((url, key))
    return candidates


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


#: Which key this HEMIS install actually uses, logged once per run rather than per
#: employee — the answer is the same for all of them and 3000 identical lines help nobody.
_seen_image_keys: set[str] = set()

IMAGE_DOWNLOAD_CONCURRENCY = 15
IMAGE_DOWNLOAD_TIMEOUT = 15.0


async def _download_employee_image(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    employee_id_number: str,
    candidates: list[tuple[str, str]],
    failures: Counter[str],
) -> tuple[str, tuple[str, str] | None]:
    """Try this employee's photo URLs in turn; return the first one that actually arrives.

    Returns ``(employee_id_number, (local_path, url_used))``, or ``(id, None)`` if every
    candidate failed. The URL that worked is returned rather than assumed, because it is
    what gets stored as ``image_source_url`` and compared against on the next run.

    Trying more than one is the whole point. At Alfraganus every ``image_full`` answers 404
    while the ``image`` crop beside it answers 200 — stopping at the first URL the item
    offered meant a sync over 700 employees downloaded nothing at all, and the interface
    showed initials for everybody with no sign that anything had gone wrong.
    """
    dest_dir = Path(settings.storage_root) / "employees"
    dest_dir.mkdir(parents=True, exist_ok=True)

    async with semaphore:
        for image_url, key in candidates:
            # Per-URL failures are counted rather than logged one line at a time: with one
            # dead field across the whole staff list that is 700 identical warnings, and
            # the aggregate below says the same thing in one line.
            try:
                resp = await client.get(image_url)
            except Exception as exc:
                failures[f"{key}:{type(exc).__name__}"] += 1
                logger.debug("Image for %s: %s failed: %r", employee_id_number, image_url, exc)
                continue

            if resp.status_code != 200:
                failures[f"{key}:HTTP {resp.status_code}"] += 1
                continue

            content_type = resp.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                # HEMIS answers a missing or unauthenticated image with an HTML page,
                # which is a perfectly successful 200 and a completely useless file.
                failures[f"{key}:{content_type or 'no content-type'}"] += 1
                continue

            dest_path = dest_dir / f"{employee_id_number}{_image_extension(image_url)}"
            try:
                dest_path.write_bytes(resp.content)
            except OSError as exc:
                logger.error(
                    "Image for %s: cannot write %s: %r", employee_id_number, dest_path, exc
                )
                failures["write-failed"] += 1
                return employee_id_number, None

            return employee_id_number, (f"employees/{dest_path.name}", image_url)

    return employee_id_number, None


async def _download_pending_images(
    pending: dict[str, list[tuple[str, str]]],
) -> dict[str, tuple[str, str]]:
    """pending: employee_id_number -> [(url, key), …]. Returns the successes.

    A success is ``(local_path, url_used)``: which of the offered URLs actually answered
    with an image is worth recording, because that is what the next run compares against.
    """
    if not pending:
        return {}

    semaphore = asyncio.Semaphore(IMAGE_DOWNLOAD_CONCURRENCY)
    limits = httpx.Limits(max_connections=IMAGE_DOWNLOAD_CONCURRENCY, max_keepalive_connections=IMAGE_DOWNLOAD_CONCURRENCY)
    results: dict[str, tuple[str, str]] = {}
    failures: Counter[str] = Counter()

    # The same bearer token the API calls use. Employee photos live behind the same auth on
    # some installs and are public on others; sending it costs nothing where it is not
    # needed, and its absence is invisible where it is — the download just returns a login
    # page with a 200 status.
    headers = {"Authorization": f"Bearer {settings.api_hemis_token}"} if settings.api_hemis_token else {}

    async with httpx.AsyncClient(
        timeout=IMAGE_DOWNLOAD_TIMEOUT, follow_redirects=True, limits=limits, headers=headers
    ) as client:
        tasks = [
            _download_employee_image(client, semaphore, employee_id_number, candidates, failures)
            for employee_id_number, candidates in pending.items()
        ]
        for employee_id_number, outcome in await asyncio.gather(*tasks):
            if outcome:
                results[employee_id_number] = outcome

    if failures:
        # One line naming every way a URL failed, with counts. A field that is dead for the
        # whole institution shows up here as a single number, which is the difference
        # between "HEMIS moved the photos" and "our token expired".
        logger.info("Employee photo failures by URL: %s", dict(failures))

    return results


def _stored_image_names() -> set[str]:
    """Every employee photo actually on disk, listed once per run.

    One directory listing rather than a stat() per employee: the check below runs for a few
    thousand rows and the answer comes from the same directory every time.
    """
    try:
        return {entry.name for entry in (Path(settings.storage_root) / "employees").iterdir()}
    except OSError:
        # No directory yet on a first run, or a volume that cannot be read. Treating every
        # photo as missing is the safe direction: it re-downloads rather than skipping.
        return set()


def _image_refetch_reason(
    row: Employee, candidates: list[tuple[str, str]], stored: set[str]
) -> str | None:
    """Why this employee's photo has to be fetched again, or None to leave it alone.

    Checked in this order for a reason. "file-missing" is the case that used to be
    unreachable: a storage volume recreated between deploys leaves every
    ``image_local_path`` pointing at a file that is no longer there, and the old check —
    URL changed, or no path recorded — was satisfied by the stale path, so re-syncing could
    never repair the photos.

    The URL comparison asks whether the stored source is still *one of* the offered URLs
    rather than equal to the first one. The download falls back between fields, so the URL
    that worked is usually not the first candidate — comparing against the first would
    re-download every photo on every run for ever.
    """
    if not row.image_local_path:
        return "never-downloaded"
    if Path(row.image_local_path).name not in stored:
        return "file-missing"
    if row.image_manual_at is not None:
        # An administrator replaced this portrait on purpose. The URL check below can never
        # match a hand-uploaded file, so without this the upload would be silently
        # overwritten by the HEMIS portrait on the very next run.
        return None
    if row.image_source_url not in {url for url, _ in candidates}:
        return "url-changed"
    return None


async def _sync_employees(session, emp_items: list[dict[str, Any]], dept_map: dict[int, int], run_start: datetime) -> tuple[int, int, int]:
    existing = {e.employee_id_number: e for e in (await session.execute(select(Employee))).scalars()}

    created = 0
    updated = 0
    revoked = 0
    pending_images: dict[str, list[tuple[str, str]]] = {}
    stored_images = _stored_image_names()
    refetch_reasons: Counter[str] = Counter()

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
        image_candidates = _image_candidates(item)
        for _, image_key in image_candidates:
            if image_key not in _seen_image_keys:
                _seen_image_keys.add(image_key)
                logger.info("HEMIS employee photos arrive under key %r", image_key)

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
            reason = (
                _image_refetch_reason(row, image_candidates, stored_images)
                if image_candidates
                else None
            )
            if reason:
                if reason == "file-missing":
                    # A hand-uploaded portrait whose file has gone cannot be recovered from
                    # HEMIS, so the marker goes with it and the HEMIS photo takes over.
                    row.image_manual_at = None
                refetch_reasons[reason] += 1
                pending_images[employee_id_number] = image_candidates
        elif not row.access_revoked:
            row.access_revoked = True
            row.access_revoked_at = datetime.now(timezone.utc)
            revoked += 1

    await session.flush()

    downloaded = await _download_pending_images(pending_images)
    logger.info(
        "Employee photos: %s on disk before this run, %s requested (%s), %s downloaded",
        len(stored_images),
        len(pending_images),
        dict(refetch_reasons) or "nothing to fetch",
        len(downloaded),
    )
    for employee_id_number, (local_path, used_url) in downloaded.items():
        row = existing[employee_id_number]
        row.image_source_url = used_url
        row.image_local_path = local_path

    # A path pointing at a file that is gone is worse than no path at all: the interface
    # keeps requesting it and every list flashes a broken image before falling back to
    # initials. If the repair download did not succeed either, say so in the data.
    for employee_id_number in pending_images:
        if employee_id_number in downloaded:
            continue
        row = existing[employee_id_number]
        if row.image_local_path and Path(row.image_local_path).name not in stored_images:
            row.image_local_path = None
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

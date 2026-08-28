import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared.models import Department, Employee, Request, User
from afu_shared.activity import record_for
from afu_shared.settings import settings
from app.deps import get_admin_actor, get_current_caller, get_db
from app.schemas.employee import EmployeeProfileUpdate, EmployeeResponse, EmployeeRolesUpdate

router = APIRouter(prefix="/employees", tags=["employees"])


#: Sort keys the employee list accepts. Anything else falls back to the name order, so a
#: stale link cannot produce an empty page.
SORT_BY_NAME = "name"
SORT_BY_REQUESTS = "requests"

#: A portrait, not a photo album. Anything larger is a camera original nobody cropped.
MAX_PHOTO_BYTES = 5 * 1024 * 1024

#: The earliest year of employment worth accepting. Guards against a mistyped date turning
#: into a four-digit number the statistics then plot.
MIN_YEAR_OF_ENTER = 1950


def _image_suffix(data: bytes) -> str | None:
    """The file type ``data`` actually is, or None if it is not an image we accept.

    Read from the bytes rather than from the upload's declared content type: that header
    is whatever the browser — or whoever wrote the request by hand — chose to claim, and
    this file is served back to every visitor afterwards.
    """
    signatures = (
        (bytes.fromhex("ffd8ff"), ".jpg"),
        (bytes.fromhex("89504e470d0a1a0a"), ".png"),
        (b"GIF87a", ".gif"),
        (b"GIF89a", ".gif"),
    )
    for magic, suffix in signatures:
        if data.startswith(magic):
            return suffix
    # WebP carries its marker eight bytes in, past the RIFF container length.
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


@router.get("", response_model=list[EmployeeResponse])
async def list_employees(
    q: str | None = None,
    department_id: int | None = None,
    is_rtm_staff: bool | None = None,
    sort: str = SORT_BY_NAME,
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> list[EmployeeResponse]:
    """The employee roster, filtered and ordered as the admin panel asked.

    Every row carries how many requests that person has filed. It is a correlated subquery
    rather than a join with a GROUP BY on purpose: the result stays exactly one row per
    employee, so the 500-row limit still means 500 people rather than 500 request-rows
    collapsed into fewer.
    """
    filed_count = (
        select(func.count(Request.id))
        .where(Request.requester_employee_id == Employee.id)
        .correlate(Employee)
        .scalar_subquery()
        .label("request_count")
    )

    stmt = select(Employee, filed_count)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Employee.full_name.ilike(like), Employee.employee_id_number.ilike(like)))
    if department_id is not None:
        stmt = stmt.where(Employee.department_id == department_id)
    if is_rtm_staff is not None:
        stmt = stmt.where(Employee.is_rtm_staff == is_rtm_staff)

    if sort == SORT_BY_REQUESTS:
        # Name as the tie-break: without it everyone on zero requests comes back in
        # whatever order the database felt like, and the list reshuffles on every reload.
        stmt = stmt.order_by(filed_count.desc(), Employee.full_name)
    else:
        stmt = stmt.order_by(Employee.full_name)

    rows = (await session.execute(stmt.limit(500))).all()
    return [
        EmployeeResponse.from_employee(employee, request_count=count)
        for employee, count in rows
    ]


@router.get("/rtm-staff", response_model=list[EmployeeResponse])
async def list_rtm_staff(
    caller: User | Employee = Depends(get_current_caller),
    session: AsyncSession = Depends(get_db),
) -> list[EmployeeResponse]:
    """Who a request can be handed to.

    Declared above ``/{employee_id}`` because FastAPI matches in order, and a literal path
    that comes second is a path that never matches.

    Open to Boshliq as well as Admin, unlike the full directory below. Assigning work is
    exactly what the Boshliq role is for, and both the assign form and the staff filter on
    the request list were dead for them while the only list of staff sat behind an
    admin-only endpoint — the form rendered with no names in it and looked broken.
    """
    if isinstance(caller, Employee) and not caller.can_manage_assignments:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Faqat Boshliq yoki Admin"
        )

    stmt = select(Employee).where(Employee.is_rtm_staff.is_(True)).order_by(Employee.full_name)
    return [EmployeeResponse.from_employee(e) for e in (await session.execute(stmt)).scalars()]


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: int, actor: User | Employee = Depends(get_admin_actor), session: AsyncSession = Depends(get_db)
) -> EmployeeResponse:
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    return EmployeeResponse.from_employee(employee)


@router.post("/{employee_id}/promote-to-staff", response_model=EmployeeResponse)
async def promote_to_staff(
    employee_id: int, actor: User | Employee = Depends(get_admin_actor), session: AsyncSession = Depends(get_db)
) -> EmployeeResponse:
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    employee.is_rtm_staff = True
    await session.flush()
    return EmployeeResponse.from_employee(employee)


@router.post("/{employee_id}/demote", response_model=EmployeeResponse)
async def demote_from_staff(
    employee_id: int, actor: User | Employee = Depends(get_admin_actor), session: AsyncSession = Depends(get_db)
) -> EmployeeResponse:
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    employee.is_rtm_staff = False
    await session.flush()
    return EmployeeResponse.from_employee(employee)


@router.post("/{employee_id}/roles", response_model=EmployeeResponse)
async def update_roles(
    employee_id: int,
    payload: EmployeeRolesUpdate,
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """Set any subset of an employee's flags.

    One endpoint for all of them, taking only the fields that were sent, because the admin
    table toggles them individually: a per-flag endpoint would be four near-identical
    handlers, and a whole-object PUT would let one toggle silently reset the rest.
    """
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    if payload.is_rtm_staff is not None:
        employee.is_rtm_staff = payload.is_rtm_staff
    if payload.is_supervisor is not None:
        employee.is_supervisor = payload.is_supervisor
    if payload.is_admin is not None:
        employee.is_admin = payload.is_admin
    if payload.is_blocked is not None and payload.is_blocked != employee.is_blocked:
        employee.is_blocked = payload.is_blocked
        employee.blocked_at = datetime.now(timezone.utc) if payload.is_blocked else None

    await record_for(
        session,
        actor,
        action="employee.roles",
        target=employee.full_name,
        detail=", ".join(
            f"{field}={value}"
            for field, value in payload.model_dump(exclude_none=True).items()
        ),
    )
    await session.flush()
    return EmployeeResponse.from_employee(employee)


@router.post("/{employee_id}/revoke", response_model=EmployeeResponse)
async def revoke_access(
    employee_id: int, actor: User | Employee = Depends(get_admin_actor), session: AsyncSession = Depends(get_db)
) -> EmployeeResponse:
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")
    employee.access_revoked = True
    employee.access_revoked_at = datetime.now(timezone.utc)
    await session.flush()
    return EmployeeResponse.from_employee(employee)


#: The columns an administrator may correct by hand. Listed once, applied in a loop, so
#: adding a field to the schema and forgetting to write it here is not possible.
EDITABLE_FIELDS = (
    "full_name",
    "department_id",
    "phone_number",
    "telegram_username",
    "recovery_email",
    "hemis_email",
    "hemis_phone",
    "year_of_enter",
)


# POST rather than PATCH, and POST rather than DELETE below. Nothing in this API uses any
# other verb, and that is not an accident: the reverse proxy in front of production allows
# GET, POST and HEAD only, so a PATCH would come back as a bare 405 from a component this
# repository cannot configure. See the 405 case in the frontend's describeError.
@router.post("/{employee_id}/profile", response_model=EmployeeResponse)
async def update_employee(
    employee_id: int,
    payload: EmployeeProfileUpdate,
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """Correct an employee's record by hand.

    Only the fields actually present in the request body are written — ``model_fields_set``
    rather than "is it None", because for every one of these columns None is a legitimate
    value meaning "clear it". Without that distinction a dialog that saves one field would
    wipe the seven it did not send.
    """
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    sent = payload.model_fields_set

    if "full_name" in sent and not payload.full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="F.I.Sh. bo'sh bo'lishi mumkin emas"
        )
    if "department_id" in sent and payload.department_id is not None:
        if await session.get(Department, payload.department_id) is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Bunday bo'lim topilmadi"
            )
    if "year_of_enter" in sent and payload.year_of_enter is not None:
        this_year = datetime.now(timezone.utc).year
        if not MIN_YEAR_OF_ENTER <= payload.year_of_enter <= this_year:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ishga kirgan yil {MIN_YEAR_OF_ENTER} va {this_year} orasida bo'lsin",
            )

    changed: list[str] = []
    for field in EDITABLE_FIELDS:
        if field not in sent:
            continue
        value = getattr(payload, field)
        if getattr(employee, field) != value:
            setattr(employee, field, value)
            changed.append(field)

    if changed:
        await record_for(
            session,
            actor,
            action="employee.update",
            target=employee.full_name,
            detail=", ".join(changed),
        )
    await session.flush()
    # Re-read rather than trust the instance: department_id has just changed and the
    # response prints the department *name*, which is a relationship the session is still
    # holding at its old value.
    await session.refresh(employee)
    return EmployeeResponse.from_employee(employee)


@router.post("/{employee_id}/photo", response_model=EmployeeResponse)
async def upload_employee_photo(
    employee_id: int,
    file: UploadFile = File(...),
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """Replace an employee's portrait with an uploaded one.

    Written under a fresh random name rather than over the HEMIS file. Two reasons: the
    photo is cached by every browser that has seen the old one, and a new path is the only
    reliable way to make them all fetch it; and the HEMIS copy stays on disk, so removing
    the upload later restores the original instead of leaving a blank circle.
    """
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    data = await file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Surat hajmi {MAX_PHOTO_BYTES // (1024 * 1024)} MB dan oshmasligi kerak",
        )
    suffix = _image_suffix(data)
    if suffix is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Faqat JPG, PNG, WEBP yoki GIF surat yuklash mumkin",
        )

    dest_dir = Path(settings.storage_root) / "employees"
    dest_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{employee.employee_id_number}-m{uuid.uuid4().hex[:8]}{suffix}"
    try:
        (dest_dir / stored_name).write_bytes(data)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Suratni saqlab bo'lmadi",
        ) from exc

    previous = employee.image_local_path if employee.image_manual_at else None
    employee.image_local_path = f"employees/{stored_name}"
    employee.image_manual_at = datetime.now(timezone.utc)

    if previous and previous != employee.image_local_path:
        # Only ever a previous *upload*: the HEMIS-downloaded portrait is left alone so
        # that removing this one can fall back to it.
        (Path(settings.storage_root) / previous).unlink(missing_ok=True)

    await record_for(session, actor, action="employee.photo", target=employee.full_name)
    await session.flush()
    return EmployeeResponse.from_employee(employee)


@router.post("/{employee_id}/photo/delete", response_model=EmployeeResponse)
async def delete_employee_photo(
    employee_id: int,
    actor: User | Employee = Depends(get_admin_actor),
    session: AsyncSession = Depends(get_db),
) -> EmployeeResponse:
    """Drop the current portrait.

    Clearing ``image_source_url`` along with the path is what lets HEMIS fill the gap
    again: the sync treats an employee with no recorded photo as never-downloaded and
    fetches theirs on the next run. Until then the interface shows initials.
    """
    employee = await session.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

    if employee.image_manual_at and employee.image_local_path:
        (Path(settings.storage_root) / employee.image_local_path).unlink(missing_ok=True)

    employee.image_local_path = None
    employee.image_source_url = None
    employee.image_manual_at = None

    await record_for(
        session, actor, action="employee.photo", target=employee.full_name, detail="o'chirildi"
    )
    await session.flush()
    return EmployeeResponse.from_employee(employee)

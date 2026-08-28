"""The quick login on the web: employee id number plus a local password.

Kept apart from ``api/auth.py``, which is about the panel admin's email session. This is a
different door for a different reason — HEMIS signs in through One-ID now, which most staff
have not linked — and the rules behind it live in ``afu_shared.quick_login`` so the bot
enforces exactly the same ones.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from afu_shared import quick_login
from afu_shared.passwords import mask_email
from app.arq_pool import get_arq_pool
from app.deps import get_db
from app.schemas.auth import (
    EmployeeMeResponse,
    QuickForgotRequest,
    QuickForgotResponse,
    QuickLoginRequest,
    QuickLookupRequest,
    QuickLookupResponse,
    QuickResetRequest,
    QuickSetupRequest,
)
from app.session import set_session_cookie

router = APIRouter(prefix="/auth/quick", tags=["auth"])


@router.post("/lookup", response_model=QuickLookupResponse)
async def quick_lookup(
    payload: QuickLookupRequest, session: AsyncSession = Depends(get_db)
) -> QuickLookupResponse:
    """Who is behind this id number, and what the form should ask for next."""
    employee = await quick_login.employee_by_id_number(session, payload.employee_id_number)
    if employee is None:
        return QuickLookupResponse(status=quick_login.Outcome.NOT_FOUND.value)
    if not employee.is_eligible:
        return QuickLookupResponse(
            status=quick_login.Outcome.NOT_ELIGIBLE.value, full_name=employee.full_name
        )

    locked = quick_login.lock_minutes_remaining(employee)
    if locked:
        return QuickLookupResponse(
            status=quick_login.Outcome.LOCKED.value,
            full_name=employee.full_name,
            locked_minutes=locked,
        )

    return QuickLookupResponse(
        status=(
            "needs_password"
            if employee.quick_password_hash
            else quick_login.Outcome.NEEDS_SETUP.value
        ),
        full_name=employee.full_name,
        department_name=employee.department.name if employee.department else None,
        masked_email=mask_email(employee.recovery_email) if employee.recovery_email else None,
    )


def _failure_message(result: quick_login.QuickLoginResult) -> str:
    """One Uzbek sentence per outcome, saying what to do rather than what went wrong."""
    if result.outcome is quick_login.Outcome.NOT_FOUND:
        return "Bunday xodim ID raqami topilmadi. Raqamni tekshirib qaytadan kiriting."
    if result.outcome is quick_login.Outcome.NOT_ELIGIBLE:
        return "Hisobingiz faol emas. RTM bilan bog'laning."
    if result.outcome is quick_login.Outcome.NEEDS_SETUP:
        return "Bu hisobda hali parol yo'q — avval parol o'rnating."
    if result.outcome is quick_login.Outcome.LOCKED:
        return (
            f"Parol bir necha marta noto'g'ri kiritildi. {result.locked_minutes} daqiqadan "
            "keyin qaytadan urinib ko'ring yoki parolni tiklang."
        )
    return "Parol noto'g'ri. Qaytadan urinib ko'ring yoki parolni tiklang."


@router.post("/login", response_model=EmployeeMeResponse)
async def quick_login_submit(
    payload: QuickLoginRequest, response: Response, session: AsyncSession = Depends(get_db)
) -> EmployeeMeResponse:
    result = await quick_login.check_password(
        session, payload.employee_id_number, payload.password
    )
    if not result.ok or result.employee is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_failure_message(result)
        )

    set_session_cookie(response, subject=str(result.employee.id), scope="employee")
    return EmployeeMeResponse.from_employee(result.employee)


@router.post("/setup", response_model=EmployeeMeResponse)
async def quick_setup(
    payload: QuickSetupRequest, response: Response, session: AsyncSession = Depends(get_db)
) -> EmployeeMeResponse:
    """First claim of an account: set the password and the recovery address, then sign in."""
    employee = await quick_login.employee_by_id_number(session, payload.employee_id_number)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Bunday xodim ID raqami topilmadi."
        )
    if not employee.is_eligible:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hisobingiz faol emas. RTM bilan bog'laning.",
        )

    try:
        await quick_login.claim_account(session, employee, payload.password)
    except quick_login.WeakPassword as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await quick_login.set_recovery_email(session, employee, str(payload.recovery_email))
    set_session_cookie(response, subject=str(employee.id), scope="employee")
    return EmployeeMeResponse.from_employee(employee)


@router.post("/forgot", response_model=QuickForgotResponse)
async def quick_forgot(
    payload: QuickForgotRequest, session: AsyncSession = Depends(get_db)
) -> QuickForgotResponse:
    """Send the reset link, and say which address it went to.

    Naming the masked address is the point of this step: somebody who can no longer open
    that mailbox has to learn it here rather than after waiting for a letter that they will
    never read.
    """
    employee = await quick_login.employee_by_id_number(session, payload.employee_id_number)
    if employee is None or not employee.is_eligible:
        # Deliberately the same answer as the success case: this endpoint must not become a
        # way of testing which id numbers exist.
        return QuickForgotResponse(
            sent=False,
            message="Agar bunday hisob mavjud bo'lsa, xat yuborildi. Pochtangizni tekshiring.",
        )

    if not employee.recovery_email:
        return QuickForgotResponse(
            sent=False,
            message=(
                "Bu hisobga elektron pochta biriktirilmagan, shuning uchun parolni "
                "avtomatik tiklab bo'lmaydi. RTM bilan bog'laning."
            ),
        )

    token = await quick_login.start_password_reset(session, employee)
    # Committed before the job is queued: the worker reads the row in its own session and
    # would otherwise mail a token the database does not know about yet.
    await session.commit()
    if token:
        pool = await get_arq_pool()
        await pool.enqueue_job("send_password_reset_email", employee.id, token)

    masked = mask_email(employee.recovery_email)
    return QuickForgotResponse(
        sent=True,
        masked_email=masked,
        message=(
            f"Parolni tiklash havolasi {masked} manziliga yuborildi. "
            "Havola 1 soat davomida amal qiladi."
        ),
    )


@router.post("/reset")
async def quick_reset(
    payload: QuickResetRequest, session: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    """Set a new password from the link in the email."""
    try:
        employee = await quick_login.complete_password_reset(
            session, payload.token, payload.password
        )
    except quick_login.WeakPassword as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Havola eskirgan yoki allaqachon ishlatilgan. Tiklashni qaytadan boshlang.",
        )

    return {
        "employee_id_number": employee.employee_id_number,
        "message": "Parol yangilandi. Endi botda yoki saytda shu parol bilan kiring.",
    }

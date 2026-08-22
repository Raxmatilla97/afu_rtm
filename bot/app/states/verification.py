from aiogram.fsm.state import State, StatesGroup


class VerificationStates(StatesGroup):
    awaiting_employee_id = State()
    awaiting_identity_confirm = State()
    awaiting_contact = State()

from aiogram.fsm.state import State, StatesGroup


class StaffActionStates(StatesGroup):
    awaiting_completion_note = State()
    awaiting_message_to_requester = State()
    awaiting_internal_message = State()


class RequesterStates(StatesGroup):
    """Requester replying inside their own request thread."""

    awaiting_reply_body = State()

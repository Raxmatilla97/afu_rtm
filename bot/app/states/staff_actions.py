from aiogram.fsm.state import State, StatesGroup


class StaffActionStates(StatesGroup):
    awaiting_completion_note = State()
    #: The report is written but the request is not closed yet — the inventory step is
    #: on screen. Its own state so a stray message here is not mistaken for a second report.
    choosing_inventory = State()
    awaiting_message_to_requester = State()
    awaiting_internal_message = State()


class RequesterStates(StatesGroup):
    """Requester replying inside their own request thread."""

    awaiting_reply_body = State()

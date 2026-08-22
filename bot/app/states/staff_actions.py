from aiogram.fsm.state import State, StatesGroup


class StaffActionStates(StatesGroup):
    awaiting_completion_note = State()
    awaiting_message_to_requester = State()
    awaiting_internal_message = State()


class RatingStates(StatesGroup):
    awaiting_comment = State()

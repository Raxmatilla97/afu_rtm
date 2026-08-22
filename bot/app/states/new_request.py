from aiogram.fsm.state import State, StatesGroup


class NewRequestStates(StatesGroup):
    awaiting_category = State()
    awaiting_description = State()
    awaiting_attachment_choice = State()
    awaiting_photo = State()

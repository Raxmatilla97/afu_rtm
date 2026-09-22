from aiogram.fsm.state import State, StatesGroup


class NewRequestStates(StatesGroup):
    awaiting_category = State()
    awaiting_description = State()
    awaiting_attachment_choice = State()
    awaiting_media = State()
    #: Boshliq only. The two extra steps that turn a request into a directive — see
    #: ``app.screens.new_request``. Everybody else goes straight from the media step to a
    #: published card, exactly as before.
    awaiting_deadline = State()
    awaiting_assignees = State()

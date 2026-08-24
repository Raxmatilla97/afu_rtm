from aiogram.fsm.state import State, StatesGroup


class AuthStates(StatesGroup):
    """HEMIS OAuth resolves identity; only the contact share still needs a bot-side state."""

    awaiting_contact = State()

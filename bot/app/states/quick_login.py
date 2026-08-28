from aiogram.fsm.state import State, StatesGroup


class QuickLoginStates(StatesGroup):
    """Signing in with an employee id number and a local password.

    Four steps rather than one form, because a chat has no form: each state names exactly
    what the next typed line means, so a stray message is never mistaken for a password and
    a password is never mistaken for an id number.
    """

    awaiting_id_number = State()
    #: First claim of this account — the password is being chosen right now.
    awaiting_new_password = State()
    #: Straight after the password: where a forgotten one should be sent.
    awaiting_email = State()
    #: Returning user typing the password they already set.
    awaiting_password = State()

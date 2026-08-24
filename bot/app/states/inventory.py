from aiogram.fsm.state import State, StatesGroup


class InventoryStates(StatesGroup):
    """The two places the inventory detour needs typed input.

    Everything else is buttons. Typing is reserved for the answers a picker genuinely
    cannot cover — an unusual quantity, and why a job is blocked.
    """

    awaiting_quantity = State()
    awaiting_wait_reason = State()

"""Typed callback data factories.

Replaces the previous flat ``prefix:arg`` strings, which were matched with ``startswith``
and so were one naming choice away from colliding (``req:`` vs ``req_start:``). Prefixes are
kept to one character because callback_data is capped at 64 bytes.
"""

from aiogram.filters.callback_data import CallbackData


class Nav(CallbackData, prefix="n"):
    """Pure navigation between screens."""

    to: str  # menu | help | login | myreq | assign | stats | newreq | noop
    page: int = 1


class ReqCB(CallbackData, prefix="r"):
    """Requester-side actions on their own request."""

    act: str  # open | thread | reply | rate | rate_set | files | back
    rid: int = 0
    page: int = 1
    score: int = 0


class AsgCB(CallbackData, prefix="a"):
    """RTM-staff actions on an assigned request."""

    act: str  # open | thread | start | complete | msg | internal | files | back
    rid: int = 0
    page: int = 1


class CatCB(CallbackData, prefix="c"):
    """Category choice while creating a request."""

    slug: str


class FlowCB(CallbackData, prefix="f"):
    """Steps inside the new-request flow."""

    act: str  # attach_yes | attach_no | media_done | cancel


class StatCB(CallbackData, prefix="s"):
    """Which statistics tab to show.

    Statistics used to be one static wall of numbers. Splitting it into tabs that swap in
    place on the anchor message is what makes it explorable inside a chat, where there is
    no room to show everything at once.
    """

    view: str  # overview | mine | work | top


class GrpCB(CallbackData, prefix="g"):
    """Buttons on a request card in an RTM group chat.

    A separate factory from ``AsgCB`` because the two answer to different rules: the
    assignment screens require the presser to already own the request, while these are
    offered precisely to people who do not yet.
    """

    act: str  # take | files | assign | pick | back
    rid: int = 0
    #: ``pick`` only: which employee the supervisor chose.
    eid: int = 0
    #: ``assign`` only: page of the staff picker.
    page: int = 1


class InvCB(CallbackData, prefix="i"):
    """Picking inventory while closing a request, and parking a request that is blocked.

    Deliberately terse. Callback data is capped at 64 bytes and this factory carries the
    most fields of any of them, so the category is referenced by its slug and everything
    else by id.
    """

    act: str  # skip | cats | items | pick | qty | done | wait | wait_for
    rid: int = 0
    #: ``items`` only — which category is being browsed.
    slug: str = ""
    #: ``pick``/``qty`` only — the chosen item.
    iid: int = 0
    #: ``qty`` only — how many, or ``wait_for`` — how many days to wait.
    n: int = 0
    page: int = 1


class QuickCB(CallbackData, prefix="q"):
    """Buttons on the login screen and inside the quick-login flow.

    ``act``: ``start`` opens the id-number step, ``reset`` mails a password reset,
    ``back`` returns to the two login options.
    """

    act: str


class SoftCB(CallbackData, prefix="d"):
    """The driver and software shelf.

    ``d`` for "download": ``s`` was already taken by the statistics tabs, and a collision
    would route a stats tap into a file send.
    """

    act: str  # cats | list | get | back
    slug: str = ""
    aid: int = 0
    page: int = 1

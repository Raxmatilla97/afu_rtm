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

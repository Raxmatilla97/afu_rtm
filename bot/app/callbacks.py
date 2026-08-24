"""Callback data factories — re-exported from ``afu_shared``.

They live in ``shared`` because the worker builds buttons too: the completion notice and
the new assignment DM both carry callbacks that this bot has to route. When the factories
lived here the worker hand-wrote the packed strings ("a:open:12:1"), which meant a field
added on this side silently produced buttons that no longer parsed on the other.
"""

from afu_shared.callbacks import AsgCB, CatCB, FlowCB, GrpCB, Nav, ReqCB, StatCB

__all__ = ["AsgCB", "CatCB", "FlowCB", "GrpCB", "Nav", "ReqCB", "StatCB"]

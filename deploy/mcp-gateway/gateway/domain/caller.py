"""当前调用方。user_id / cube 只来自 token，永不作为工具参数。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Caller:
    user_id: str
    cube_id: str

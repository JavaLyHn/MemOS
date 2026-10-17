"""从 Bearer token 取调用方身份。"""

from __future__ import annotations

from fastmcp.server.dependencies import get_access_token

from .config import Settings
from .domain.caller import Caller
from .errors import MemoryServiceError


class IdentityResolver:
    def __init__(self, settings: Settings):
        self._allowed = settings.allowed_cubes

    def current(self) -> Caller:
        """取当前调用方 —— 只能来自 token，不能来自模型。"""
        token = get_access_token()
        claims = dict(getattr(token, "claims", None) or {})
        user_id = claims.get("user_id")
        if not user_id:
            raise MemoryServiceError(
                "无法确定调用方身份：请使用分配给自己的 Bearer token 访问本服务。"
            )
        cube_id = claims.get("cube_id") or user_id
        if self._allowed and cube_id not in self._allowed:
            raise MemoryServiceError(f"cube '{cube_id}' is not allowed")
        return Caller(user_id=user_id, cube_id=cube_id)

    def peek_user_id(self) -> str | None:
        """尽力取当前 MCP 请求的租户；取不到返回 None（审计绝不能让请求失败）。"""
        try:
            token = get_access_token()
            claims = dict(getattr(token, "claims", None) or {})
            return claims.get("user_id")
        except Exception:  # noqa: BLE001
            return None

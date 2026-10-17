"""token → 记忆空间。解析、查询、掩码都走 TenantRegistry。"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Tenant:
    user_id: str
    cube_id: str


def parse_tenants(raw: str) -> dict[str, Tenant]:
    """把 MEMOS_TENANTS 解析成 {token: Tenant}。"""
    raw = (raw or "").strip()
    if not raw:
        return {}
    if raw.startswith("{"):
        data = json.loads(raw)
        out: dict[str, Tenant] = {}
        for token, spec in data.items():
            if isinstance(spec, str):
                spec = {"user_id": spec}
            uid = (spec or {}).get("user_id")
            if not uid:
                raise ValueError(f"tenant '{token}' has no user_id")
            out[token] = Tenant(user_id=uid, cube_id=spec.get("cube_id") or uid)
        return out
    # 紧凑写法 tok:user_id,tok2:user_id2
    # 用 rpartition 而不是 partition：token 里万一出现冒号也不会把映射切错，
    # 因为 user_id 不允许含冒号，最后一个冒号右边一定是 user_id。
    out = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        token, sep, uid = pair.rpartition(":")
        token, uid = token.strip(), uid.strip()
        if not sep or not token or not uid:
            raise ValueError(f"malformed tenant entry: {pair!r} (expected token:user_id)")
        out[token] = Tenant(user_id=uid, cube_id=uid)
    return out


def mask_token(token: str | None) -> str | None:
    """token 掩码：前 12 + 后 4。"""
    if not token:
        return None
    if len(token) <= 20:
        return token[:4] + "…"
    return f"{token[:12]}…{token[-4:]}"


class TenantRegistry:
    def __init__(self, mapping: dict[str, Tenant]):
        self._by_token = mapping

    @classmethod
    def from_raw(cls, raw: str) -> TenantRegistry:
        return cls(parse_tenants(raw))

    def __len__(self) -> int:
        return len(self._by_token)

    def get(self, token: str | None) -> Tenant | None:
        if not token:
            return None
        return self._by_token.get(token)

    def user_id_of(self, token: str | None) -> str | None:
        """不认识的 token 返回 None（正是 401 那批）。"""
        tenant = self.get(token)
        return tenant.user_id if tenant else None

    def verifier_tokens(self) -> dict[str, dict]:
        """StaticTokenVerifier 要的 claims 表。"""
        return {
            token: {
                "client_id": tenant.user_id,
                "scopes": ["memory"],
                "user_id": tenant.user_id,
                "cube_id": tenant.cube_id,
            }
            for token, tenant in self._by_token.items()
        }

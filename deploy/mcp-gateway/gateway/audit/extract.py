"""从工具参数 / JSON-RPC 消息里折会话、个案标识、工具名。"""

from __future__ import annotations

import inspect
import json
import re

from ..domain.session import session_id_from_first_message

CASE_LIKE_PATTERNS = (
    r"[0-9a-f]{8}-[0-9a-f]{4}-",                              # UUID / task_id
    r"uid[:：]?\s*\d{4,}",                                    # uid
    r"A2600[0-9A-Z]{5,}",                                    # 业务编号
    r"\b[0-9a-f]{32,64}\b",                                  # 文件哈希
    r"\b\d{1,3}(?:\.\d{1,3}){3}\b",                           # IP
    r"(?:[a-z0-9-]+\.)+(?:com|cn|net|org|io|top|xyz)\b",        # 域名
)


def looks_case_specific(text) -> bool:
    """只看不拦：判断待写入内容是否像「个案结论」。"""
    if not isinstance(text, str):
        try:
            text = json.dumps(text, ensure_ascii=False)
        except Exception:
            return False
    return any(re.search(pat, text, re.I) for pat in CASE_LIKE_PATTERNS)


def _bound_args(fn, args, kwargs):
    return inspect.signature(fn).bind(*args, **kwargs).arguments


def case_like_from_args(fn, args, kwargs) -> bool | None:
    """从 add_message 的 messages 判断是否含个案标识；非写入类工具返回 None。"""
    try:
        msgs = _bound_args(fn, args, kwargs).get("messages")
        if msgs is None:
            return None
        return looks_case_specific(msgs)
    except Exception:
        return None


def session_id_from_args(fn, args, kwargs) -> str | None:
    """工具层：从入参折算会话标识。审计是旁路，任何异常都必须吞掉。"""
    try:
        first = _bound_args(fn, args, kwargs).get("conversation_first_message")
        if not isinstance(first, str) or not first.strip():
            return None
        return session_id_from_first_message(first)
    except Exception:  # noqa: BLE001
        return None


def session_id_from_message(message) -> str | None:
    """协议层：从 JSON-RPC 消息的 arguments 里折算会话标识。"""
    try:
        params = getattr(message, "params", None)
        arguments = getattr(params, "arguments", None)
        if arguments is None and isinstance(params, dict):
            arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            return None
        first = arguments.get("conversation_first_message")
        if not isinstance(first, str) or not first.strip():
            return None
        return session_id_from_first_message(first)
    except Exception:  # noqa: BLE001
        return None


def rpc_tool_name(message) -> str | None:
    """从 MCP 消息里取工具名。

    实测 fastmcp 2.13 在中间件这层给的**对象形态随方法而异**，所以要三级回退：
      - tools/call  → CallToolRequestParams 本身，工具名直接在 message.name
      - initialize  → InitializeRequest，参数在 message.params
      - tools/list  → ListToolsRequest，本来就没有工具名
    只查 params.name 的话，tools/call 会被记成 null（踩过）。
    """
    name = getattr(message, "name", None)
    if name:
        return name
    params = getattr(message, "params", None)
    if isinstance(params, dict):
        return params.get("name")
    return getattr(params, "name", None)


SEARCH_BUCKETS = {
    "memory_detail_list": "text",
    "preference_detail_list": "pref",
    "tool_memory_detail_list": "tool",
}


def search_hits(out: str | None) -> list[dict]:
    if not out:
        return []
    data = json.loads(out)
    returned = []
    for key, bucket in SEARCH_BUCKETS.items():
        for item in data.get(key) or []:
            text = (
                item.get("memory_value")
                or item.get("preference")
                or item.get("tool_value")
                or ""
            )
            returned.append({
                "id": item.get("memory_id") or item.get("id"),
                "bucket": bucket,
                "score": item.get("relativity"),
                "excerpt": " ".join(str(text).split())[:200],
            })
    return returned


_MAX_AUDIT_CHARS = 16_000


def clip(value, *, limit: int = _MAX_AUDIT_CHARS):
    """审计落盘用：超长截断并打标，避免单行把 JSONL 撑爆。"""
    if value is None:
        return None
    if isinstance(value, str):
        if len(value) <= limit:
            return value
        return {"truncated": True, "chars": len(value), "text": value[:limit]}
    try:
        dumped = json.dumps(value, ensure_ascii=False)
    except TypeError:
        dumped = str(value)
    if len(dumped) <= limit:
        return value
    return {"truncated": True, "chars": len(dumped), "text": dumped[:limit]}


def args_for_audit(fn, args, kwargs):
    """工具入参原样折成可 JSON 的 dict（绑定失败则退回 raw）。"""
    try:
        bound = dict(_bound_args(fn, args, kwargs))
        return {k: clip(v) for k, v in bound.items()}
    except Exception:  # noqa: BLE001
        return {"args": clip(list(args)), "kwargs": clip(kwargs)}

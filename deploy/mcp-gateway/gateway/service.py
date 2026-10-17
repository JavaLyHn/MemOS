"""记忆用例：5 个 MCP 工具的业务逻辑，不碰 FastMCP。"""

from __future__ import annotations

import json

from .backend import ProductClient
from .config import Settings
from .domain.caller import Caller
from .domain.session import session_id_from_first_message
from .domain.shape import cloud_lists, dump_json, total_nodes
from .errors import MemoryServiceError


def _clamp(value, *, default: int, lo: int, hi: int) -> int:
    try:
        n = int(value if value is not None else default)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(n, hi))


_QUOTE_FOLLOWERS = frozenset(":,}]")


def _repair_unescaped_quotes(text: str) -> str:
    """给字符串内部未转义的引号补上反斜杠。

    只在 `json.loads` 失败之后兜底。一个引号若是 JSON 字符串的结束符，它后面第一个
    非空白字符必然是 `:`、`,`、`}` 或 `]`；不是这四种，就说明它是内容里的一部分。
    实测：`"content":"…这是"某个名称"的记录…"` —— 内容里
    自带的引号没转义，整段 JSON 因此不合法。
    """
    out: list[str] = []
    in_string = False
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_string and ch == "\\" and i + 1 < n:
            out.append(text[i : i + 2])
            i += 2
            continue
        if ch == '"':
            if not in_string:
                in_string = True
                out.append(ch)
            else:
                j = i + 1
                while j < n and text[j] in " \t\r\n":
                    j += 1
                if j < n and text[j] in _QUOTE_FOLLOWERS:
                    in_string = False
                    out.append(ch)
                else:
                    out.append('\\"')
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _loads_lenient(text: str):
    """先按原样解析，不合法再补一次引号转义。两次都不行返回 None。"""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        pass
    try:
        return json.loads(_repair_unescaped_quotes(text))
    except (TypeError, ValueError):
        return None


def _decode_message_item(item) -> list:
    """把一项入参展开成消息 dict 的列表，展开不了就返回空列表。

    客户端（调用方 agent 背后的 LLM）有时把整段对话当 JSON 文本发过来，于是 `messages`
    长成 `['[{"role": "user", "content": "..."}]']`——列表里装的是 JSON 字符串，不是 dict。
    实测这一种占 add_message 调用的 10%~23%，
    每次都是一个静默丢掉的写入。
    """
    if isinstance(item, dict):
        return [item]
    if not isinstance(item, str):
        return []
    decoded = _loads_lenient(item)
    if isinstance(decoded, dict):
        return [decoded]
    if isinstance(decoded, list):
        return [d for d in decoded if isinstance(d, dict)]
    return []


def _normalize_messages(messages) -> list[dict]:
    # 整个 messages 也可能是一个 JSON 字符串而不是列表。
    if isinstance(messages, str):
        messages = _decode_message_item(messages)
    if not messages:
        raise MemoryServiceError("messages must not be empty")
    flattened: list = []
    for item in messages:
        flattened.extend(_decode_message_item(item))
    normalized = [
        {"role": str(m.get("role") or "user"), "content": str(m.get("content") or "")}
        for m in flattened
    ]
    if not normalized:
        raise MemoryServiceError(
            "messages 里没有可用的消息对象；每项应为 "
            '{"role": "user"|"assistant", "content": "..."}'
        )
    return normalized


# 关键词替换路径（feedback.py 的 process_keyword_replace）会改掉**所有**含该词的记忆，
# 一次反馈上百条是可能的，而审计日志会把工具返回值整个写进 calls-*.jsonl 的 output 字段。
_FEEDBACK_ITEM_LIMIT = 50


def _feedback_summary(result) -> dict:
    """把后端 feedback 的 record 折成对外形状。

    后端 ``/product/feedback`` 返回 ``[{"answer": ..., "record": {"add": [...], "update": [...]}}]``，
    ``record`` 就是这次纠错到底改了哪几条的完整清单。网关以前连返回值都不接，只回一句无条件的
    ``"Feedback recorded"``：改没改、改了几条、还是后端 30 秒超时静默返回了空 record，调用方
    一概分辨不出来 —— 而这条通道是 5 个工具里唯一被设计成"修改/纠错"的入口。

    ``record`` 为空（超时、无有效判定、或反馈被判成无关）时如实说明未产生改动，不拿成功文案盖过去。
    """
    added: list[dict] = []
    updated: list[dict] = []

    payloads = result if isinstance(result, list) else [result]
    for payload in payloads:
        record = payload.get("record") if isinstance(payload, dict) else None
        if not isinstance(record, dict):
            continue
        for item in record.get("add") or []:
            if isinstance(item, dict) and item.get("id"):
                added.append({"id": item["id"], "text": item.get("text")})
        for item in record.get("update") or []:
            if isinstance(item, dict) and item.get("id"):
                updated.append({
                    "id": item["id"],
                    "text": item.get("text"),
                    "archived_id": item.get("archived_id"),
                })

    n_added, n_updated = len(added), len(updated)
    if n_added or n_updated:
        message = f"Feedback recorded: {n_added} added, {n_updated} updated"
    else:
        message = "Feedback recorded, but no memory was changed"

    summary = {
        "status": "success",
        "message": message,
        "added": added[:_FEEDBACK_ITEM_LIMIT],
        "updated": updated[:_FEEDBACK_ITEM_LIMIT],
    }
    if n_added > _FEEDBACK_ITEM_LIMIT or n_updated > _FEEDBACK_ITEM_LIMIT:
        summary["truncated"] = True
    return summary


class MemoryService:
    def __init__(self, client: ProductClient, settings: Settings):
        self._client = client
        self._query_prefix = settings.query_prefix

    def add_message(
        self,
        caller: Caller,
        conversation_first_message: str,
        messages: list[dict],
        tags: list[str] | None = None,
    ) -> str:
        payload = {
            "user_id": caller.user_id,
            "mem_cube_id": caller.cube_id,
            "session_id": session_id_from_first_message(conversation_first_message),
            "messages": _normalize_messages(messages),
            "async_mode": "sync",
        }
        if tags:
            payload["custom_tags"] = list(tags)
        # 本部署会先用 LLM 把内容改写后再入库，读回来的是改写稿而非原文。
        self._client.add(payload)
        return dump_json({"status": "success", "message": "Memory added successfully"})

    def search_memory(
        self,
        caller: Caller,
        query: str,
        filter: dict | None = None,
        top_k: int = 10,
        conversation_first_message: str | None = None,
    ) -> str:
        top_k = _clamp(top_k, default=10, lo=1, hi=50)
        payload = {
            "user_id": caller.user_id,
            "query": (self._query_prefix + query) if self._query_prefix else query,
            "mem_cube_id": caller.cube_id,
            "top_k": top_k,
        }
        if filter:
            payload["filter"] = filter
        if conversation_first_message:
            payload["session_id"] = session_id_from_first_message(conversation_first_message)
        data = self._client.search(payload)
        return dump_json(cloud_lists(data, top_k=top_k))

    def delete_memory(self, caller: Caller, memory_ids: list[str]) -> str:
        ids = [m for m in (memory_ids or []) if m]
        if not ids:
            raise MemoryServiceError("memory_ids 至少需要一个 id")

        # ⚠️ 归属校验：本部署的 /product/delete_memory 只认 memory_ids，不校验 owner。
        # 整批失败（fail-closed），避免出现「删了一半」。
        mine, foreign, missing = [], [], []
        for mid in ids:
            owner = self._client.owner_of(mid)
            if owner is None:
                missing.append(mid)
            elif owner != caller.user_id:
                foreign.append(mid)
            else:
                mine.append(mid)

        if foreign:
            raise MemoryServiceError(
                f"拒绝执行：{len(foreign)} 个 id 不属于当前调用方的记忆空间，未做任何删除。"
            )
        if not mine:
            return dump_json({
                "status": "success",
                "deleted_ids": [],
                "not_found_ids": missing,
                "message": "没有可删除的记忆（id 不存在或已删除）",
            })

        self._client.delete(mine)
        result = {
            "status": "success",
            "deleted_ids": mine,
            "message": "Memories deleted successfully",
        }
        if missing:
            result["not_found_ids"] = missing
        return dump_json(result)

    def add_feedback(
        self,
        caller: Caller,
        feedback_content: str,
        conversation_first_message: str = "",
        retrieved_memory_ids: list[str] | None = None,
    ) -> str:
        payload = {
            "user_id": caller.user_id,
            "history": [{"role": "user", "content": feedback_content}],
            "feedback_content": feedback_content,
            "async_mode": "sync",
        }
        if retrieved_memory_ids:
            payload["retrieved_memory_ids"] = list(retrieved_memory_ids)
        if conversation_first_message:
            payload["session_id"] = session_id_from_first_message(conversation_first_message)
        # 后端的 record 是这次纠错改了哪几条的唯一证据，必须带回给调用方（以前整个丢掉）。
        return dump_json(_feedback_summary(self._client.feedback(payload)))

    def get_user_profile(
        self,
        caller: Caller,
        include_preference: bool = True,
        include_tool_memory: bool = False,
        current: int = 1,
        size: int = 20,
    ) -> str:
        size = _clamp(size, default=20, lo=1, hi=50)
        current = _clamp(current, default=1, lo=1, hi=10**9)
        data = self._client.get_memory({
            "mem_cube_id": caller.cube_id,
            "user_id": caller.user_id,
            "page": current,
            "page_size": size,
        })
        body = cloud_lists(
            data,
            include_preference=include_preference,
            include_tool_memory=include_tool_memory,
        )
        body.update({"current": current, "size": size, "total": total_nodes(data)})
        return dump_json(body)

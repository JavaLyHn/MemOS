"""把本部署 REST 返回摊平成云版 MCP 字段。"""

from __future__ import annotations

import json
from typing import Any


def metadata_of(item: dict) -> dict:
    return item.get("metadata") or {}


def is_deleted(item: dict) -> bool:
    return metadata_of(item).get("status") == "deleted"


def flatten_buckets(data: Any) -> dict[str, list[dict]]:
    """把 {'text_mem': [{'cube_id':…,'memories':[…]}, …], 'pref_mem': […]}
    摊平成 {'text_mem': [记录, …], 'pref_mem': [记录, …]}。"""
    out: dict[str, list[dict]] = {}
    if not isinstance(data, dict):
        return out
    for bucket, groups in data.items():
        if not isinstance(groups, list):
            continue
        rows: list[dict] = []
        for group in groups:
            if isinstance(group, dict):
                rows.extend(m for m in (group.get("memories") or []) if isinstance(m, dict))
        out[bucket] = rows
    return out


def relativity(item: dict) -> float:
    value = metadata_of(item).get("relativity")
    return round(float(value), 4) if isinstance(value, (int, float)) else 0.0


def live_sorted(rows: list[dict], top_k: int | None = None) -> list[dict]:
    """去掉软删除记录 → 按 id 去重 → 按 relativity 降序排 → 可选截断。

    去重是必要的：后端 /product/get_memory 会把**同一条记录返回多次**
    （实测同一 id 连续出现两遍，total_nodes 也跟着翻倍）。原样透传会让
    get_user_profile 看起来像存了两份，所以在这里按 id 收敛。
    """
    live: list[dict] = []
    seen: set[str] = set()
    for item in rows:
        if is_deleted(item):
            continue
        key = item.get("id") or id(item)
        if key in seen:
            continue
        seen.add(key)
        live.append(item)
    live.sort(key=relativity, reverse=True)
    return live[:top_k] if top_k else live


def as_fact(item: dict) -> dict:
    md = metadata_of(item)
    return {
        "memory_key": md.get("key"),
        "memory_value": item.get("memory"),
        "relativity": relativity(item),
        "create_time": md.get("created_at"),
        "tags": md.get("tags"),
        "memory_id": item.get("id"),
    }


def as_preference(item: dict) -> dict:
    md = metadata_of(item)
    return {
        "preference": item.get("memory"),
        "preference_type": md.get("type"),
        "relativity": relativity(item),
        "create_time": md.get("created_at"),
        "memory_id": item.get("id"),
    }


def as_tool_memory(item: dict) -> dict:
    md = metadata_of(item)
    return {
        "tool_value": item.get("memory"),
        "relativity": relativity(item),
        "create_time": md.get("created_at"),
        "memory_id": item.get("id"),
    }


def drop_none(obj):
    """递归去掉 dict 里的 None，保持输出紧凑。list 里的 None 原样保留。"""
    if isinstance(obj, dict):
        return {k: drop_none(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [drop_none(v) for v in obj]
    return obj


def dump_json(obj) -> str:
    return json.dumps(drop_none(obj), ensure_ascii=False, indent=1)


def cloud_lists(
    data,
    *,
    include_preference: bool = True,
    include_tool_memory: bool = True,
    top_k: int | None = None,
) -> dict:
    grouped = flatten_buckets(data)
    facts = [as_fact(m) for m in live_sorted(grouped.get("text_mem", []))]
    prefs = [as_preference(m) for m in live_sorted(grouped.get("pref_mem", []))] if include_preference else []
    tools = [as_tool_memory(m) for m in live_sorted(grouped.get("tool_mem", []))] if include_tool_memory else []
    if top_k is not None:
        for group in (facts, prefs, tools):
            group.sort(key=lambda x: x["relativity"], reverse=True)
        facts, prefs, tools = facts[:top_k], prefs[:top_k], tools[:top_k]
    return {
        "memory_detail_list": facts,
        "preference_detail_list": prefs,
        "tool_memory_detail_list": tools,
    }


def total_nodes(data) -> int | None:
    total = None
    if not isinstance(data, dict):
        return None
    for groups in data.values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if isinstance(group, dict) and group.get("total_nodes") is not None:
                total = (total or 0) + int(group["total_nodes"])
    return total

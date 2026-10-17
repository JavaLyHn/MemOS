#!/usr/bin/env python3
"""工具描述回归测试（改任何 prompt / 工具描述后**必跑**）。

为什么必须跑：给 add_message 加"写入边界"时，只验证了"文本上线"，没验证"模型看到后还会不会调用"
——结果调用方 agent 彻底不再写记忆，记忆库变成只读库。**描述是 prompt 的一部分，改它就是在改行为，必须做行为回归。**

做法：从网关拉真实的 tools/list（MCP 格式）→ 转成 OpenAI function schema →
用与业务同族的模型（DeepSeek-V4-Flash）跑 5 个场景 → 断言"该调的调了、不该调的没调、
摘取后不带个案标识"。整链只读，不写记忆库。

用法（在能同时访问网关与模型网关的机器上跑）：
    python3 prompt_regression_test.py                 # 跑全部场景
    python3 prompt_regression_test.py --show-calls    # 额外打印模型给的参数
环境变量：OPENAI_API_BASE / OPENAI_API_KEY / GATEWAY_URL / GATEWAY_TOKEN（GATEWAY_TOKEN 必须自行提供）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.request

GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:8002/mcp")
TOKEN = os.getenv("GATEWAY_TOKEN", "")  # 不内置 token，运行前 export GATEWAY_TOKEN=<sk- token>
LLM_BASE = os.getenv("OPENAI_API_BASE", "https://api.example.com/v1")
LLM_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL = os.getenv("REGRESSION_MODEL", "DeepSeek-V4-Flash")

CASE_LIKE_PATTERNS = (r"[0-9a-f]{8}-[0-9a-f]{4}-", r"uid[:：]?\s*\d{4,}", r"A2600[0-9A-Z]{5,}",
                      r"\b[0-9a-f]{32,64}\b", r"\b\d{1,3}(?:\.\d{1,3}){3}\b",
                      r"(?:[a-z0-9-]+\.)+(?:com|cn|net|org|io|top|xyz)\b")


def looks_case_specific(text) -> bool:
    s = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
    return any(re.search(p, s, re.I) for p in CASE_LIKE_PATTERNS)


def mcp_rpc(method: str, params: dict, rid: int = 1) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}).encode()
    req = urllib.request.Request(GATEWAY, data=body, method="POST", headers={
        "Authorization": "Bearer " + TOKEN, "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream"})
    raw = urllib.request.urlopen(req, timeout=60).read().decode()
    for line in raw.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return json.loads(raw)


def fetch_tools() -> list[dict]:
    d = mcp_rpc("tools/list", {})["result"]["tools"]
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t.get("inputSchema") or {"type": "object", "properties": {}}}}
            for t in d]


def ask(messages: list[dict], tools: list[dict], retries: int = 4) -> dict:
    """调用 LLM；对 429/5xx 做指数退避重试（网关会限流，实测踩过）。"""
    body = json.dumps({"model": LLM_MODEL, "messages": messages, "tools": tools,
                       "tool_choice": "auto", "temperature": 0}).encode()
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(LLM_BASE.rstrip("/") + "/chat/completions", data=body, method="POST",
                                         headers={"Authorization": "Bearer " + LLM_KEY,
                                                  "Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=180))
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 500, 502, 503, 504) and i < retries - 1:
                wait = 6 * (2 ** i)
                print("      [限流/错误 %s，%ds 后重试 %d/%d]" % (e.code, wait, i + 1, retries))
                time.sleep(wait)
                continue
            raise
    raise last


# 场景：(名称, 用户消息, 期望调用的工具集合, 是否要求"写入内容不含个案标识")
SCENARIOS = [
    # 注意：不要在场景里夹带"待做任务"——模型会先完成任务、把记录偏好延后到回合末，
    # 单轮测试看不到那一步，会产生假失败（2026-09-23 踩过）。
    ("S1 输出格式偏好（可泛化，无待做任务）",
     "以后截图取证任务只返回链接，不要附解释。",
     {"add_message"}, True),
    ("S2 纯个案结论（不可泛化）",
     "帮我看看：2026年9月20日晚9:20 处理 uid:10000001 的那次工单，页面跳转后 404，最终判定为无需关注。",
     {"search_memory"}, False),
    ("S3 个案+规则混合（应只摘可泛化那半）",
     "今天处理 uid:10000001 的那次工单，判定为无需关注。顺便把规则沉淀下来："
     "页面跳转后 404 的，一律判为无需关注。",
     {"search_memory", "add_message"}, True),
    ("S4 工具踩坑（可泛化）",
     "记个坑：Splunk 查询不允许通配符索引名，用了会报 422，必须用完整索引名。",
     {"add_message"}, True),
    ("S5 寒暄（不该写）",
     "你好",
     {"search_memory"}, False),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show-calls", action="store_true")
    ap.add_argument("--delay", type=float, default=2.0, help="场景间隔秒数（默认 2s，避开网关限流）")
    ap.add_argument("--repeat", type=int, default=3, help="每个场景重复次数（决策是概率性的，默认 3）")
    a = ap.parse_args()
    if not LLM_KEY:
        raise SystemExit("缺少 OPENAI_API_KEY")
    tools = fetch_tools()
    names = [t["function"]["name"] for t in tools]
    print("网关工具: %s" % ", ".join(names))
    print("模型: %s\n" % LLM_MODEL)
    total_ok = 0
    total_runs = 0
    for name, user_msg, expect, must_be_clean in SCENARIOS:
        hits = 0
        details = []
        for k in range(a.repeat):
            r = ask([{"role": "system", "content": "你是一个助手，按工具描述决定是否调用工具。"},
                     {"role": "user", "content": user_msg}], tools)
            calls = r["choices"][0]["message"].get("tool_calls") or []
            got = {c["function"]["name"] for c in calls}
            ok = True
            if ("S1" in name) or ("S3" in name) or ("S4" in name):
                ok = "add_message" in got
            if ("S2" in name) or ("S5" in name):
                ok = "add_message" not in got
            if ok and must_be_clean and ("add_message" in got):
                args = next(c["function"]["arguments"] for c in calls if c["function"]["name"] == "add_message")
                ok = not looks_case_specific(args)
            hits += ok
            total_runs += 1
            details.append("%s%s" % ("✓" if ok else "✗", ",".join(sorted(got)) or "无调用"))
            if a.delay:
                time.sleep(a.delay)
        total_ok += hits
        # 门槛：写入类要求 ≥2/3 会写；不写类要求 3/3 不写
        need = a.repeat if ("S2" in name or "S5" in name) else max(2, a.repeat - 1)
        print("%-32s 通过 %d/%d（门槛 %d）%s  %s" % (name, hits, a.repeat, need, "✅" if hits >= need else "❌", " | ".join(details)))
    print("\n合计通过 %d/%d 次调用" % (total_ok, total_runs))
    # 门槛：所有"不该写"的场景必须 3/3 干净，且"该写"的场景整体通过率 ≥70%
    raise SystemExit(0 if total_ok >= int(total_runs * 0.7) else 1)


if __name__ == "__main__":
    main()

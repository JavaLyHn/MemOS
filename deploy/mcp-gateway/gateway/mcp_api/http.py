"""运维侧 HTTP 端点（不属于 MCP 协议）。

加这两个是为了「用浏览器打开时不要看到一堆报错」——直接访问 /mcp 是浏览器做不到的
（MCP 要求 POST + text/event-stream），而且会在日志里留下 ClosedResourceError 堆栈，
看着像故障其实是正常的协议拒绝。给人一个能看的页面。
"""

from __future__ import annotations

import time

from starlette.responses import HTMLResponse, JSONResponse

from ..config import Settings
from ..domain.tenants import TenantRegistry

_LANDING_CSS = """
:root{--bg:#fbfbfa;--fg:#1f2430;--muted:#6b7280;--line:#e3e5e9;--accent:#0f7a6c;--code:#f3f4f6}
*{box-sizing:border-box}
body{margin:0;padding:48px 24px;background:var(--bg);color:var(--fg);
 font:15px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB",sans-serif}
main{max-width:820px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px;letter-spacing:.2px}
.sub{color:var(--muted);margin:0 0 32px;font-size:14px}
.pill{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12.5px;
 background:#e6f3f0;color:#0b5a50;border:1px solid #b6ddd6;vertical-align:middle;margin-left:8px}
h2{font-size:13px;text-transform:uppercase;letter-spacing:1.2px;color:var(--muted);
 margin:34px 0 12px;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:14px}
td,th{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:500;width:180px}
code,pre{font-family:"SF Mono",Menlo,Consolas,monospace}
code{background:var(--code);padding:1.5px 5px;border-radius:4px;font-size:13px}
pre{background:var(--code);padding:14px 16px;border-radius:8px;overflow-x:auto;font-size:13px;margin:0}
.note{color:var(--muted);font-size:13.5px;margin-top:10px}
a{color:var(--accent)}
"""

_BARE_HEADERS = {
    "trigger:", "purpose:", "strict rules:", "parameters:", "notes:",
    "returns:", "rule:", "usage requirements:",
}


def first_line(text: str | None) -> str:
    """从工具描述里取一句做简介。

    描述是按 "Trigger: / Purpose: / STRICT RULES:" 分段的，直接取第一行会得到
    一个光秃秃的 "Trigger:"，所以要跳过这类纯标题行。
    """
    for raw in (text or "").splitlines():
        line = raw.strip().lstrip("-•*0123456789. ").replace("*", "").replace("`", "").strip()
        if not line or line.lower() in _BARE_HEADERS:
            continue
        if line.endswith(":") and len(line) < 20:
            continue
        for head in ("Trigger:", "Purpose:", "Rule:", "Notes:"):
            if line.startswith(head):
                line = line[len(head):].strip()
        if line:
            return line[:110]
    return "—"


def format_uptime(started_at: float, now: float | None = None) -> str:
    total = int((now if now is not None else time.time()) - started_at)
    h, remaining = divmod(total, 3600)
    m, s = divmod(remaining, 60)
    return f"{h} 小时 {m} 分" if h else (f"{m} 分 {s} 秒" if m else f"{s} 秒")


class PublicPages:
    def __init__(self, settings: Settings, tenants: TenantRegistry, mcp):
        self._settings = settings
        self._tenants = tenants
        self._mcp = mcp

    async def health(self, request):  # noqa: ARG001
        """给探针/监控用的机器可读健康检查（无需鉴权，不含任何敏感信息）。"""
        return JSONResponse({
            "status": "healthy",
            "service": self._settings.service_name,
            "tools": len(await self._mcp.get_tools()),
            "tenants": len(self._tenants),
            "uptime_seconds": int(time.time() - self._settings.started_at),
        })

    async def landing(self, request):
        """人看的落地页：服务状态 + 工具清单 + 怎么接。"""
        host = request.headers.get("host", "")
        try:
            tools = sorted((await self._mcp.get_tools()).values(), key=lambda t: t.name)
            tool_count = len(tools)
            rows = "\n".join(
                f"<tr><td><code>{t.name}</code></td><td>{first_line(t.description)}</td></tr>"
                for t in tools
            )
        except Exception:
            tool_count = 0
            rows = "<tr><td colspan=2>工具清单暂时不可用</td></tr>"

        html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>长期记忆服务</title><style>{_LANDING_CSS}</style></head><body><main>
<h1>长期记忆服务<span class="pill">运行中</span></h1>
<p class="sub">给 Agent 提供跨会话的长期记忆：回答前检索、回答后沉淀。</p>

<h2>接入信息</h2>
<table>
<tr><th>MCP 地址</th><td><code>http://{host}/mcp</code></td></tr>
<tr><th>鉴权</th><td><code>Authorization: Bearer &lt;你的 token&gt;</code></td></tr>
<tr><th>传输方式</th><td>Streamable HTTP（需要客户端支持）</td></tr>
<tr><th>已配空间</th><td>{len(self._tenants)} 个</td></tr>
<tr><th>已运行</th><td>{format_uptime(self._settings.started_at)}</td></tr>
</table>
<p class="note">在 MCP 客户端里填上面的地址与 Authorization 头即可接入。</p>

<h2>提供的工具（{tool_count} 个）</h2>
<table>{rows}</table>
<p class="note">本页只用于查看状态，不能在这里调用工具。请用你的 MCP 客户端连接上面的地址。</p>
</main></body></html>"""
        return HTMLResponse(html)

    def register(self, mcp) -> None:
        mcp.custom_route("/health", methods=["GET"])(self.health)
        mcp.custom_route("/", methods=["GET"])(self.landing)

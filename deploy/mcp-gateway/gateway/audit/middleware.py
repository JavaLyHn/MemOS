"""HTTP 层 + MCP 协议层审计中间件。"""

from __future__ import annotations

import time

from fastmcp.server.middleware import Middleware as McpMiddleware

from ..domain.tenants import TenantRegistry, mask_token
from .extract import rpc_tool_name, session_id_from_message
from .sink import JsonlSink


class AuditHTTPMiddleware:
    """HTTP 层审计：纯 ASGI，不读请求体、不缓冲响应体。

    刻意不读 body：/mcp 上有流式响应（GET 是 SSE 长连接），一旦在中间件里
    缓冲就可能把它弄坏。所以这里只记「请求行 + 响应头」，协议层的细节交给
    AuditRpcMiddleware。

    在**响应头发出时**就记一行，而不是等响应结束：否则 GET /mcp 这种长连接
    要等断开才有记录，运维侧看不到「此刻谁连着」。
    """

    def __init__(self, app, *, sink: JsonlSink, tenants: TenantRegistry):
        self.app = app
        self._sink = sink
        self._tenants = tenants

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        started = time.time()
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in (scope.get("headers") or [])
        }
        auth = headers.get("authorization", "")
        token = auth[7:].strip() if auth[:7].lower() == "bearer " else None
        client = scope.get("client") or (None, None)
        logged_once = False

        async def send_and_log(message):
            nonlocal logged_once
            if message["type"] == "http.response.start" and not logged_once:
                logged_once = True
                self._sink.write({
                    "kind": "http",
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": message["status"],
                    "ms": int((time.time() - started) * 1000),
                    "tenant": self._tenants.user_id_of(token),
                    "token": mask_token(token),
                    "ip": client[0],
                    "port": client[1],
                    "ua": headers.get("user-agent"),
                })
            await send(message)

        await self.app(scope, receive, send_and_log)


class AuditRpcMiddleware(McpMiddleware):
    """MCP 协议层审计：记每条 JSON-RPC 消息的方法名。

    HTTP 层只知道「有人 POST /mcp」，协议层才知道他在干什么。
    鉴权失败（401）走不到这一层，由 AuditHTTPMiddleware 覆盖。
    """

    def __init__(self, *, sink: JsonlSink, peek_tenant):
        super().__init__()
        self._sink = sink
        self._peek_tenant = peek_tenant

    async def _audited(self, context, call_next):
        started = time.time()
        ok, err = True, None
        try:
            return await call_next(context)
        except Exception as exc:
            ok, err = False, type(exc).__name__
            raise
        finally:
            try:
                self._sink.write({
                    "kind": "rpc",
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "rpc": getattr(context, "method", None),
                    "tool": rpc_tool_name(context.message),
                    "tenant": self._peek_tenant(),
                    "session_id": session_id_from_message(context.message),
                    "ms": int((time.time() - started) * 1000),
                    "ok": ok,
                    "err": err,
                })
            except Exception:  # noqa: BLE001 - 审计是旁路
                pass

    async def on_message(self, context, call_next):
        return await self._audited(context, call_next)

    async def on_notification(self, context, call_next):
        """通知类消息的钩子。

        ⚠️ 实测（2026-09-20）：当前 stateless_http=True 下，通知被 Streamable HTTP
        直接以 202 应答、不进入协议处理链，所以 on_message / on_notification 都
        **不会触发**。这类消息在审计里只能靠 HTTP 层的 ``"status": 202`` 认出来。
        这里保留钩子：一旦将来改回有状态模式，它就能记到。
        """
        return await self._audited(context, call_next)

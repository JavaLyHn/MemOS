"""组装审计用的 sink / 装饰器 / 中间件。"""

from __future__ import annotations

from starlette.middleware import Middleware as ASGIMiddleware

from ..config import Settings
from ..domain.tenants import TenantRegistry
from ..identity import IdentityResolver
from .middleware import AuditHTTPMiddleware, AuditRpcMiddleware
from .sink import JsonlSink
from .tool_log import ToolLogger


class Auditor:
    def __init__(self, settings: Settings, tenants: TenantRegistry, identity: IdentityResolver):
        call_dir = settings.call_log_dir
        audit_dir = settings.audit_log_dir
        self.calls = JsonlSink(call_dir, "calls", stdout_tag="call")
        self.searches = JsonlSink(call_dir, "searches")
        self.requests = JsonlSink(audit_dir, "requests", stdout_tag="req")
        self.tool_logger = ToolLogger(
            calls=self.calls,
            searches=self.searches,
            peek_tenant=identity.peek_user_id,
        )
        self.rpc_middleware = AuditRpcMiddleware(
            sink=self.requests,
            peek_tenant=identity.peek_user_id,
        )
        self._tenants = tenants

    def http_middleware(self):
        tenants = self._tenants
        sink = self.requests

        def factory(app):
            return AuditHTTPMiddleware(app, sink=sink, tenants=tenants)

        return ASGIMiddleware(factory)

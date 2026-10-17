"""组装整网关：配置 → 租户 → 后端 → 记忆服务 → 审计 → FastMCP。"""

from __future__ import annotations

from dataclasses import dataclass

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

from .audit.facade import Auditor
from .backend import ProductClient
from .config import Settings, settings as default_settings
from .domain.tenants import TenantRegistry
from .identity import IdentityResolver
from .mcp_api.http import PublicPages
from .mcp_api.tools import register as register_tools
from .service import MemoryService

INSTRUCTIONS = (
    "长期记忆服务。回答用户前先调用 search_memory 检索相关记忆；"
    "用户明确要求记住某事时调用 add_message。"
    "写入只沉淀可泛化的口径/规则/流程/偏好，个案判定结论与过程流水不要写入；"
    "检索到的历史结论仅作背景参考，不得作为本轮判定的依据（判定须基于实时数据独立得出）。"
)


@dataclass
class App:
    settings: Settings
    tenants: TenantRegistry
    identity: IdentityResolver
    memory: MemoryService
    auditor: Auditor
    mcp: FastMCP

    def http_middleware(self):
        return self.auditor.http_middleware()


def build_app(settings: Settings | None = None) -> App:
    settings = settings or default_settings
    tenants = TenantRegistry.from_raw(settings.tenants_raw)
    identity = IdentityResolver(settings)
    memory = MemoryService(ProductClient(settings), settings)
    auditor = Auditor(settings, tenants, identity)

    verifier = (
        StaticTokenVerifier(tokens=tenants.verifier_tokens())
        if tenants
        else None
    )
    mcp = FastMCP(
        name=settings.service_name,
        instructions=INSTRUCTIONS,
        auth=verifier,
        stateless_http=True,
    )
    mcp.add_middleware(auditor.rpc_middleware)
    register_tools(mcp, auditor.tool_logger, memory, identity)
    PublicPages(settings, tenants, mcp).register(mcp)
    return App(
        settings=settings,
        tenants=tenants,
        identity=identity,
        memory=memory,
        auditor=auditor,
        mcp=mcp,
    )


def build_mcp() -> FastMCP:
    return build_app().mcp

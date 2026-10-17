#!/usr/bin/env python3
"""MCP 网关入口。实现在 ``gateway/`` 包里，本文件只负责启动。

    python3 memos_gateway.py                     # Streamable HTTP（默认）
    python3 memos_gateway.py --transport stdio   # 本地 stdio 调试
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许 ``python3 memos_gateway.py`` 直接跑：把本文件所在目录加入 sys.path，
# 这样 ``import gateway`` 在 ConfigMap 挂载到 /opt/memos-mcp 时也能找到。
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from gateway.app import build_app

app = build_app()
mcp = app.mcp


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Memory MCP Gateway")
    parser.add_argument("--transport", choices=["http", "stdio"], default="http")
    parser.add_argument("--host", default=app.settings.host)
    parser.add_argument("--port", type=int, default=app.settings.port)
    args = parser.parse_args()

    if not app.tenants:
        raise SystemExit(
            "MEMOS_TENANTS 未配置：请设置 token -> user_id 映射，"
            "例如 MEMOS_TENANTS='tok-alice:alice,tok-b:bob'"
        )

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        # middleware 必须在这里挂到 ASGI 层：鉴权失败（401）由 /mcp 路由上的
        # RequireAuthMiddleware 直接返回，走不到 MCP 协议层，只有 ASGI 层能看到。
        mcp.run(
            transport="http",
            host=args.host,
            port=args.port,
            middleware=[app.http_middleware()],
        )

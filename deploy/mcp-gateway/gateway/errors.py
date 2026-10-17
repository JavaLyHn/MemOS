"""网关对外抛给 MCP 调用方的错误。"""

from __future__ import annotations


class MemoryServiceError(RuntimeError):
    """后端拒绝请求，或网关无法确定调用方身份。"""

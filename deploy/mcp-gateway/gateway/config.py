"""进程配置。只从环境变量读一次，其它层拿 ``settings`` 而不是自己 getenv。"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    service_name: str
    api_base: str
    timeout: int
    host: str
    port: int
    allowed_cubes: frozenset[str]
    call_log_dir: str
    audit_log_dir: str
    query_prefix: str
    tenants_raw: str
    started_at: float

    @classmethod
    def from_env(cls) -> Settings:
        call_log_dir = os.getenv("MEMORY_CALL_LOG_DIR", "/var/log/memos-gateway")
        cubes = {c.strip() for c in os.getenv("MEMOS_ALLOWED_CUBES", "").split(",") if c.strip()}
        return cls(
            # 对客户端展示的服务名。⚠️ 不要带任何上游技术来源字样。
            service_name=os.getenv("MEMORY_SERVICE_NAME", "MemoryService"),
            api_base=os.getenv("MEMOS_API_BASE_URL", "http://localhost:8000").rstrip("/"),
            # 默认 120s：/product/add 在入库前会先过一遍 LLM 改写，慢的时候远超 60s。
            timeout=int(os.getenv("MEMOS_TIMEOUT", "120")),
            host=os.getenv("MEMOS_HOST", "0.0.0.0"),
            port=int(os.getenv("MEMOS_PORT", "8002")),
            allowed_cubes=frozenset(cubes),
            call_log_dir=call_log_dir,
            audit_log_dir=os.getenv("MEMORY_AUDIT_LOG_DIR", call_log_dir),
            query_prefix=os.getenv("MEMORY_QUERY_PREFIX", ""),
            tenants_raw=os.getenv("MEMOS_TENANTS", ""),
            started_at=time.time(),
        )


settings = Settings.from_env()

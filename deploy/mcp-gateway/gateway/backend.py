"""调用后端 REST，并消化本部署的已知坑。"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .config import Settings
from .errors import MemoryServiceError
from .log import logger


class ProductClient:
    def __init__(self, settings: Settings):
        self._base = settings.api_base
        self._timeout = settings.timeout

    def request(
        self,
        path: str,
        payload: Any = None,
        *,
        method: str = "POST",
        params: dict | None = None,
        timeout: int | None = None,
    ):
        """调用后端 REST 并返回其 data 段。"""
        url = f"{self._base}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"},
            method=method,
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout or self._timeout) as resp:
                body = json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            try:
                body = json.loads(raw)
            except ValueError:
                raise MemoryServiceError(f"后端返回 HTTP {e.code}: {raw[:300]}") from None
        except urllib.error.URLError as e:
            # 不要把后端地址写进错误（那会泄露内网主机名），细节留给服务端日志
            logger.warning("backend unreachable: %s (%s)", self._base, e.reason)
            raise MemoryServiceError("暂时连不上记忆服务，请稍后重试。") from None

        if isinstance(body, dict):
            code = body.get("code")
            if code not in (None, 200):
                raise MemoryServiceError(f"后端错误 {code}: {body.get('message')}")
            data = body.get("data")
            # 部分路由失败时仍返回 HTTP 200，只把 data.status 置成 "failure"
            # （delete_memory 就是），必须显式识别，否则删除会「假装成功」。
            if isinstance(data, dict) and data.get("status") == "failure":
                raise MemoryServiceError(f"后端拒绝了该请求: {body.get('message')}")
            if "data" in body:
                return data
        return body

    def add(self, payload: dict):
        return self.request("/product/add", payload)

    def search(self, payload: dict):
        return self.request("/product/search", payload)

    def delete(self, memory_ids: list[str]):
        # 只能传 memory_ids：带上 user_id 会被判成「两个删除模式」而静默失败。
        return self.request("/product/delete_memory", {"memory_ids": memory_ids})

    def feedback(self, payload: dict):
        return self.request("/product/feedback", payload)

    def get_memory(self, payload: dict):
        return self.request("/product/get_memory", payload)

    def get_memory_by_id(self, memory_id: str):
        return self.request(
            f"/product/get_memory/{urllib.parse.quote(memory_id)}",
            method="GET",
        )

    def owner_of(self, memory_id: str) -> str | None:
        """查一条记忆归属哪个 user_id。

        返回 None 表示查不到（id 不存在，或该记录已被软删除 —— 本部署对已删除记录
        的单条 GET 会返回 data: null）。
        """
        data = self.get_memory_by_id(memory_id)
        if isinstance(data, dict):
            return (data.get("metadata") or {}).get("user_id")
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return (data[0].get("metadata") or {}).get("user_id")
        return None

"""工具调用埋点。签名原样透传（FastMCP 靠 inspect.signature 生成 schema）。"""

from __future__ import annotations

import functools
import inspect
import time

from ..log import logger
from .extract import args_for_audit, case_like_from_args, clip, search_hits, session_id_from_args
from .sink import JsonlSink


class ToolLogger:
    def __init__(self, *, calls: JsonlSink, searches: JsonlSink, peek_tenant):
        self._calls = calls
        self._searches = searches
        self._peek_tenant = peek_tenant

    def wrap(self, fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            started = time.time()
            out = None
            try:
                tenant = self._peek_tenant()
            except Exception:  # noqa: BLE001 - 身份异常由工具函数自己抛
                tenant = None
            ok, err, size = True, None, None
            try:
                out = fn(*args, **kwargs)
                size = len(out) if isinstance(out, str) else None
                return out
            except Exception as exc:
                ok, err = False, type(exc).__name__
                raise
            finally:
                ms = int((time.time() - started) * 1000)
                if fn.__name__ == "search_memory" and ok:
                    try:
                        query = kwargs.get("query") if kwargs.get("query") is not None else (
                            args[0] if args else None
                        )
                    except Exception:  # noqa: BLE001
                        query = None
                    try:
                        hits = search_hits(out)
                        self._searches.write({
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                            "tenant": tenant,
                            "query": " ".join(str(query or "").split())[:500],
                            "returned_n": len(hits),
                            "returned": hits,
                            "ms": ms,
                        })
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("search log write failed: %s", exc)
                self._calls.write({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "tool": fn.__name__,
                    "tenant": tenant,
                    "session_id": session_id_from_args(fn, args, kwargs),
                    "case_like": case_like_from_args(fn, args, kwargs),
                    "ms": ms,
                    "ok": ok,
                    "err": err,
                    "result_bytes": size,
                    "input": args_for_audit(fn, args, kwargs),
                    "output": clip(out),
                })

        wrapper.__signature__ = inspect.signature(fn)
        return wrapper

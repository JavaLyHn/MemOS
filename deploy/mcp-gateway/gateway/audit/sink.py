"""按天追加的 JSONL。写失败绝不能影响主路径。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..log import logger


class JsonlSink:
    """只追加、按天分文件。默认信任宿主盘；fsync 保证进程被杀不丢已写入的行。"""

    def __init__(self, directory: str, prefix: str, stdout_tag: str | None = None):
        self._directory = directory
        self._prefix = prefix
        self._stdout_tag = stdout_tag
        self.failures = 0

    def write(self, entry: dict) -> None:
        try:
            os.makedirs(self._directory, exist_ok=True)
            path = Path(self._directory) / f"{self._prefix}-{time.strftime('%Y%m%d')}.jsonl"
            line = json.dumps(entry, ensure_ascii=False) + "\n"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
                fh.flush()
                os.fsync(fh.fileno())
        except Exception as exc:  # noqa: BLE001
            self.failures += 1
            logger.warning(
                "%s log write failed (%s total): %s",
                self._prefix, self.failures, exc,
            )
        if self._stdout_tag:
            try:
                logger.info("[%s] %s", self._stdout_tag, json.dumps(entry, ensure_ascii=False))
            except Exception:  # noqa: BLE001
                pass

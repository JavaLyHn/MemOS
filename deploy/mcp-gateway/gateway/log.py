"""进程级日志器。

必须在任何 ``logger.*`` 调用之前建好 handler：本服务是脚本入口，
没有它会抛 NameError。之前正是因为缺了这一段，审计行 ``[call]``
被写入方自己的 try/except 静默吃掉（表现为「Pod 日志里永远看不到
工具调用」），而 backend 里那句 "backend unreachable" 会在后端真的
挂掉时变成 NameError，盖掉本该返回给使用者的「暂时连不上记忆服务」。
"""

from __future__ import annotations

import logging

logger = logging.getLogger("memory-gateway")
if not logger.handlers:
    _log_handler = logging.StreamHandler()
    _log_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(_log_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # 不往 root 冒泡，避免和 uvicorn/fastmcp 的日志配置打架

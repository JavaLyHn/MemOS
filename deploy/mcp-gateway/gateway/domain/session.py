"""把云版 conversation_first_message 折算成本部署 session_id。"""

from __future__ import annotations

import hashlib


def session_id_from_first_message(first_message: str | None) -> str:
    """本部署的 session_id 是软信号（加权，不做硬过滤），稳定即可。

    同一会话内首条用户消息不变，session_id 就不变。
    """
    text = (first_message or "").strip()
    if not text:
        return ""
    return "conv_" + hashlib.sha1(text.encode()).hexdigest()[:16]

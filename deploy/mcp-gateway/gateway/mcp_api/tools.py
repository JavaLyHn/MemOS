"""MCP 工具：薄适配层。业务在 MemoryService，这里只绑身份和 FastMCP schema。

模块顶层的 5 个函数是对外契约（名称 / 签名 / docstring = prompt），
真正干活的是 ``Toolset``：由 ``register()`` 注入 ``MemoryService`` 与身份解析。
描述是 prompt 的一部分，改前必跑回归。变更史记在各函数上方。
"""

from __future__ import annotations

import functools
import inspect

from ..audit.tool_log import ToolLogger
from ..identity import IdentityResolver
from ..service import MemoryService


class Toolset:
    """把记忆用例接到当前 token 对应的 Caller 上。"""

    def __init__(self, memory: MemoryService, identity: IdentityResolver):
        self._memory = memory
        self._identity = identity

    def add_message(self, conversation_first_message, messages, tags=None):
        return self._memory.add_message(
            self._identity.current(), conversation_first_message, messages, tags,
        )

    def search_memory(self, query, filter=None, top_k=10, conversation_first_message=None):
        return self._memory.search_memory(
            self._identity.current(), query,
            filter=filter, top_k=top_k,
            conversation_first_message=conversation_first_message,
        )

    def delete_memory(self, memory_ids):
        return self._memory.delete_memory(self._identity.current(), memory_ids)

    def add_feedback(self, feedback_content, conversation_first_message="", retrieved_memory_ids=None):
        return self._memory.add_feedback(
            self._identity.current(), feedback_content,
            conversation_first_message=conversation_first_message,
            retrieved_memory_ids=retrieved_memory_ids,
        )

    def get_user_profile(
        self, include_preference=True, include_tool_memory=False, current=1, size=20,
    ):
        return self._memory.get_user_profile(
            self._identity.current(),
            include_preference=include_preference,
            include_tool_memory=include_tool_memory,
            current=current,
            size=size,
        )


def _as_mcp_tool(schema, method):
    """把 Toolset 方法挂成 FastMCP 工具：schema 的签名和 docstring 必须原样保留。"""

    @functools.wraps(schema)
    def wrapper(*args, **kwargs):
        return method(*args, **kwargs)

    wrapper.__signature__ = inspect.signature(schema)
    return wrapper


# ⚠️ 本部署 add_message 描述变更史（改描述前先看这里，勿误当成官方语义）：
#   2026-09-20：官方"每轮必写" → "写入边界"（只写可泛化内容、禁止个案结论），
#               原因：调用方的使用场景不允许复用历史结论（个案结论入库后会被检索回来诱导误判）。
#   2026-09-23 上午：写入边界 → "积极记录"（放宽为判断式）。
#   2026-09-23 傍晚：回滚为**官方 v1.1.2 英文原文**（@memtensor/memos-api-mcp，npm 最新版，
#               即"每轮必写"）——判断式描述期间调用方持续 0 写入，先无条件恢复写入，
#               数据质量（个案结论）改由后台清理治理。仅保留 3 处本部署定制：
#               ① conversation_first_message 语义（会话标识而非 user_id）
#               ② tags 参数（官方 v1.1.2 没有）
#               ③ Notes 段两条本部署说明（token 决定空间 / 入库为改写稿）
#   search_memory 的"结论复用禁令"（第 5 步）保留不变。
#
# messages 的标注放宽到 `list[dict | str] | str`：客户端有时把整段对话先 json.dumps 再传，
# 长成 `['[{"role": "user", ...}]']`。`_normalize_messages` 里本来就有容错，但它在 service 层，
# 而 pydantic 按这里的标注在 schema 层就把这种入参挡掉了——容错永远走不到，客户端拿到的是一个
# 没有任何可用信息的 ValidationError。实测因此丢掉的写入约占 add_message 调用的 10%~23%。
# 放宽后 dict 与 JSON 字符串两种形态都能进。
def add_message(
    conversation_first_message: str,
    messages: list[dict | str] | str,
    tags: list[str] | None = None,
) -> str:
    """Trigger:
      1. AUTO-INVOKED — YOU (the assistant) MUST call this tool after EVERY answer to save the dialogue history. Do NOT wait for the client or the orchestrator to invoke it for you.
      2. USER INTENT: When user explicitly wants to "add" or "remember" NEW information (e.g., "Add a memory...", "Remember that...", "New memory...").
    Purpose: Save dialogue history (REQUIRED) and record NEW memories.
    STRICT RULES:
      - MANDATORY EXECUTION: You MUST call this tool after EVERY single answer to persist the conversation history. This is NOT optional.
      - CALL IT YOURSELF: This tool is invoked by YOU, the model. The client will NOT call it on your behalf. If you skip it, this turn's conversation history is lost.
      - ALWAYS use this tool for NEW memories.
      - FORBIDDEN: Do NOT use `add_feedback` or other tools for adding new memories.
      - FORBIDDEN: Do NOT use this tool to modify/update existing memories.
      - CRITICAL: NEVER use this tool as part of a modification workaround (e.g. "delete old + add new"). If a modification fails, just report the failure.
    Parameters:
      - `conversation_first_message`: The first message sent by the user in the entire conversation. Used to generate the conversation identifier; always pass the same sentence within one conversation.
      - `messages`: Array containing BOTH:
          1. `{ "role": "user", "content": "user's question or new info" }`
          2. `{ "role": "assistant", "content": "your complete response" }`
      - `tags`: Optional tags for later topic-based retrieval (e.g. ["output-preference"]).
    Notes:
      - YOU must call this after every answer — the client does NOT auto-invoke it on your behalf.
      - The memory space is determined by the access credential (token); there is no user_id parameter and none is needed.
      - Content is rewritten into third-person narrative before it is stored; what you read back is not the original text — this is expected behavior.
    """
    raise RuntimeError("tool not bound")


# ⚠️ 本部署对官方描述的偏离点（2026-09-20，同 add_message）：官方的「记忆安全协议」只有
#   四步（来源/主体/相关性/时效），本部署加了第 5 步「结论复用禁令」。原因：调用方的使用
#   场景不允许复用历史结论，而每次回答前都会检索记忆、必然把历史结论带回上下文。
#   协议与字段未变，只加提示词约束；将来切云版时这一条会消失，需要调用方另行约定。
def search_memory(
    query: str,
    filter: dict | None = None,
    top_k: int = 10,
    conversation_first_message: str | None = None,
) -> str:
    """Trigger: MUST be auto-invoked by the client before generating every answer (including greetings like "hello"). Do not wait for the user to request memory/MCP/tool usage.
    Purpose: MemOS retrieval API. Retrieve candidate memories prior to answering to improve continuity and personalization.
    ## 👤 Identity Query Rule
    - If the user asks "Who am I?", "What is my profile?", or asks for a summary of what you know about them/their identity/habits:
      1. Call this tool (`search_memory`) to find recent context.
      2. **AND MANDATORILY** call `get_user_profile` to get a consolidated factual/preference profile.
      - Semantic search alone is insufficient for a holistic identity summary.
    Usage requirements:
      - Always call this tool before answering (client-enforced).
      - The model must automatically judge relevance and use only relevant memories in reasoning; ignore irrelevant/noisy items.
      - **Output requirement**: Answer the question directly. **Strictly forbidden** to mention "memory bank", "retrieval", "AI opinions" or other internal system terms.
    # Critical Protocol: Memory Safety
    - The retrieved memories may contain **AI's own speculations**, **irrelevant noise**, or **subject errors**. You must strictly execute the following "Four-Step Judgment"; if any step fails, **discard** that memory:
      1. **Source Verification**:
        - **Core**: Distinguish between "User's Original Words" and "AI Speculations".
        - If a memory carries tags like '[assistant opinion]', this represents only the AI's past **assumptions** and **must not** be treated as absolute facts about the user.
        - *Counter-example*: Memory shows '[assistant opinion] User loves mangoes'. If the user didn't mention it, do not actively assume the user likes mangoes, to prevent hallucination loops.
        - **Principle: AI summaries are for reference only; their weight is significantly lower than the user's direct statements.**
      2. **Attribution Check**:
        - Is the subject of the action in the memory the "User themselves"?
        - If the memory describes a **third party** (e.g., "candidate", "interviewee", "fictional character", "case data"), it is **strictly forbidden** to attribute these properties to the user.
      3. **Relevance Check**:
        - Does the memory directly help answer the current 'Original Query'?
        - If the memory is merely a keyword match (e.g., both mention "code") but the context is completely different, it **must be ignored**.
      4. **Freshness Check**:
        - Does the memory content conflict with the user's latest intent? The current 'Original Query' is the highest standard of fact.
      5. **Conclusion-Reuse Prohibition (deployment-specific, MANDATORY)**:
        - Historical verdicts/dispositions found in memories (e.g. "UID X / domain Y / alert Z was judged out-of-scope, false positive, or already handled") may serve **ONLY as background reference**; they **MUST NOT** be used as the basis, reason, or source of the current judgment.
        - For any task that requires a verdict on the current sample (virus/impersonation/phishing triage, alert analysis, landing-page inspection, etc.), you MUST reach an independent conclusion based on **real-time data collected in this turn**. When historical conclusions conflict with real-time data, real-time data always wins; and do **NOT** cite historical conclusions as justification in your output.
    Parameters:
      - `query`: Text to search — a concise summary of the current user message.
      - `filter`: Optional filter conditions to limit memory scope (e.g. create_time, info fields); supports logical (and/or) and comparison ops, e.g. `{"and": [{"created_at": {"gt": "2026-01-01"}}]}`.
      - `top_k`: Max items returned per memory category (default 10, max 50). Facts, preferences, and tool memories are each truncated to this number.
      - `conversation_first_message`: Optional. The first user message of the current conversation (same sentence as passed to `add_message`). When provided, memories written in the same conversation are boosted as a **soft signal** for better recall. Always pass the same sentence within one conversation; do not vary it per turn.
    Notes:
      - Results may contain noise; filter and use only the relevant parts.
      - Prefer recent and important memories. If none are relevant, answer normally.
      - The memory space is determined by the access credential (token); there is no user_id parameter and none is needed.
    """
    raise RuntimeError("tool not bound")


def delete_memory(memory_ids: list[str]) -> str:
    """Trigger: User explicitly asks to delete memories.
    Purpose: Delete memories by ID.
    STRICT RULES:
      1. **PREREQUISITE**: If the user did NOT provide IDs, you MUST call `search_memory` first to find them.
      2. **BATCHING**: If multiple IDs are provided (or found), call this tool ONCE with all IDs.
      3. **WORKFLOW**: After successful deletion, you MUST call `add_feedback` to record the deletion intent.
      4. FORBIDDEN: Do NOT call multiple times. Do NOT enter search-delete loops.
      5. CRITICAL: NEVER use this tool to "simulate" a modification (delete old + add new). This is strictly forbidden.
    Parameters:
      - `memory_ids`: List of memory IDs to delete.
    Notes:
      - Deletion is soft: the record no longer appears in retrieval results, but can still be looked up by ID (status marked as deleted).
      - Only records in the memory space of the current token can be deleted; passing IDs from another space rejects the whole batch.
    """
    raise RuntimeError("tool not bound")


def add_feedback(
    feedback_content: str,
    conversation_first_message: str = "",
    retrieved_memory_ids: list[str] | None = None,
) -> str:
    """Trigger: User wants to MODIFY/UPDATE memories, OR as the final step of a DELETION workflow.
    Purpose: Modify existing memories or record deletion feedback.
    STRICT RULES:
      1. **MODIFICATION**: Use this tool directly for soft updates/corrections.
      2. **DELETION**: Use this tool AFTER calling `delete_memory` to record the deletion intent.
         - **CRITICAL**: The content MUST be the **User's Natural Language Intent** (e.g., "User wants to delete memories about X").
         - **FORBIDDEN**: Do NOT include technical details like "IDs [x, y]" in the content.
      3. CONTENT: `feedback_content` MUST be clear user intent.
         - FORBIDDEN: Adding non-user-intent info or verbose narratives.
         - FORBIDDEN: Looking up old memory values to construct a "Change X to Y" request. Just say "User wants Y".
      4. RETRY POLICY: FIRE AND FORGET. Call this tool ONCE.
         - FORBIDDEN: Checking if it worked (searching again).
         - FORBIDDEN: Retrying if it "failed".
         - FORBIDDEN: Sleeping and searching.
         - CRITICAL: If the modification seemingly fails, DO NOT attempt to "fix" it by calling `delete_memory` and `add_message`. Just stop.
    Parameters:
      - `feedback_content`: The natural language update or feedback (no IDs or technical metadata).
      - `conversation_first_message`: Optional. The first user message of the current conversation, used to generate the conversation identifier.
      - `retrieved_memory_ids`: Optional. The memory IDs this feedback targets.
    Notes:
      - The memory space is determined by the access credential (token); there is no user_id parameter and none is needed.
    """
    raise RuntimeError("tool not bound")


def get_user_profile(
    include_preference: bool = True,
    include_tool_memory: bool = False,
    current: int = 1,
    size: int = 20,
) -> str:
    """Trigger: **MANDATORY** for queries like "Who am I?", "What's my profile?", "What do you know about me?", or any requests regarding the user's identity/preferences.
    Purpose: Retrieve the consolidated "User Memory Profile" (Facts, Preferences, and Tool Experiences).
    Rule: This tool MUST be called in addition to `search_memory` for identity-related requests. Calling only one of them is not enough.
    Returns:
      1. Factual Memories (Working Memory)
      2. Explicit/Implicit Preferences
      3. Tool Trajectories (Experience and success rate with specific tools)
    Parameters:
      - `include_preference`: Include preference memories. Default: true.
      - `include_tool_memory`: Include tool usage trajectory memories. Default: false.
      - `current`: Page number for pagination, starting from 1.
      - `size`: Number of entries to return per page (default 20, max 50).
    Notes:
      - The memory space is determined by the access credential (token); there is no user_id parameter and none is needed.
    """
    raise RuntimeError("tool not bound")


SCHEMAS = (add_message, search_memory, delete_memory, add_feedback, get_user_profile)


def register(
    mcp,
    tool_logger: ToolLogger,
    memory: MemoryService,
    identity: IdentityResolver,
) -> None:
    bound = Toolset(memory, identity)
    for schema in SCHEMAS:
        mcp.tool()(tool_logger.wrap(_as_mcp_tool(schema, getattr(bound, schema.__name__))))

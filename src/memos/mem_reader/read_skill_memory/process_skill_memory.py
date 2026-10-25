import copy
import json
import os
import re
import shutil
import uuid
import zipfile

from concurrent.futures import as_completed
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv

from memos.context.context import ContextThreadPoolExecutor
from memos.dependency import require_python_package
from memos.embedders.base import BaseEmbedder
from memos.graph_dbs.base import BaseGraphDB
from memos.llms.base import BaseLLM
from memos.log import get_logger, text_hash
from memos.mem_reader.custom_extract import apply_custom_extract_prompt
from memos.mem_reader.read_multi_modal import detect_lang
from memos.mem_reader.read_skill_memory import skill_store
from memos.memories.textual.item import (
    ArchivedTextualMemory,
    SourceMessage,
    TextualMemoryItem,
    TreeNodeTextualMemoryMetadata,
)
from memos.memories.textual.tree_text_memory.organize import versioning
from memos.memories.textual.tree_text_memory.retrieve.searcher import Searcher
from memos.templates.skill_mem_prompt import (
    OTHERS_GENERATION_PROMPT,
    OTHERS_GENERATION_PROMPT_ZH,
    SCRIPT_GENERATION_PROMPT,
    SKILL_MEMORY_EXTRACTION_PROMPT,
    SKILL_MEMORY_EXTRACTION_PROMPT_MD,
    SKILL_MEMORY_EXTRACTION_PROMPT_MD_ZH,
    SKILL_MEMORY_EXTRACTION_PROMPT_ZH,
    TASK_CHUNKING_PROMPT,
    TASK_CHUNKING_PROMPT_ZH,
    TASK_QUERY_REWRITE_PROMPT,
    TASK_QUERY_REWRITE_PROMPT_ZH,
    TOOL_GENERATION_PROMPT,
)
from memos.types import MessageList
from memos.utils import timed, utc_now_iso


load_dotenv()

if TYPE_CHECKING:
    from memos.types.general_types import UserContext


logger = get_logger(__name__)


def _generate_content_by_llm(llm: BaseLLM, prompt_template: str, **kwargs) -> Any:
    """Generate content using LLM."""
    try:
        prompt = prompt_template.format(**kwargs)
        response = llm.generate([{"role": "user", "content": prompt}])
        if not response:
            logger.warning("[PROCESS_SKILLS] LLM returned empty or invalid response")
            return {} if "json" in prompt_template.lower() else ""
        if "json" in prompt_template.lower():
            response = response.replace("```json", "").replace("```", "").strip()
            return json.loads(response)
        return response.strip()
    except Exception as e:
        logger.warning(f"[PROCESS_SKILLS] LLM generation failed: {e}")
        return {} if "json" in prompt_template.lower() else ""


@timed
def _batch_extract_skills(
    task_chunks: dict[str, MessageList],
    related_memories_map: dict[str, list[TextualMemoryItem]],
    llm: BaseLLM,
    chat_history: MessageList,
) -> list[tuple[dict[str, Any], str, MessageList]]:
    """Phase 1: Batch extract base skill structures from all task chunks in parallel."""
    results = []
    with ContextThreadPoolExecutor(max_workers=min(5, len(task_chunks))) as executor:
        futures = {
            executor.submit(
                _extract_skill_memory_by_llm_md,
                messages=messages,
                old_memories=related_memories_map.get(task_type, []),
                llm=llm,
                chat_history=chat_history,
            ): task_type
            for task_type, messages in task_chunks.items()
        }

        for future in as_completed(futures):
            task_type = futures[future]
            try:
                skill_memory = future.result()
                if skill_memory:
                    skill_memory["_task_type"] = task_type
                    results.append((skill_memory, task_type, task_chunks.get(task_type, [])))
            except Exception as e:
                logger.warning(
                    f"[PROCESS_SKILLS] Error extracting skill memory for task '{task_type}': {e}"
                )
    return results


@timed
def _batch_generate_skill_details(
    raw_skills_data: list[tuple[dict[str, Any], str, MessageList]],
    related_skill_memories_map: dict[str, list[TextualMemoryItem]],
    llm: BaseLLM,
) -> list[dict[str, Any]]:
    """Phase 2: Batch generate details (scripts, tools, others, examples) for all skills in parallel."""
    generation_tasks = []

    # Helper to create task objects
    def create_task(skill_mem, gen_type, prompt, requirements, context, **kwargs):
        return {
            "type": gen_type,
            "skill_memory": skill_mem,
            "func": _generate_content_by_llm,
            "args": (llm, prompt),
            "kwargs": {"requirements": requirements, "context": context, **kwargs},
        }

    # 1. Collect all generation tasks from all skills
    for skill_memory, task_type, messages in raw_skills_data:
        messages_context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])

        # Script
        script_req = copy.deepcopy(skill_memory.get("scripts"))
        if script_req:
            generation_tasks.append(
                create_task(
                    skill_memory, "scripts", SCRIPT_GENERATION_PROMPT, script_req, messages_context
                )
            )
            # TODO Add loop verification after code completion to ensure the generated script meets requirements
        else:
            skill_memory["scripts"] = {}

        # Tool
        tool_req = skill_memory.get("tool")
        if tool_req:
            # Extract available tool schemas from related memories
            tool_memories = [
                memory
                for memory in related_skill_memories_map.get(task_type, [])
                if memory.metadata.memory_type == "ToolSchemaMemory"
            ]
            tool_schemas_list = [memory.memory for memory in tool_memories]

            tool_schemas_str = (
                "\n\n".join(
                    [
                        f"Tool Schema {i + 1}:\n{schema}"
                        for i, schema in enumerate(tool_schemas_list)
                    ]
                )
                if tool_schemas_list
                else "No specific tool schemas available."
            )

            generation_tasks.append(
                create_task(
                    skill_memory,
                    "tool",
                    TOOL_GENERATION_PROMPT,
                    tool_req,
                    messages_context,
                    tool_schemas=tool_schemas_str,
                )
            )
        else:
            skill_memory["tool"] = {}

        lang = detect_lang(messages_context)
        others_req = skill_memory.get("others")
        if others_req and isinstance(others_req, dict):
            for filename, summary in others_req.items():
                generation_tasks.append(
                    {
                        "type": "others",
                        "skill_memory": skill_memory,
                        "key": filename,
                        "func": _generate_content_by_llm,
                        "args": (
                            llm,
                            OTHERS_GENERATION_PROMPT_ZH
                            if lang == "zh"
                            else OTHERS_GENERATION_PROMPT,
                        ),
                        "kwargs": {
                            "filename": filename,
                            "summary": summary,
                            "context": messages_context,
                        },
                    }
                )
        else:
            skill_memory["others"] = {}

    if not generation_tasks:
        return [item[0] for item in raw_skills_data]

    # 2. Execute all tasks in parallel
    with ContextThreadPoolExecutor(max_workers=min(len(generation_tasks), 5)) as executor:
        futures = {
            executor.submit(t["func"], *t["args"], **t["kwargs"]): t for t in generation_tasks
        }

        for future in as_completed(futures):
            task_info = futures[future]
            try:
                result = future.result()
                if not result:
                    continue

                skill_mem = task_info["skill_memory"]

                if task_info["type"] == "scripts":
                    if isinstance(result, dict):
                        # Combine code with script_req
                        try:
                            skill_mem["scripts"] = {
                                filename: f"# {abstract}:\n{code}"
                                for abstract, (filename, code) in zip(
                                    script_req, result.items(), strict=False
                                )
                            }
                        except ValueError:
                            logger.warning(
                                f"[PROCESS_SKILLS] Invalid script generation result: {result}"
                            )
                            skill_mem["scripts"] = {}

                elif task_info["type"] == "tool":
                    skill_mem["tool"] = result

                elif task_info["type"] == "others":
                    if "others" not in skill_mem or not isinstance(skill_mem["others"], dict):
                        skill_mem["others"] = {}
                    skill_mem["others"][task_info["key"]] = (
                        f"# {task_info['kwargs']['summary']}\n{result}"
                    )

            except Exception as e:
                logger.warning(
                    f"[PROCESS_SKILLS] Error in generation task {task_info['type']}: {e}"
                )

    return [item[0] for item in raw_skills_data]


@require_python_package(
    import_name="alibabacloud_oss_v2",
    install_command="pip install alibabacloud-oss-v2",
)
def create_oss_client(oss_config: dict[str, Any] | None = None) -> Any:
    import alibabacloud_oss_v2 as oss

    credentials_provider = oss.credentials.EnvironmentVariableCredentialsProvider()

    # load SDK's default configuration, and set credential provider
    cfg = oss.config.load_default()
    cfg.credentials_provider = credentials_provider
    cfg.region = oss_config.get("region", os.getenv("OSS_REGION"))
    cfg.endpoint = oss_config.get("endpoint", os.getenv("OSS_ENDPOINT"))
    client = oss.Client(cfg)

    return client


def _reconstruct_messages_from_memory_items(memory_items: list[TextualMemoryItem]) -> MessageList:
    reconstructed_messages = []
    seen = set()  # Track (role, content) tuples to detect duplicates

    for memory_item in memory_items:
        for source_message in memory_item.metadata.sources:
            try:
                role = source_message.role
                content = source_message.content

                # Create a tuple for deduplication
                message_key = (role, content)

                # Only add if not seen before (keep first occurrence)
                if message_key not in seen:
                    reconstructed_messages.append({"role": role, "content": content})
                    seen.add(message_key)
            except Exception as e:
                logger.warning(f"[PROCESS_SKILLS] Error reconstructing message: {e}")
                continue

    return reconstructed_messages


def _preprocess_extract_messages(
    history: MessageList, messages: MessageList
) -> (MessageList, MessageList):
    """Process data and check whether to extract skill memory"""
    history = history[-20:]
    if (len(history) + len(messages)) < 10:
        # TODO: maybe directly return []
        logger.info("[PROCESS_SKILLS] Not enough messages to extract skill memory")
    return history, messages


def _add_index_to_message(messages: MessageList) -> MessageList:
    for i, message in enumerate(messages):
        message["idx"] = i
    return messages


def _split_task_chunk_by_llm(llm: BaseLLM, messages: MessageList) -> dict[str, MessageList]:
    """Split messages into task chunks by LLM."""
    messages_context = "\n".join(
        [
            f"{message.get('idx', i)}: {message['role']}: {message['content']}"
            for i, message in enumerate(messages)
        ]
    )
    lang = detect_lang(messages_context)
    template = TASK_CHUNKING_PROMPT_ZH if lang == "zh" else TASK_CHUNKING_PROMPT
    prompt = [{"role": "user", "content": template.replace("{{messages}}", messages_context)}]
    for attempt in range(3):
        try:
            skills_llm = os.getenv("SKILLS_LLM", None)
            llm_kwargs = {"model_name_or_path": skills_llm} if skills_llm else {}
            response_text = llm.generate(prompt, **llm_kwargs)
            response_json = json.loads(response_text.replace("```json", "").replace("```", ""))
            break
        except Exception as e:
            logger.warning(f"[PROCESS_SKILLS] LLM generate failed (attempt {attempt + 1}): {e}")
            if attempt == 2:
                logger.warning(
                    "[PROCESS_SKILLS] LLM generate failed after 3 retries, returning empty dict"
                )
                response_json = []
                break

    task_chunks = {}
    for item in response_json:
        task_name = item["task_name"]
        message_indices = item["message_indices"]
        for indices in message_indices:
            # Validate that indices is a list/tuple with exactly 2 elements
            if isinstance(indices, list) and len(indices) == 1:
                start, end = indices[0], indices[0] + 1
            elif isinstance(indices, int):
                start, end = indices, indices + 1
            elif isinstance(indices, list) and len(indices) == 2:
                start, end = indices[0], indices[1] + 1
            else:
                logger.warning(
                    f"[PROCESS_SKILLS] Invalid message indices format for task '{task_name}': {indices}, skipping"
                )
                continue
            task_chunks.setdefault(task_name, []).extend(messages[start:end])
    return task_chunks


def _extract_skill_memory_by_llm(
    messages: MessageList,
    old_memories: list[TextualMemoryItem],
    llm: BaseLLM,
    chat_history: MessageList,
    chat_history_max_length: int = 5000,
) -> dict[str, Any]:
    old_memories_dict = [skill_memory.model_dump() for skill_memory in old_memories]
    old_mem_references = [
        {
            "id": mem["id"],
            "name": mem["metadata"]["name"],
            "description": mem["metadata"]["description"],
            "procedure": mem["metadata"]["procedure"],
            "experience": mem["metadata"]["experience"],
            "preference": mem["metadata"]["preference"],
            "examples": mem["metadata"]["examples"],
            "tags": mem["metadata"]["tags"],
            "scripts": mem["metadata"].get("scripts"),
            "others": mem["metadata"].get("others"),
        }
        for mem in old_memories_dict
    ]

    # Prepare conversation context
    messages_context = "\n".join(
        [f"{message['role']}: {message['content']}" for message in messages]
    )

    # Prepare history context
    chat_history_context = "\n".join(
        [f"{history['role']}: {history['content']}" for history in chat_history]
    )
    chat_history_context = chat_history_context[-chat_history_max_length:]

    # Prepare old memories context
    old_memories_context = json.dumps(old_mem_references, ensure_ascii=False, indent=2)

    # Prepare prompt
    lang = detect_lang(messages_context)
    template = SKILL_MEMORY_EXTRACTION_PROMPT_ZH if lang == "zh" else SKILL_MEMORY_EXTRACTION_PROMPT
    prompt_content = (
        template.replace("{old_memories}", old_memories_context)
        .replace("{messages}", messages_context)
        .replace("{chat_history}", chat_history_context)
    )
    prompt_content = apply_custom_extract_prompt(prompt_content, "skill")

    prompt = [{"role": "user", "content": prompt_content}]
    logger.info(
        f"[Skill Memory]: Prompt chars={len(prompt_content)} hash={text_hash(prompt_content)}"
    )

    # Call LLM to extract skill memory with retry logic
    for attempt in range(3):
        try:
            # Only pass model_name_or_path if SKILLS_LLM is set
            skills_llm = os.getenv("SKILLS_LLM", None)
            llm_kwargs = {"model_name_or_path": skills_llm} if skills_llm else {}
            response_text = llm.generate(prompt, **llm_kwargs)
            if not response_text:
                logger.warning("[PROCESS_SKILLS] LLM returned empty or invalid response")
                continue
            # Clean up response (remove Markdown code blocks if present)
            logger.info(f"[Skill Memory]: response_text {response_text}")
            response_text = response_text.strip()
            response_text = response_text.replace("```json", "").replace("```", "").strip()

            # Parse JSON response
            skill_memory = json.loads(response_text)

            # If LLM returns null (parsed as None), log and return None
            if skill_memory is None:
                logger.info(
                    "[PROCESS_SKILLS] No skill memory extracted from conversation (LLM returned null)"
                )
                return None

            return skill_memory

        except json.JSONDecodeError as e:
            logger.warning(f"[PROCESS_SKILLS] JSON decode failed (attempt {attempt + 1}): {e}")
            logger.debug(f"[PROCESS_SKILLS] Response text: {response_text}")
            if attempt == 2:
                logger.warning("[PROCESS_SKILLS] Failed to parse skill memory after 3 retries")
                return None
        except Exception as e:
            logger.warning(
                f"[PROCESS_SKILLS] LLM skill memory extraction failed (attempt {attempt + 1}): {e}"
            )
            if attempt == 2:
                logger.warning(
                    "[PROCESS_SKILLS] LLM skill memory extraction failed after 3 retries"
                )
                return None

    return None


def _extract_skill_memory_by_llm_md(
    messages: MessageList,
    old_memories: list[TextualMemoryItem],
    llm: BaseLLM,
    chat_history: MessageList,
    chat_history_max_length: int = 5000,
) -> dict[str, Any]:
    old_memories_dict = [memory.model_dump() for memory in old_memories]
    old_memories_context = {}
    old_skill_content = []
    seen_messages = set()

    for mem in old_memories_dict:
        if mem["metadata"]["memory_type"] == "SkillMemory":
            old_skill_content.append(
                {
                    "id": mem["id"],
                    "name": mem["metadata"]["name"],
                    "description": mem["metadata"]["description"],
                    "procedure": mem["metadata"]["procedure"],
                    "experience": mem["metadata"]["experience"],
                    "preference": mem["metadata"]["preference"],
                    "examples": mem["metadata"]["examples"],
                    "others": mem["metadata"].get("others"),  # TODO: maybe remove, too long
                }
            )
        else:
            # Filter and deduplicate messages
            unique_messages = []
            for item in mem["metadata"]["sources"]:
                message_content = f"{item['role']}: {item['content']}"
                if message_content not in seen_messages:
                    seen_messages.add(message_content)
                    unique_messages.append(message_content)

            if unique_messages:
                old_memories_context.setdefault(mem["metadata"]["memory_type"], []).extend(
                    unique_messages
                )

    # Prepare current conversation context
    messages_context = "\n".join(
        [f"{message['role']}: {message['content']}" for message in messages]
    )

    # Prepare history context
    chat_history_context = "\n".join(
        [f"{history['role']}: {history['content']}" for history in chat_history]
    )
    chat_history_context = chat_history_context[-chat_history_max_length:]

    # Prepare prompt
    lang = detect_lang(messages_context)

    # Prepare old memories context
    old_skill_content = (
        "已有技能列表: \n"
        if lang == "zh"
        else "Exist Skill Schemas: \n" + json.dumps(old_skill_content, ensure_ascii=False, indent=2)
        if old_skill_content
        else ""
    )

    old_memories_context = (
        "相关历史对话:\n"
        if lang == "zh"
        else "Relevant Context:\n"
        + "\n".join([f"{k}:\n{v}" for k, v in old_memories_context.items()])
    )

    template = (
        SKILL_MEMORY_EXTRACTION_PROMPT_MD_ZH if lang == "zh" else SKILL_MEMORY_EXTRACTION_PROMPT_MD
    )
    prompt_content = (
        template.replace("{old_memories}", old_memories_context + old_skill_content)
        .replace("{messages}", messages_context)
        .replace("{chat_history}", chat_history_context)
    )
    prompt_content = apply_custom_extract_prompt(prompt_content, "skill")

    prompt = [{"role": "user", "content": prompt_content}]
    logger.info(
        "[Skill Memory]: _extract_skill_memory_by_llm_md: Prompt "
        f"chars={len(prompt_content)} hash={text_hash(prompt_content)}"
    )

    # Call LLM to extract skill memory with retry logic
    for attempt in range(3):
        try:
            # Only pass model_name_or_path if SKILLS_LLM is set
            skills_llm = os.getenv("SKILLS_LLM", None)
            llm_kwargs = {"model_name_or_path": skills_llm} if skills_llm else {}
            response_text = llm.generate(prompt, **llm_kwargs)
            if not response_text:
                logger.warning("[PROCESS_SKILLS] LLM returned empty or invalid response")
                continue
            # Clean up response (remove Markdown code blocks if present)
            logger.info(f"[Skill Memory]: response_text {response_text}")
            response_text = response_text.strip()
            response_text = response_text.replace("```json", "").replace("```", "").strip()

            # Parse JSON response
            skill_memory = json.loads(response_text)

            # If LLM returns null (parsed as None), log and return None
            if skill_memory is None:
                logger.info(
                    "[PROCESS_SKILLS] No skill memory extracted from conversation (LLM returned null)"
                )
                return None
            # If no old skill content, set update to False (for llm hallucination)
            if not old_skill_content:
                skill_memory["old_memory_id"] = ""
                skill_memory["update"] = False

            return skill_memory

        except json.JSONDecodeError as e:
            logger.warning(f"[PROCESS_SKILLS] JSON decode failed (attempt {attempt + 1}): {e}")
            logger.debug(f"[PROCESS_SKILLS] Response text: {response_text}")
            if attempt == 2:
                logger.warning("[PROCESS_SKILLS] Failed to parse skill memory after 3 retries")
                return None
        except Exception as e:
            logger.warning(
                f"[PROCESS_SKILLS] LLM skill memory extraction failed (attempt {attempt + 1}): {e}"
            )
            if attempt == 2:
                logger.warning(
                    "[PROCESS_SKILLS] LLM skill memory extraction failed after 3 retries"
                )
                return None

    return None


def _recall_related_skill_memories(
    task_type: str,
    messages: MessageList,
    searcher: Searcher,
    llm: BaseLLM,
    rewrite_query: bool,
    info: dict[str, Any],
    mem_cube_id: str,
) -> list[TextualMemoryItem]:
    query = _rewrite_query(task_type, messages, llm, rewrite_query)
    related_skill_memories = searcher.search(
        query,
        top_k=5,
        memory_type="All",
        info=info,
        include_skill_memory=True,
        user_name=mem_cube_id,
    )

    return related_skill_memories


def _rewrite_query(task_type: str, messages: MessageList, llm: BaseLLM, rewrite_query: bool) -> str:
    if not rewrite_query:
        # Return the first user message content if rewrite is disabled
        return messages[0]["content"] if messages else ""

    # Construct messages context for LLM
    messages_context = "\n".join(
        [f"{message['role']}: {message['content']}" for message in messages]
    )

    # Prepare prompt with task type and messages
    lang = detect_lang(messages_context)
    template = TASK_QUERY_REWRITE_PROMPT_ZH if lang == "zh" else TASK_QUERY_REWRITE_PROMPT
    prompt_content = template.replace("{task_type}", task_type).replace(
        "{messages}", messages_context
    )
    prompt = [{"role": "user", "content": prompt_content}]

    # Call LLM to rewrite the query
    try:
        response_text = llm.generate(prompt)
        # Clean up response (remove any markdown formatting if present)
        if response_text and isinstance(response_text, str):
            return response_text.strip()
        else:
            logger.warning(
                "[PROCESS_SKILLS] LLM returned empty or invalid response, returning first message content"
            )
            return messages[0]["content"] if messages else ""
    except Exception as e:
        logger.warning(
            f"[PROCESS_SKILLS] LLM query rewrite failed: {e}, returning first message content"
        )
        return messages[0]["content"] if messages else ""


def _upload_skills(
    skills_repo_backend: str,
    skills_oss_dir: str | None,
    local_tmp_file_path: str,
    local_save_file_path: str,
    client: Any,
    user_id: str,
    skills_dir_config: dict[str, Any] | None = None,
) -> str:
    config = {"skills_local_dir": local_save_file_path, "skills_oss_dir": skills_oss_dir or ""}
    config.update(skills_dir_config or {})
    return skill_store.publish_skill(
        Path(local_tmp_file_path),
        user_id,
        backend=skills_repo_backend,
        skills_dir_config=config,
        oss_client=client,
    )


def _cleanup_skill_tmp_files(zip_path: str) -> None:
    try:
        zip_file = Path(zip_path)
        skill_dir = zip_file.parent / zip_file.stem
        zip_file.unlink(missing_ok=True)
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
        logger.info(f"[PROCESS_SKILLS] Cleaned up local files: {zip_path} and {skill_dir}")
    except Exception as cleanup_error:
        logger.warning(f"[PROCESS_SKILLS] Error cleaning up local files: {cleanup_error}")


def _delete_zip(
    url: str | None,
    *,
    skills_repo_backend: str,
    oss_client: Any,
    skills_dir_config: dict[str, Any],
    user_id: str,
) -> None:
    if not url:
        return
    try:
        skill_store.delete_skill_by_url(
            url,
            user_id,
            backend=skills_repo_backend,
            skills_dir_config=skills_dir_config,
            oss_client=oss_client,
        )
    except Exception as e:
        logger.warning(
            f"[PROCESS_SKILLS] Failed to delete skill file from {skills_repo_backend}: {e}"
        )


def _publish_skill(
    skill_memory: dict[str, Any],
    zip_path: str,
    *,
    skills_repo_backend: str,
    oss_client: Any,
    skills_dir_config: dict[str, Any],
    user_id: str,
) -> bool:
    """Upload the new zip. Returns False when an update must be dropped.

    The previous zip of an updated skill is not touched here: it goes only once the new item
    exists (see ``process_skill_memory``), so a failure on the way leaves the old version intact.
    """
    is_update = bool(skill_memory.get("update", False) and skill_memory.get("old_memory_id"))
    try:
        try:
            url = _upload_skills(
                skills_repo_backend=skills_repo_backend,
                skills_oss_dir=skills_dir_config["skills_oss_dir"],
                local_tmp_file_path=zip_path,
                local_save_file_path=skills_dir_config["skills_local_dir"],
                client=oss_client,
                user_id=user_id,
                skills_dir_config=skills_dir_config,
            )
        except Exception as e:
            logger.warning(f"[PROCESS_SKILLS] Error uploading skill to {skills_repo_backend}: {e}")
            url = ""
        if is_update and not url:
            return False
        skill_memory["url"] = url
        logger.info(f"[PROCESS_SKILLS] Uploaded skill to {skills_repo_backend}: {url}")
        return True
    finally:
        _cleanup_skill_tmp_files(zip_path)


@timed
def _write_skills_to_file(
    skill_memory: dict[str, Any], info: dict[str, Any], skills_dir_config: dict[str, Any]
) -> str:
    user_id = info.get("user_id", "unknown")
    raw_name = skill_memory.get("name") or "unnamed_skill"
    skill_name = re.sub(r"\s+", "_", str(raw_name).strip()).lower()
    # Filesystem names never come from the raw skill name or user id, and every write is unique.
    zip_stem = skill_store.unique_zip_stem(raw_name)
    folder_name = skill_store.skill_slug(raw_name)

    tmp_dir = Path(skills_dir_config["skills_local_tmp_dir"]) / skill_store.user_dir_name(user_id)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    skill_dir = tmp_dir / zip_stem
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Generate SKILL.md content with frontmatter
    skill_md_content = f"""---
name: {skill_name}
description: {skill_memory.get("description", "")}
---
"""

    # Add trigger
    trigger = skill_memory.get("trigger", "")
    if trigger:
        skill_md_content += f"\n## Trigger\n{trigger}\n"

    # Add Procedure section only if present
    procedure = skill_memory.get("procedure", "")
    if procedure and procedure.strip():
        skill_md_content += f"\n## Procedure\n{procedure}\n"

    # Add Experience section only if there are items
    experiences = skill_memory.get("experience", [])
    if experiences:
        skill_md_content += "\n## Experience\n"
        for idx, exp in enumerate(experiences, 1):
            skill_md_content += f"{idx}. {exp}\n"

    # Add User Preferences section only if there are items
    preferences = skill_memory.get("preference", [])
    if preferences:
        skill_md_content += "\n## User Preferences\n"
        for pref in preferences:
            skill_md_content += f"- {pref}\n"

    # Add Examples section only if there are items
    examples = skill_memory.get("examples", [])
    if examples:
        skill_md_content += "\n## Examples\n"
        for idx, example in enumerate(examples, 1):
            skill_md_content += f"\n### Example {idx}\n```markdown\n{example}\n```\n"

    # Add scripts reference if present
    scripts = skill_memory.get("scripts")
    if scripts and isinstance(scripts, dict):
        skill_md_content += "\n## Scripts\n"
        skill_md_content += "This skill includes the following executable scripts:\n\n"
        for script_name in scripts:
            skill_md_content += f"- `./scripts/{script_name}`\n"

    tool_usage = skill_memory.get("tool", "")
    if tool_usage:
        skill_md_content += f"\n## Tool Usage\n{tool_usage}\n"

    # Add others - handle both inline content and separate markdown files
    others = skill_memory.get("others")
    if others and isinstance(others, dict):
        # Separate markdown files from inline content
        md_files = {}
        inline_content = {}

        for key, value in others.items():
            if key.endswith(".md"):
                md_files[key] = value
            else:
                inline_content[key] = value

        # Add inline content to SKILL.md
        if inline_content:
            skill_md_content += "\n## Additional Information\n"
            for key, value in inline_content.items():
                skill_md_content += f"\n### {key}\n{value}\n"

        # Add references to separate markdown files
        if md_files:
            if not inline_content:
                skill_md_content += "\n## Additional Information\n"
            skill_md_content += "\nSee also:\n"
            for md_filename in md_files:
                skill_md_content += f"- [{md_filename}](./reference/{md_filename})\n"

    # Write SKILL.md file
    skill_md_path = skill_dir / "SKILL.md"
    with open(skill_md_path, "w", encoding="utf-8") as f:
        f.write(skill_md_content)

    # Write separate markdown files from others
    if others and isinstance(others, dict):
        for key, value in others.items():
            if key.endswith(".md") and Path(key).name not in {"", ".", ".."}:
                md_file_dir = skill_dir / "reference"
                md_file_dir.mkdir(parents=True, exist_ok=True)
                md_file_path = md_file_dir / Path(key).name
                with open(md_file_path, "w", encoding="utf-8") as f:
                    f.write(value)

    # If there are scripts, create a scripts directory with individual script files
    if scripts and isinstance(scripts, dict):
        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)

        # Write each script to its own file
        for script_filename, script_content in scripts.items():
            # Ensure filename ends with .py
            if not script_filename.endswith(".py"):
                script_filename = f"{script_filename}.py"

            script_filename = Path(script_filename).name
            if script_filename in {"", ".", ".."}:
                continue
            script_path = scripts_dir / script_filename
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script_content)

    # Create zip file in tmp_dir
    zip_path = tmp_dir / f"{zip_stem}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        # Walk through the skill directory and add all files
        for file_path in skill_dir.rglob("*"):
            if file_path.is_file():
                # Use relative path from skill_dir for archive
                arcname = Path(folder_name) / file_path.relative_to(skill_dir)
                zipf.write(str(file_path), str(arcname))

    logger.info(f"[PROCESS_SKILLS] Created skill zip file: {zip_path}")
    return str(zip_path)


def create_skill_memory_item(
    skill_memory: dict[str, Any],
    info: dict[str, Any],
    embedder: BaseEmbedder | None = None,
    sources: list[SourceMessage] | None = None,
    **kwargs: Any,
) -> TextualMemoryItem:
    info_ = info.copy()
    user_id = info_.pop("user_id", "")
    session_id = info_.pop("session_id", "")

    # Extract manager_user_id and project_id from user_context
    user_context: UserContext | None = kwargs.get("user_context")
    manager_user_id = user_context.manager_user_id if user_context else None
    project_id = user_context.project_id if user_context else None

    # Use description as the memory content
    memory_content = skill_memory.get("description", "")
    embed_text = memory_content
    if skill_memory.get("skill_source") == "user_upload":
        # Uploaded descriptions are author-written and often terse; the name carries intent too.
        embed_text = "\n".join(part for part in (skill_memory.get("name"), memory_content) if part)

    # Create metadata with all skill-specific fields directly
    metadata = TreeNodeTextualMemoryMetadata(
        user_id=user_id,
        session_id=session_id,
        memory_type="SkillMemory",
        status="activated",
        tags=skill_memory.get("tags") or skill_memory.get("trigger", []),
        key=skill_memory.get("name", ""),
        sources=sources or [],
        usage=[],
        background="",
        confidence=0.99,
        created_at=utc_now_iso(),
        updated_at=utc_now_iso(),
        type="skills",
        info=info_,
        embedding=embedder.embed([embed_text])[0] if embedder else None,
        # Skill-specific fields
        name=skill_memory.get("name", ""),
        description=skill_memory.get("description", ""),
        procedure=skill_memory.get("procedure", ""),
        experience=skill_memory.get("experience", []),
        preference=skill_memory.get("preference", []),
        examples=skill_memory.get("examples", []),
        scripts=skill_memory.get("scripts"),
        others=skill_memory.get("others"),
        url=skill_memory.get("url", ""),
        skill_source=skill_memory.get("skill_source"),
        manager_user_id=manager_user_id,
        project_id=project_id,
    )

    # If this is an update, use the old memory ID
    item_id = (
        skill_memory.get("old_memory_id", "")
        if skill_memory.get("update", False)
        else str(uuid.uuid4())
    )
    if not item_id:
        item_id = str(uuid.uuid4())

    return TextualMemoryItem(id=item_id, memory=memory_content, metadata=metadata)


def carry_over_history(item: TextualMemoryItem, previous: TextualMemoryItem) -> None:
    """Record the replaced skill's description as a version of ``item``, which reuses its id.

    ``item`` overwrites the old node when it is written, so the old description would otherwise
    be lost. The zip of the old version is not kept.
    """
    fields = versioning.merge_into_head(item, previous, update_type="update")
    item.metadata.history = [ArchivedTextualMemory(**json.loads(e)) for e in fields["history"]]
    item.metadata.version = fields["version"]
    item.metadata.valid_from = fields["valid_from"]


def _skill_init(skills_repo_backend, oss_config, skills_dir_config):
    if skills_repo_backend == "OSS":
        # Validate required configurations
        if not oss_config:
            logger.warning(
                "[PROCESS_SKILLS] OSS configuration is required for skill memory processing"
            )
            return None, None, False

        if not skills_dir_config:
            logger.warning(
                "[PROCESS_SKILLS] Skills directory configuration is required for skill memory processing"
            )
            return None, None, False

        # Validate skills_dir has required keys
        required_keys = ["skills_local_tmp_dir", "skills_local_dir", "skills_oss_dir"]
        missing_keys = [key for key in required_keys if key not in skills_dir_config]
        if missing_keys:
            logger.warning(
                f"[PROCESS_SKILLS] Skills directory configuration missing required keys: {', '.join(missing_keys)}"
            )
            return None, None, False

        oss_client = create_oss_client(oss_config)
        if not oss_client:
            logger.warning("[PROCESS_SKILLS] Failed to create OSS client")
            return None, None, False
        return oss_client, missing_keys, True
    else:
        return None, None, True


def _get_skill_file_storage_location() -> str:
    # SKILLS_REPO_BACKEND: Skill file storage location OSS/LOCAL
    return skill_store.storage_backend()


def _get_skill_min_tool_rounds() -> int:
    """Minimum number of tool-call rounds required before skill extraction.

    The historical value was a hard-coded 5, which never triggered for batch
    judgement workloads that do not send ``role: tool`` messages. Deployments
    can lower it with ``SKILL_MIN_TOOL_ROUNDS`` (0 disables the gate).
    """
    default = 5
    raw = os.getenv("SKILL_MIN_TOOL_ROUNDS")
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "Environment variable [SKILL_MIN_TOOL_ROUNDS]=%r is not an integer, using %d",
            raw,
            default,
        )
        return default
    if value < 0:
        logger.warning(
            "Environment variable [SKILL_MIN_TOOL_ROUNDS]=%r must be >= 0, using %d",
            raw,
            default,
        )
        return default
    return value


@timed
def process_skill_memory_fine(
    fast_memory_items: list[TextualMemoryItem],
    info: dict[str, Any],
    searcher: Searcher | None = None,
    graph_db: BaseGraphDB | None = None,
    llm: BaseLLM | None = None,
    embedder: BaseEmbedder | None = None,
    rewrite_query: bool = True,
    oss_config: dict[str, Any] | None = None,
    skills_dir_config: dict[str, Any] | None = None,
    complete_skill_memory: bool = True,
    **kwargs,
) -> list[TextualMemoryItem]:
    is_upload_skill = kwargs.pop("is_upload_skill", False)
    if is_upload_skill:
        from memos.mem_reader.read_skill_memory.upload_skill_memory import (
            process_upload_skill_memory,
        )

        return process_upload_skill_memory(
            fast_memory_items=fast_memory_items,
            info=info,
            embedder=embedder,
            oss_config=oss_config,
            skills_dir_config=skills_dir_config,
            **kwargs,
        )

    skills_repo_backend = _get_skill_file_storage_location()
    oss_client, _missing_keys, flag = _skill_init(
        skills_repo_backend, oss_config, skills_dir_config
    )
    if not flag:
        return []

    chat_history = kwargs.get("chat_history")
    if not chat_history or not isinstance(chat_history, list):
        chat_history = []

    messages = _reconstruct_messages_from_memory_items(fast_memory_items)
    tool_rounds = sum(1 for message in messages if message.get("role") == "tool")
    min_tool_rounds = _get_skill_min_tool_rounds()
    if tool_rounds < min_tool_rounds:
        logger.info(
            f"[PROCESS_SKILLS] Skip skill extraction: tool rounds {tool_rounds} < {min_tool_rounds}"
        )
        return []

    chat_history, messages = _preprocess_extract_messages(chat_history, messages)
    if not messages:
        return []

    messages = _add_index_to_message(messages)
    chat_history = _add_index_to_message(chat_history)

    task_chunks = _split_task_chunk_by_llm(llm, messages)
    if not task_chunks:
        logger.warning("[PROCESS_SKILLS] No task chunks found")
        return []

    # recall - get related skill memories for each task separately (parallel)
    related_skill_memories_by_task = {}
    with ContextThreadPoolExecutor(max_workers=5) as executor:
        recall_futures = {
            executor.submit(
                _recall_related_skill_memories,
                task_type=task,
                messages=msg,
                searcher=searcher,
                llm=llm,
                rewrite_query=rewrite_query,
                info=info,
                mem_cube_id=kwargs.get("user_name", info.get("user_id", "")),
            ): task
            for task, msg in task_chunks.items()
        }
        for future in as_completed(recall_futures):
            task_name = recall_futures[future]
            try:
                related_memories = future.result()
                related_skill_memories_by_task[task_name] = related_memories
            except Exception as e:
                logger.warning(
                    f"[PROCESS_SKILLS] Error recalling skill memories for task '{task_name}': {e}"
                )
                related_skill_memories_by_task[task_name] = []

    @timed
    def _simple_extract():
        # simple extract skill memory, only one stage
        memories = []
        with ContextThreadPoolExecutor(max_workers=min(5, len(task_chunks))) as executor:
            futures = {
                executor.submit(
                    _extract_skill_memory_by_llm,
                    messages=chunk_messages,
                    # Filter only SkillMemory types
                    old_memories=[
                        item
                        for item in related_skill_memories_by_task.get(task_type, [])
                        if item and getattr(item.metadata, "memory_type", "") == "SkillMemory"
                    ],
                    llm=llm,
                    chat_history=chat_history,
                ): task_type
                for task_type, chunk_messages in task_chunks.items()
            }

            for future in as_completed(futures):
                task_type = futures[future]
                try:
                    skill_memory = future.result()
                    if skill_memory:
                        skill_memory["_task_type"] = task_type
                        memories.append(skill_memory)
                except Exception as e:
                    logger.warning(
                        f"[PROCESS_SKILLS] _simple_extract: Error processing task '{task_type}': {e}"
                    )
        return memories

    @timed
    def _full_extract():
        # full extract skill memory, include two stage
        raw_extraction_results = _batch_extract_skills(
            task_chunks=task_chunks,
            related_memories_map=related_skill_memories_by_task,
            llm=llm,
            chat_history=chat_history,
        )
        if not raw_extraction_results:
            return []
        return _batch_generate_skill_details(
            raw_skills_data=raw_extraction_results,
            related_skill_memories_map=related_skill_memories_by_task,
            llm=llm,
        )

    # Execute both parts in parallel
    skill_memories = _simple_extract() if not complete_skill_memory else _full_extract()

    # write skills to file and get zip paths
    skill_memory_with_paths = []
    with ContextThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(
                _write_skills_to_file, skill_memory, info, skills_dir_config
            ): skill_memory
            for skill_memory in skill_memories
        }
        for future in as_completed(futures):
            try:
                zip_path = future.result()
                skill_memory = futures[future]
                skill_memory_with_paths.append((skill_memory, zip_path))
            except Exception as e:
                logger.warning(f"[PROCESS_SKILLS] Error writing skills to file: {e}")
                continue

    # Create a mapping from old_memory_id to old memory for easy lookup
    # Collect all related memories from all tasks
    all_related_memories = []
    for memories in related_skill_memories_by_task.values():
        all_related_memories.extend(memories)
    old_memories_map = {mem.id: mem for mem in all_related_memories}

    # Publish each new zip; the zip of a replaced version goes after its new item exists.
    user_id = info.get("user_id", "unknown")
    published_ids = set()
    for skill_memory, zip_path in skill_memory_with_paths:
        if _publish_skill(
            skill_memory,
            zip_path,
            skills_repo_backend=skills_repo_backend,
            oss_client=oss_client,
            skills_dir_config=skills_dir_config,
            user_id=user_id,
        ):
            published_ids.add(id(skill_memory))

    # An update that could not be published must not overwrite the node of the previous version.
    skill_memories = [
        skill_memory
        for skill_memory in skill_memories
        if not (skill_memory.get("update", False) and skill_memory.get("old_memory_id"))
        or id(skill_memory) in published_ids
    ]

    # Build source lookup: (role, content) → SourceMessage from fast_memory_items
    source_lookup: dict[tuple[str, str], SourceMessage] = {}
    for fast_item in fast_memory_items:
        for source in getattr(fast_item.metadata, "sources", []) or []:
            source_lookup.setdefault((source.role, source.content), source)

    # Create TextualMemoryItem objects
    skill_memory_items = []
    zip_args = {
        "skills_repo_backend": skills_repo_backend,
        "oss_client": oss_client,
        "skills_dir_config": skills_dir_config,
        "user_id": user_id,
    }
    for skill_memory in skill_memories:
        previous = None
        try:
            # Match sources precisely via the task chunk messages that produced this skill
            task_type = skill_memory.pop("_task_type", None)
            chunk_messages = task_chunks.get(task_type, []) if task_type else []
            skill_sources = []
            seen = set()
            for msg in chunk_messages:
                key = (msg.get("role"), msg.get("content"))
                if key not in seen:
                    seen.add(key)
                    source = source_lookup.get(key)
                    if source:
                        skill_sources.append(source)

            skill_memory["skill_source"] = "auto_create"
            memory_item = create_skill_memory_item(
                skill_memory, info, embedder, sources=skill_sources, **kwargs
            )
            previous = (
                old_memories_map.get(skill_memory.get("old_memory_id"))
                if skill_memory.get("update", False)
                else None
            )
            if previous is not None and previous.id == memory_item.id:
                carry_over_history(memory_item, previous)
        except Exception as e:
            logger.warning(f"[PROCESS_SKILLS] Error creating skill memory item: {e}")
            _delete_zip(skill_memory.get("url"), **zip_args)
            continue
        skill_memory_items.append(memory_item)
        if memory_item.metadata.url:
            replaced = previous if previous is not None and previous.id == memory_item.id else None
            skill_store.defer_file_cleanup(
                memory_item.id,
                memory_item.metadata.url,
                on_stored=partial(_delete_zip, getattr(replaced.metadata, "url", None), **zip_args)
                if replaced
                else (lambda: None),
                on_lost=partial(_delete_zip, memory_item.metadata.url, **zip_args),
            )

    return skill_memory_items

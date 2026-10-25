"""Project-level extraction prompt configuration and model inventory.

These endpoints are what the console's "custom extraction" page and "models"
page call. Before them the prompt could only be changed by editing a mounted
Python file in the deployment, and the model list had to be read from a
ConfigMap by the BFF.
"""

from __future__ import annotations

import os
import re

from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException

from memos.api.handlers.base_handler import BaseHandler
from memos.api.product_models import (
    DebugExtractRequest,
    ExtractDebugData,
    ExtractDebugResponse,
    ExtractDebugResult,
    ExtractPromptData,
    ExtractPromptRequest,
    ExtractPromptResponse,
    GenerateExtractPromptRequest,
    ModelListData,
    ModelListResponse,
    ModelRecord,
    PromptData,
    PromptResponse,
    SaveExtractPromptRequest,
)
from memos.mem_reader.prompt_config import (
    EXTRACTION_TYPES,
    PROMPT_PLACEHOLDER,
    default_extract_prompt,
    delete_prompt,
    get_saved_prompt,
    normalize_extract_prompt,
    save_prompt,
)
from memos.mem_reader.utils import parse_json_result


_REWRITE_SYSTEM = (
    "你是提示词工程专家。用户会给你一份「记忆抽取器」的提示词，以及一句修改要求。"
    "请按修改要求重写这份提示词，保持它原有的输出 JSON 结构（memory list / summary）不变，"
    "只调整抽取规则部分。必须保留 ${conversation} 占位符。"
    "直接输出重写后的完整提示词正文，不要任何解释、不要 markdown 代码块。"
)

# 与部署里真正生效的配置键一一对应。只列能指到具体键的模型；缺失的整行不出现。
_MODEL_ROWS: tuple[dict[str, Any], ...] = (
    {
        "model": "MEMRADER_MODEL",
        "role": "记忆读取",
        "group": "memory",
        "provider": "MEMRADER_API_BASE",
    },
    {
        "model": "MOS_CHAT_MODEL",
        "role": "记忆写入 / 对话",
        "group": "chat",
        "provider": "OPENAI_API_BASE",
    },
    {
        "model": "MOS_EMBEDDER_MODEL",
        "role": "向量化",
        "group": "memory",
        "extra": lambda: _embedding_spec(),
    },
    {
        "model": "MOS_RERANKER_MODEL",
        "role": "重排",
        "group": "memory",
        "extra": lambda: _rerank_spec(),
    },
)


def _env(key: str) -> str:
    return os.getenv(key, "").strip()


def _host_of(url: str) -> str:
    if not url:
        return ""
    try:
        return urlparse(url).netloc
    except ValueError:
        return ""


def _embedding_spec() -> str:
    dimension = _env("EMBEDDING_DIMENSION")
    return f"{dimension} 维" if dimension else ""


def _rerank_spec() -> str:
    backend = _env("MOS_RERANKER_BACKEND")
    return f"后端 {backend}" if backend else ""


def list_models() -> ModelListData:
    records: list[ModelRecord] = []
    for row in _MODEL_ROWS:
        model = _env(row["model"])
        if not model:
            continue
        parts: list[str] = []
        provider = _host_of(_env(row.get("provider", "")))
        if provider:
            parts.append(provider)
        extra = row["extra"]() if "extra" in row else ""
        if extra:
            parts.append(extra)
        records.append(
            ModelRecord(
                role=row["role"],
                model=model,
                spec=" · ".join(parts),
                source=row["model"],
                group=row["group"],
            )
        )
    return ModelListData(records=records, total=len(records))


def _strip_fence(text: str) -> str:
    fenced = re.match(r"^```(?:\w+)?\s*([\s\S]*?)```$", text.strip())
    return (fenced.group(1) if fenced else text).strip()


class PromptHandler(BaseHandler):
    """Read/write the per-project extraction prompt and list configured models."""

    def get_prompt(self, request: ExtractPromptRequest) -> ExtractPromptResponse:
        saved = get_saved_prompt(request.mem_cube_id)
        prompt = saved[0] if saved else default_extract_prompt()
        return ExtractPromptResponse(
            code=200,
            message="Extract prompt loaded",
            data=ExtractPromptData(
                mem_cube_id=request.mem_cube_id,
                prompt=prompt,
                extraction_types=list(EXTRACTION_TYPES),
                updated_at=saved[1] if saved else None,
                source="saved" if saved else "default",
                is_default=saved is None,
            ),
        )

    def save(self, request: SaveExtractPromptRequest) -> PromptResponse:
        try:
            normalize_extract_prompt(request.prompt)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        save_prompt(request.mem_cube_id, request.prompt)
        return PromptResponse(
            code=200, message="Extract prompt saved", data=PromptData(prompt=request.prompt.strip())
        )

    def reset(self, request: ExtractPromptRequest) -> PromptResponse:
        delete_prompt(request.mem_cube_id)
        return PromptResponse(
            code=200,
            message="Extract prompt reset to default",
            data=PromptData(prompt=default_extract_prompt()),
        )

    def generate(self, request: GenerateExtractPromptRequest) -> PromptResponse:
        prompt = self._current_prompt(request.mem_cube_id)
        try:
            text = self.llm.generate(
                [
                    {"role": "system", "content": _REWRITE_SYSTEM},
                    {
                        "role": "user",
                        "content": f"修改要求：{request.description}\n\n原提示词：\n{prompt}",
                    },
                ]
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"prompt generation failed: {exc}") from exc
        rewritten = _strip_fence(text or "")
        if PROMPT_PLACEHOLDER not in rewritten:
            raise HTTPException(
                status_code=502,
                detail=f"model response dropped {PROMPT_PLACEHOLDER}; try again",
            )
        return PromptResponse(
            code=200, message="Extract prompt generated", data=PromptData(prompt=rewritten)
        )

    def debug_extract(self, request: DebugExtractRequest) -> ExtractDebugResponse:
        prompt = self._current_prompt(request.mem_cube_id)
        conversation = "\n\n".join(
            f"{'助手' if message.role == 'assistant' else '用户'}：{message.content}"
            for message in request.messages
        )
        try:
            raw = self.llm.generate(
                [{"role": "user", "content": prompt.replace(PROMPT_PLACEHOLDER, conversation)}]
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"debug extraction failed: {exc}") from exc

        results: list[ExtractDebugResult] = []
        try:
            parsed = parse_json_result(raw or "")
        except Exception:  # noqa: BLE001 - a malformed model reply must not 500
            parsed = None
        memory_list = (parsed or {}).get("memory list") or (parsed or {}).get("memory_list")
        if isinstance(memory_list, list):
            for item in memory_list:
                if not isinstance(item, dict):
                    continue
                content = item.get("value") or item.get("content") or item.get("key") or ""
                if content:
                    results.append(
                        ExtractDebugResult(
                            type=str(item.get("memory_type") or item.get("type") or "memory"),
                            content=str(content),
                        )
                    )
        else:
            # 模型没按结构返回时给一条原文，明确标成 raw，不假装抽取成功。
            results = [ExtractDebugResult(type="raw", content=(raw or "")[:2000])]

        return ExtractDebugResponse(
            code=200,
            message="Extraction completed",
            data=ExtractDebugData(
                extraction_types=request.extraction_types or list(EXTRACTION_TYPES),
                results=results,
            ),
        )

    def _current_prompt(self, mem_cube_id: str) -> str:
        saved = get_saved_prompt(mem_cube_id)
        return saved[0] if saved else default_extract_prompt()


def model_list() -> ModelListResponse:
    data = list_models()
    return ModelListResponse(code=200, message="Model list loaded", data=data)

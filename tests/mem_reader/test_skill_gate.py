"""Tests for the skill-extraction gate and storage-backend selection."""

import pytest

from memos.mem_reader.read_skill_memory import process_skill_memory as psm


def test_min_tool_rounds_defaults_to_five(monkeypatch):
    monkeypatch.delenv("SKILL_MIN_TOOL_ROUNDS", raising=False)

    assert psm._get_skill_min_tool_rounds() == 5


def test_min_tool_rounds_reads_env(monkeypatch):
    monkeypatch.setenv("SKILL_MIN_TOOL_ROUNDS", "2")

    assert psm._get_skill_min_tool_rounds() == 2


@pytest.mark.parametrize("raw", ["", "   "])
def test_min_tool_rounds_blank_env_uses_default(monkeypatch, raw):
    monkeypatch.setenv("SKILL_MIN_TOOL_ROUNDS", raw)

    assert psm._get_skill_min_tool_rounds() == 5


@pytest.mark.parametrize("raw", ["abc", "-1", "1.5"])
def test_min_tool_rounds_invalid_env_uses_default(monkeypatch, raw):
    monkeypatch.setenv("SKILL_MIN_TOOL_ROUNDS", raw)

    assert psm._get_skill_min_tool_rounds() == 5


def test_storage_backend_defaults_to_local_when_unset(monkeypatch):
    monkeypatch.delenv("SKILLS_REPO_BACKEND", raising=False)

    assert psm._get_skill_file_storage_location() == "LOCAL"


def test_storage_backend_accepts_lowercase(monkeypatch):
    monkeypatch.setenv("SKILLS_REPO_BACKEND", "oss")

    assert psm._get_skill_file_storage_location() == "OSS"


def test_storage_backend_invalid_falls_back_to_local(monkeypatch):
    monkeypatch.setenv("SKILLS_REPO_BACKEND", "S3")

    assert psm._get_skill_file_storage_location() == "LOCAL"


def _run_gate(monkeypatch, tool_rounds: int):
    """Run the gate with everything after it stubbed out.

    Returns True when the gate let the request through.
    """
    messages = [{"role": "tool", "content": "x"} for _ in range(tool_rounds)]
    monkeypatch.setattr(psm, "_get_skill_file_storage_location", lambda: "LOCAL")
    monkeypatch.setattr(psm, "_skill_init", lambda *args, **kwargs: (None, None, True))
    monkeypatch.setattr(psm, "_reconstruct_messages_from_memory_items", lambda items: messages)

    passed = {"value": False}

    def _preprocess(chat_history, msgs):
        passed["value"] = True
        return [], []

    monkeypatch.setattr(psm, "_preprocess_extract_messages", _preprocess)

    psm.process_skill_memory_fine(
        fast_memory_items=[],
        info={},
        oss_config={},
        skills_dir_config={},
    )
    return passed["value"]


def test_gate_blocks_below_configured_rounds(monkeypatch):
    monkeypatch.setenv("SKILL_MIN_TOOL_ROUNDS", "3")

    assert _run_gate(monkeypatch, tool_rounds=2) is False


def test_gate_allows_at_configured_rounds(monkeypatch):
    monkeypatch.setenv("SKILL_MIN_TOOL_ROUNDS", "3")

    assert _run_gate(monkeypatch, tool_rounds=3) is True


def test_zero_disables_the_gate(monkeypatch):
    monkeypatch.setenv("SKILL_MIN_TOOL_ROUNDS", "0")

    assert _run_gate(monkeypatch, tool_rounds=0) is True

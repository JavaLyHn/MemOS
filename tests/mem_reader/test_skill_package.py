"""Tests for deterministic skill-package parsing (SKILL.md and zip) and the user-upload path."""

import io
import zipfile

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from memos.mem_reader.read_skill_memory import process_skill_memory as psm
from memos.mem_reader.read_skill_memory import skill_package as sp
from memos.mem_reader.read_skill_memory import upload_skill_memory as usm


THIRD_PARTY_BODY = (
    "# PDF toolkit\n\n"
    "Use this skill whenever the user hands you a PDF and wants text extracted.\n\n"
    "## Quick start\n\n"
    "1. Run `pdftotext -layout input.pdf -`.\n"
    "2. If the output is empty, fall back to OCR.\n\n"
    "## Gotchas\n\n"
    "Scanned documents need `ocrmypdf` first."
)
THIRD_PARTY_MD = (
    "---\n"
    "name: pdf-toolkit\n"
    "description: Extract text and tables from PDF files\n"
    "---\n\n" + THIRD_PARTY_BODY + "\n"
)


def _zip(entries: dict[str, str | bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for path, data in entries.items():
            archive.writestr(path, data)
    return buf.getvalue()


def test_third_party_body_is_kept_whole():
    parsed = sp.parse_skill_package(THIRD_PARTY_MD.encode(), "SKILL.md")

    assert parsed["name"] == "pdf-toolkit"
    assert parsed["description"] == "Extract text and tables from PDF files"
    assert parsed["procedure"] == THIRD_PARTY_BODY
    assert len(parsed["procedure"]) > 20


def test_project_generated_sections_are_kept_whole():
    body = (
        "## Trigger\n\nWhen the user asks for a weekly report.\n\n"
        "## Procedure\n\n1. Pull the metrics\n2. Render the template\n\n"
        "## Experience\n\n- Always check the timezone\n"
    )
    content = f"---\nname: weekly-report\ndescription: Build weekly reports\n---\n\n{body}"

    parsed = sp.parse_skill_package(content.encode(), "weekly-report.md")

    assert parsed["procedure"] == body.strip()


def test_name_falls_back_to_file_stem_and_description_may_be_empty():
    parsed = sp.parse_skill_package(b"Just some notes.\n", "release-notes.md")

    assert parsed["name"] == "release-notes"
    assert parsed["description"] == ""
    assert parsed["procedure"] == "Just some notes."


def test_front_matter_with_colon_in_value_falls_back_to_line_parsing():
    content = "---\nname: colon-skill\ndescription: Use when: the build fails\n---\nbody text\n"

    parsed = sp.parse_skill_package(content.encode(), "SKILL.md")

    assert parsed["name"] == "colon-skill"
    assert parsed["description"] == "Use when: the build fails"
    assert parsed["procedure"] == "body text"


def test_zip_and_markdown_give_the_same_result():
    from_md = sp.parse_skill_package(THIRD_PARTY_MD.encode(), "SKILL.md")
    from_zip = sp.parse_skill_package(_zip({"SKILL.md": THIRD_PARTY_MD}), "pdf-toolkit.zip")

    assert from_zip == from_md


def test_zip_reads_scripts_and_reference_files():
    data = _zip(
        {
            "SKILL.md": THIRD_PARTY_MD,
            "scripts/extract.py": "print('extract')\n",
            "scripts/readme.txt": "ignored",
            "reference/api.md": "# API\nlong reference\n",
            "assets/logo.png": b"\x89PNG\r\n",
            "reference/binary.md": b"\xff\xfe\x00bad",
        }
    )

    parsed = sp.parse_skill_package(data, "pdf-toolkit.zip")

    assert parsed["scripts"] == {"extract.py": "print('extract')\n"}
    assert parsed["others"] == {"api.md": "# API\nlong reference\n"}


def test_zip_with_single_top_level_folder_is_still_parsed():
    data = _zip({"pdf-toolkit/SKILL.md": THIRD_PARTY_MD, "pdf-toolkit/scripts/run.py": "x = 1\n"})

    parsed = sp.parse_skill_package(data, "pdf-toolkit.zip")

    assert parsed["procedure"] == THIRD_PARTY_BODY
    assert parsed["scripts"] == {"run.py": "x = 1\n"}


def test_macos_resource_entries_do_not_count_or_confuse_the_parser():
    data = _zip(
        {
            "__MACOSX/._SKILL.md": b"\x00\x05",
            "SKILL.md": THIRD_PARTY_MD,
        }
    )

    assert sp.parse_skill_package(data, "x.zip")["name"] == "pdf-toolkit"


def test_zip_without_skill_md_is_rejected():
    with pytest.raises(ValueError, match=r"SKILL\.md"):
        sp.parse_skill_package(_zip({"notes.md": "hello"}), "x.zip")


def test_zip_path_escape_is_rejected():
    with pytest.raises(ValueError, match="unsafe"):
        sp.parse_skill_package(_zip({"../evil.md": "x", "SKILL.md": THIRD_PARTY_MD}), "x.zip")


def test_oversized_manifest_is_rejected(monkeypatch):
    monkeypatch.setattr(sp, "SKILL_MANIFEST_MAX_BYTES", 64)

    with pytest.raises(ValueError, match="too large"):
        sp.parse_skill_package(THIRD_PARTY_MD.encode(), "SKILL.md")


def test_unpacked_total_over_limit_is_rejected(monkeypatch):
    monkeypatch.setattr(sp, "SKILL_ZIP_MAX_UNPACKED_BYTES", 10)

    with pytest.raises(ValueError, match="unpacked"):
        sp.parse_skill_package(_zip({"SKILL.md": THIRD_PARTY_MD}), "x.zip")


def test_procedure_is_capped_with_marker_free_truncation(monkeypatch):
    monkeypatch.setattr(sp, "SKILL_PROCEDURE_MAX_CHARS", 40)

    parsed = sp.parse_skill_package(THIRD_PARTY_MD.encode(), "SKILL.md")

    assert parsed["procedure"] == THIRD_PARTY_BODY[:40]


def test_auxiliary_file_text_is_capped(monkeypatch):
    monkeypatch.setattr(sp, "SKILL_FILE_TEXT_MAX_CHARS", 8)
    data = _zip({"SKILL.md": THIRD_PARTY_MD, "scripts/a.py": "0123456789abcdef"})

    assert sp.parse_skill_package(data, "x.zip")["scripts"] == {"a.py": "01234567"}


def test_auxiliary_file_count_is_capped(monkeypatch):
    monkeypatch.setattr(sp, "SKILL_AUX_MAX_FILES", 2)
    entries = {"SKILL.md": THIRD_PARTY_MD}
    entries.update({f"scripts/s{i}.py": f"v={i}\n" for i in range(5)})

    assert len(sp.parse_skill_package(_zip(entries), "x.zip")["scripts"]) == 2


def test_upload_path_keeps_full_text_and_attaches_url_and_file_ids(monkeypatch):
    zip_bytes = _zip({"SKILL.md": THIRD_PARTY_MD, "reference/api.md": "# API\n"})

    def fake_download(url, tmp_dir):
        path = tmp_dir / "download.zip"
        path.write_bytes(zip_bytes)
        return path

    monkeypatch.setattr(usm, "_download_zip", fake_download)
    embedder = MagicMock()
    embedder.embed.return_value = [[0.1, 0.2]]
    fast_item = SimpleNamespace(
        metadata=SimpleNamespace(
            file_ids=["f-1"],
            sources=[
                SimpleNamespace(
                    file_info={"file_data": "https://x/files/pdf-toolkit.zip", "file_id": "f-1"}
                )
            ],
        )
    )

    items = usm.process_upload_skill_memory(
        [fast_item], {"user_id": "u1", "session_id": "s1"}, embedder
    )

    assert len(items) == 1
    meta = items[0].metadata
    assert meta.name == "pdf-toolkit"
    assert meta.procedure == THIRD_PARTY_BODY
    assert meta.others == {"api.md": "# API\n"}
    assert meta.url == "https://x/files/pdf-toolkit.zip"
    assert meta.skill_source == "user_upload"
    assert meta.file_ids == ["f-1"]


def test_upload_path_names_a_nameless_skill_after_the_url_file(monkeypatch):
    zip_bytes = _zip({"SKILL.md": "Body only, no front matter.\n"})

    def fake_download(url, tmp_dir):
        path = tmp_dir / "7f3c-random.zip"
        path.write_bytes(zip_bytes)
        return path

    monkeypatch.setattr(usm, "_download_zip", fake_download)
    fast_item = SimpleNamespace(
        metadata=SimpleNamespace(
            file_ids=[],
            sources=[SimpleNamespace(file_info={"file_data": "https://x/files/my-skill.zip"})],
        )
    )

    items = usm.process_upload_skill_memory([fast_item], {"user_id": "u1"}, None)

    assert items[0].metadata.name == "my-skill"


def _skill_memory(source):
    return {
        "name": "pdf-toolkit",
        "description": "Extract text and tables from PDF files",
        "procedure": "p",
        "url": "https://x/a.zip",
        "skill_source": source,
    }


def test_user_upload_embeds_name_and_description():
    embedder = MagicMock()
    embedder.embed.return_value = [[0.0]]

    item = psm.create_skill_memory_item(_skill_memory("user_upload"), {"user_id": "u1"}, embedder)

    embedder.embed.assert_called_once_with(["pdf-toolkit\nExtract text and tables from PDF files"])
    assert item.memory == "Extract text and tables from PDF files"


def test_auto_created_skill_still_embeds_description_only():
    embedder = MagicMock()
    embedder.embed.return_value = [[0.0]]

    psm.create_skill_memory_item(_skill_memory("auto_create"), {"user_id": "u1"}, embedder)

    embedder.embed.assert_called_once_with(["Extract text and tables from PDF files"])

"""T3.1 knowledge base MVP: tenant isolation, storage limits, cleanup."""

import base64
import io
import zipfile

from pathlib import Path

import pytest

from memos.api import knowledge_base
from memos.api.cloud_store import JsonMetadataStore
from memos.api.knowledge_base import KnowledgeBaseService, NoopIngestor, public_file_view


def _service(tmp_path):
    return KnowledgeBaseService(
        store=JsonMetadataStore(tmp_path / "store"),
        storage_dir=tmp_path / "kb",
        ingestor=NoopIngestor(),
    )


def _kb(service, tenant="tenant-1", name="docs"):
    return service.create(user_name=tenant, name=name, owner_user_id=tenant)


def test_create_list_get_and_delete(tmp_path):
    service = _service(tmp_path)
    document = _kb(service)

    assert service.get(user_name="tenant-1", knowledgebase_id=document["entity_id"])
    listed, total = service.list(user_name="tenant-1")
    assert total == 1
    assert listed[0]["name"] == "docs"

    assert service.delete(user_name="tenant-1", knowledgebase_id=document["entity_id"]) is True
    assert service.get(user_name="tenant-1", knowledgebase_id=document["entity_id"]) is None


def test_knowledge_bases_are_tenant_scoped(tmp_path):
    service = _service(tmp_path)
    document = _kb(service, tenant="tenant-1")

    assert service.get(user_name="tenant-2", knowledgebase_id=document["entity_id"]) is None
    assert service.list(user_name="tenant-2") == ([], 0)
    assert service.delete(user_name="tenant-2", knowledgebase_id=document["entity_id"]) is False
    # The original owner still sees it.
    assert service.get(user_name="tenant-1", knowledgebase_id=document["entity_id"])


def test_blank_name_is_rejected(tmp_path):
    service = _service(tmp_path)

    with pytest.raises(ValueError, match="required"):
        service.create(user_name="tenant-1", name="   ")


def test_update_renames_and_replaces_description(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)
    original_updated_at = kb["updated_at"]

    renamed = service.update(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        name="handbook",
        description="ops",
    )

    assert renamed["name"] == "handbook"
    assert renamed["description"] == "ops"
    assert renamed["updated_at"] >= original_updated_at
    assert service.get(user_name="tenant-2", knowledgebase_id=kb["entity_id"]) is None


def test_update_rejects_blank_name(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)

    with pytest.raises(ValueError, match="required"):
        service.update(user_name="tenant-1", knowledgebase_id=kb["entity_id"], name="  ")


def test_upload_stores_bytes_and_updates_stats(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)

    files = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[{"name": "notes.md", "content": "hello kb"}],
    )

    assert len(files) == 1
    stored = Path(files[0]["storage_path"])
    assert stored.read_bytes() == b"hello kb"
    assert files[0]["status"] == "stored"

    refreshed = service.get(user_name="tenant-1", knowledgebase_id=kb["entity_id"])
    assert refreshed["file_count"] == 1
    assert refreshed["total_size"] == len(b"hello kb")


def test_base64_upload_is_decoded(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)

    files = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[{"name": "a.txt", "base64": "aGVsbG8="}],
    )

    assert Path(files[0]["storage_path"]).read_bytes() == b"hello"


def test_unsupported_extension_is_rejected_before_writing(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)

    with pytest.raises(ValueError, match="unsupported file type"):
        service.add_files(
            user_name="tenant-1",
            knowledgebase_id=kb["entity_id"],
            files=[{"name": "malware.exe", "content": "x"}],
        )
    assert service.list_files(user_name="tenant-1", knowledgebase_id=kb["entity_id"]) == ([], 0)


def test_upload_count_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_MAX_FILES_PER_UPLOAD", "2")
    service = _service(tmp_path)
    kb = _kb(service)

    with pytest.raises(ValueError, match="at most 2"):
        service.add_files(
            user_name="tenant-1",
            knowledgebase_id=kb["entity_id"],
            files=[{"name": f"{i}.txt", "content": "x"} for i in range(3)],
        )


def test_per_file_size_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_MAX_FILE_SIZE_MB", "1")
    service = _service(tmp_path)
    kb = _kb(service)

    with pytest.raises(ValueError, match="1 MB"):
        service.add_files(
            user_name="tenant-1",
            knowledgebase_id=kb["entity_id"],
            files=[{"name": "big.txt", "content": b"x" * (1024 * 1024 + 1)}],
        )


def test_page_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("KB_MAX_FILE_PAGES", "500")
    service = _service(tmp_path)
    kb = _kb(service)

    with pytest.raises(ValueError, match="500 page"):
        service.add_files(
            user_name="tenant-1",
            knowledgebase_id=kb["entity_id"],
            files=[{"name": "big.pdf", "content": b"%PDF", "pages": 501}],
        )


def test_upload_to_foreign_kb_is_rejected(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service, tenant="tenant-1")

    with pytest.raises(ValueError, match="not found"):
        service.add_files(
            user_name="tenant-2",
            knowledgebase_id=kb["entity_id"],
            files=[{"name": "a.txt", "content": "x"}],
        )


def test_path_traversal_in_filename_is_neutralised(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)

    files = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[{"name": "../../etc/passwd.txt", "content": "x"}],
    )

    stored = Path(files[0]["storage_path"])
    assert files[0]["name"] == "passwd.txt"
    assert (tmp_path / "kb") in stored.parents


def test_list_files_filters_and_paginates(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)
    service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[{"name": f"{i}.txt", "content": "x"} for i in range(5)],
    )

    page, total = service.list_files(
        user_name="tenant-1", knowledgebase_id=kb["entity_id"], page=2, page_size=2
    )
    assert total == 5
    assert len(page) == 2

    filtered, total = service.list_files(user_name="tenant-1", file_type="manual")
    assert (filtered, total) == ([], 0)


def test_delete_file_removes_bytes_and_stats(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)
    file_doc = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[{"name": "a.txt", "content": "x"}],
    )[0]

    assert service.delete_files(user_name="tenant-1", file_ids=[file_doc["entity_id"]]) == 1

    assert not Path(file_doc["storage_path"]).exists()
    assert service.get_file(user_name="tenant-1", file_id=file_doc["entity_id"]) is None
    assert service.get(user_name="tenant-1", knowledgebase_id=kb["entity_id"])["file_count"] == 0


def test_delete_kb_removes_its_files_only(tmp_path):
    service = _service(tmp_path)
    kb1 = _kb(service, name="one")
    kb2 = _kb(service, name="two")
    file1 = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb1["entity_id"],
        files=[{"name": "a.txt", "content": "x"}],
    )[0]
    file2 = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb2["entity_id"],
        files=[{"name": "b.txt", "content": "y"}],
    )[0]

    service.delete(user_name="tenant-1", knowledgebase_id=kb1["entity_id"])

    assert not Path(file1["storage_path"]).exists()
    assert Path(file2["storage_path"]).exists()
    assert service.get_file(user_name="tenant-1", file_id=file2["entity_id"])


def test_download_reads_bytes_for_the_owner_only(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)
    file_doc = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[{"name": "a.txt", "content": "payload"}],
    )[0]

    content, document = service.read_file(user_name="tenant-1", file_id=file_doc["entity_id"])
    assert content == b"payload"
    assert document["name"] == "a.txt"
    assert service.read_file(user_name="tenant-2", file_id=file_doc["entity_id"]) is None


def test_remote_url_is_not_fetched_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("KB_FETCH_REMOTE_FILES", raising=False)
    service = _service(tmp_path)
    kb = _kb(service)

    file_doc = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[{"name": "remote.txt", "content": "https://example.com/a.txt"}],
    )[0]

    assert Path(file_doc["storage_path"]).read_bytes() == b""
    assert file_doc["source_url"] == "https://example.com/a.txt"


def test_noop_ingestor_reports_stored_without_chunks():
    result = NoopIngestor().ingest(
        user_name="tenant-1", knowledgebase={"entity_id": "kb_1"}, file={}, content=b"x"
    )

    assert result["status"] == "stored"
    assert result["chunks"] == 0


def test_public_file_view_shape(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)
    file_doc = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[{"name": "a.txt", "content": "1234"}],
    )[0]

    view = public_file_view(file_doc)

    assert view["id"] == file_doc["entity_id"]
    assert view["name"] == "a.txt"
    assert view["size"] == 4
    assert view["sizeMB"] == pytest.approx(0.000004, abs=1e-9)


def test_batch_is_validated_before_any_file_is_written(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)

    with pytest.raises(ValueError, match="unsupported file type"):
        service.add_files(
            user_name="tenant-1",
            knowledgebase_id=kb["entity_id"],
            files=[
                {"name": "good.txt", "content": "hello"},
                {"name": "evil.exe", "content": "nope"},
            ],
        )

    listed, total = service.list_files(user_name="tenant-1", knowledgebase_id=kb["entity_id"])
    assert (listed, total) == ([], 0)
    assert list((tmp_path / "kb").rglob("*.*")) == []
    assert service.get(user_name="tenant-1", knowledgebase_id=kb["entity_id"])["file_count"] == 0


def test_url_only_file_derives_its_extension(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)

    [document] = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[{"name": "spec", "url": "https://example.com/docs/spec.pdf"}],
    )

    assert document["name"] == "spec.pdf"
    assert document["ext"] == "pdf"


def test_private_urls_are_refused(tmp_path, monkeypatch):
    from memos.api.knowledge_base import _is_public_url

    monkeypatch.delenv("KB_ALLOW_PRIVATE_URLS", raising=False)
    assert _is_public_url("http://127.0.0.1/secret") is False
    assert _is_public_url("http://10.0.0.1/secret") is False


def test_read_file_refuses_paths_outside_the_storage_root(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)
    [document] = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[{"name": "a.txt", "content": "hello"}],
    )
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    document = service.store.get("knowledgebase_file", document["entity_id"])
    document["storage_path"] = str(outside)
    service.store.put("knowledgebase_file", document)

    assert service.read_file(user_name="tenant-1", file_id=document["entity_id"]) is None


def test_remote_fetch_requires_an_explicit_host_allowlist(monkeypatch):
    from memos.api.knowledge_base import _remote_host_allowed

    monkeypatch.setenv("KB_REMOTE_ALLOWED_HOSTS", "files.example.com")
    assert _remote_host_allowed("https://files.example.com/a.pdf") is True
    assert _remote_host_allowed("https://evil.example.com/a.pdf") is False

    monkeypatch.delenv("KB_REMOTE_ALLOWED_HOSTS")
    assert _remote_host_allowed("https://files.example.com/a.pdf") is False


def test_read_file_refuses_files_over_the_size_limit(tmp_path, monkeypatch):
    service = _service(tmp_path)
    kb = _kb(service)
    [file_doc] = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[{"name": "a.txt", "content": "x"}],
    )
    stored = Path(file_doc["storage_path"])
    stored.write_bytes(b"x" * (1024 * 1024 + 1))
    monkeypatch.setenv("KB_MAX_FILE_SIZE_MB", "1")

    with pytest.raises(ValueError, match="1 MB download limit"):
        service.read_file(user_name="tenant-1", file_id=file_doc["entity_id"])


# ---- skill packages ---------------------------------------------------------------------


SKILL_MD = "---\nname: pdf-tools\ndescription: Work with PDF files\n---\n\n# PDF tools\n"


def _zip_bytes(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry, data in entries.items():
            archive.writestr(entry, data)
    return buffer.getvalue()


def _upload_skill(tmp_path, name, content, **extra):
    service = _service(tmp_path)
    kb = _kb(service)
    return service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[{"name": name, "bytes": content}],
        file_type="skill",
        **extra,
    )


def test_skill_zip_with_root_manifest_is_accepted(tmp_path):
    package = _zip_bytes({"SKILL.md": SKILL_MD, "scripts/run.py": "print(1)"})

    [doc] = _upload_skill(tmp_path, "pdf-tools.zip", package)

    assert doc["file_type"] == "skill"
    assert (doc["skill_name"], doc["skill_description"]) == ("pdf-tools", "Work with PDF files")
    assert Path(doc["storage_path"]).read_bytes() == package
    assert public_file_view(doc)["skill_name"] == "pdf-tools"


def test_skill_zip_with_a_top_level_folder_is_rejected(tmp_path):
    package = _zip_bytes({"pdf-tools/SKILL.md": SKILL_MD, "pdf-tools/ref.md": "x"})

    with pytest.raises(ValueError, match="first level"):
        _upload_skill(tmp_path, "pdf-tools.zip", package)


def test_macos_resource_entries_are_ignored_and_not_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "SKILL_ZIP_MAX_ENTRIES", 2)
    package = _zip_bytes(
        {
            "SKILL.md": SKILL_MD,
            "ref.md": "x",
            "__MACOSX/._SKILL.md": "junk",
            "__MACOSX/._ref.md": "junk",
        }
    )

    assert _upload_skill(tmp_path, "s.zip", package)[0]["skill_name"] == "pdf-tools"


def test_directory_entries_are_not_counted_as_files(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "SKILL_ZIP_MAX_ENTRIES", 2)
    package = _zip_bytes({"SKILL.md": SKILL_MD, "scripts/": "", "scripts/run.py": "print(1)"})

    assert _upload_skill(tmp_path, "s.zip", package)[0]["skill_name"] == "pdf-tools"


def test_standalone_skill_md_is_accepted(tmp_path):
    [doc] = _upload_skill(tmp_path, "SKILL.md", SKILL_MD.encode())

    assert doc["skill_name"] == "pdf-tools"
    assert doc["ext"] == "md"


def test_a_standalone_markdown_skill_may_have_any_file_name(tmp_path):
    [doc] = _upload_skill(tmp_path, "pdf-notes.md", SKILL_MD.encode())

    assert doc["skill_name"] == "pdf-tools"


def test_plain_files_have_no_skill_fields(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)

    [doc] = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[{"name": "notes.md", "content": "hi"}],
    )

    assert "skill_name" not in doc
    assert "skill_name" not in public_file_view(doc)


def test_zip_is_only_accepted_for_skill_uploads(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)

    with pytest.raises(ValueError, match="unsupported file type zip"):
        service.add_files(
            user_name="tenant-1",
            knowledgebase_id=kb["entity_id"],
            files=[{"name": "a.zip", "bytes": _zip_bytes({"SKILL.md": SKILL_MD})}],
        )


@pytest.mark.parametrize(
    "name,content,message",
    [
        ("notes.txt", b"hello", "must be a .zip package or a .md file"),
        ("README.md", b"# no front matter", "front matter"),
        ("bad.zip", b"not a zip", "not a valid zip"),
        ("empty.zip", _zip_bytes({}), "SKILL.md must be at the first level"),
        (
            "deep.zip",
            _zip_bytes({"a/b/SKILL.md": SKILL_MD}),
            "SKILL.md must be at the first level",
        ),
        (
            "mixed.zip",
            _zip_bytes({"pdf/SKILL.md": SKILL_MD, "stray.txt": "x"}),
            "SKILL.md must be at the first level",
        ),
        ("slip.zip", _zip_bytes({"SKILL.md": SKILL_MD, "../evil.sh": "x"}), "escapes"),
        ("abs.zip", _zip_bytes({"SKILL.md": SKILL_MD, "/etc/passwd": "x"}), "escapes"),
        ("win.zip", _zip_bytes({"SKILL.md": SKILL_MD, "..\\evil.sh": "x"}), "escapes"),
        ("nofm.zip", _zip_bytes({"SKILL.md": "# just markdown"}), "front matter"),
        ("noname.zip", _zip_bytes({"SKILL.md": "---\ndescription: d\n---\n"}), "non-empty name"),
        (
            "nodesc.zip",
            _zip_bytes({"SKILL.md": "---\nname: n\ndescription: '  '\n---\n"}),
            "non-empty description",
        ),
        ("list.zip", _zip_bytes({"SKILL.md": "---\n- a\n- b\n---\n"}), "non-empty name"),
        ("yaml.zip", _zip_bytes({"SKILL.md": "---\nname: [oops\n---\n"}), "invalid SKILL.md"),
        (
            "longname.zip",
            _zip_bytes({"SKILL.md": f"---\nname: {'n' * 65}\ndescription: d\n---\n"}),
            "longer than 64",
        ),
        (
            "bigmd.zip",
            _zip_bytes({"SKILL.md": SKILL_MD + "x" * (100 * 1024)}),
            "exceeds 100 KB",
        ),
    ],
)
def test_invalid_skill_uploads_are_rejected(tmp_path, name, content, message):
    with pytest.raises(ValueError, match=message):
        _upload_skill(tmp_path, name, content)


def test_skill_zip_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_base, "SKILL_ZIP_MAX_ENTRIES", 2)
    crowded = _zip_bytes({"SKILL.md": SKILL_MD, "a": "1", "b": "2"})
    with pytest.raises(ValueError, match="more than 2 files"):
        _upload_skill(tmp_path, "crowded.zip", crowded)

    monkeypatch.setattr(knowledge_base, "SKILL_ZIP_MAX_ENTRIES", 200)
    monkeypatch.setattr(knowledge_base, "SKILL_ZIP_MAX_FILE_BYTES", 1024)
    fat = _zip_bytes({"SKILL.md": SKILL_MD, "scripts/big.py": "0" * 2048})
    with pytest.raises(ValueError, match=r"scripts/big\.py.*per-file limit"):
        _upload_skill(tmp_path, "fat.zip", fat)
    monkeypatch.setattr(knowledge_base, "SKILL_ZIP_MAX_FILE_BYTES", 10 * 1024 * 1024)

    monkeypatch.setattr(knowledge_base, "SKILL_ZIP_MAX_UNPACKED_BYTES", 50)
    bomb = _zip_bytes({"SKILL.md": SKILL_MD, "big.txt": "0" * 4096})
    with pytest.raises(ValueError, match="unpacks to more than"):
        _upload_skill(tmp_path, "bomb.zip", bomb)

    monkeypatch.setattr(knowledge_base, "SKILL_ZIP_MAX_BYTES", 10)
    with pytest.raises(ValueError, match="skill limit"):
        _upload_skill(tmp_path, "huge.zip", _zip_bytes({"SKILL.md": SKILL_MD}))


def test_encrypted_and_symlink_entries_are_rejected(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SKILL.md", SKILL_MD)
        link = zipfile.ZipInfo("link")
        link.external_attr = 0o120777 << 16
        archive.writestr(link, "/etc/passwd")
    with pytest.raises(ValueError, match="symbolic link"):
        _upload_skill(tmp_path, "link.zip", buffer.getvalue())

    raw = bytearray(_zip_bytes({"SKILL.md": SKILL_MD}))
    for marker in (b"PK\x03\x04", b"PK\x01\x02"):
        offset = bytes(raw).index(marker) + (6 if marker == b"PK\x03\x04" else 8)
        raw[offset] |= 0x01
    with pytest.raises(ValueError, match="encrypted"):
        _upload_skill(tmp_path, "locked.zip", bytes(raw))


def test_bad_skill_in_a_batch_writes_nothing(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)

    with pytest.raises(ValueError):
        service.add_files(
            user_name="tenant-1",
            knowledgebase_id=kb["entity_id"],
            files=[
                {"name": "ok.zip", "bytes": _zip_bytes({"SKILL.md": SKILL_MD})},
                {"name": "bad.zip", "bytes": b"nope"},
            ],
            file_type="skill",
        )

    assert service.list_files(user_name="tenant-1", knowledgebase_id=kb["entity_id"])[1] == 0


def test_each_file_declares_its_own_type_and_a_batch_may_mix_documents_and_skills(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)

    docs = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[
            {"name": "SKILL.md", "bytes": SKILL_MD.encode(), "type": "skill"},
            {"name": "notes.txt", "bytes": b"hello", "type": "document"},
            {"name": "plain.txt", "bytes": b"hi"},
        ],
    )

    assert [d["file_type"] for d in docs] == ["skill", "document", None]
    assert docs[0]["skill_name"] == "pdf-tools" and "skill_name" not in docs[1]


def test_a_files_own_type_beats_the_request_level_one_and_unknown_types_are_rejected(tmp_path):
    service = _service(tmp_path)
    kb = _kb(service)
    args = {"user_name": "tenant-1", "knowledgebase_id": kb["entity_id"]}

    [doc] = service.add_files(
        **args, files=[{"name": "n.txt", "bytes": b"x", "type": "document"}], file_type="skill"
    )
    assert doc["file_type"] == "document"
    with pytest.raises(ValueError, match="unsupported file type"):
        service.add_files(**args, files=[{"name": "n.txt", "bytes": b"x", "type": "video"}])


def test_base64_content_is_decoded_as_a_data_url_or_for_binary_formats(tmp_path):
    package = _zip_bytes({"SKILL.md": SKILL_MD})
    encoded = base64.b64encode(package).decode()
    service = _service(tmp_path)
    kb = _kb(service)

    docs = service.add_files(
        user_name="tenant-1",
        knowledgebase_id=kb["entity_id"],
        files=[
            {"name": "a.zip", "content": encoded, "type": "skill"},
            {"name": "b.zip", "content": f"data:application/zip;base64,{encoded}", "type": "skill"},
            {
                "name": "SKILL.md",
                "content": "data:text/markdown;base64,"
                + base64.b64encode(SKILL_MD.encode()).decode(),
                "type": "skill",
            },
            {"name": "plain.txt", "content": "1234"},
            {"name": "notes.pdf", "content": "test"},
        ],
    )

    assert [Path(d["storage_path"]).read_bytes() for d in docs] == [
        package,
        package,
        SKILL_MD.encode(),
        b"1234",
        b"test",
    ]

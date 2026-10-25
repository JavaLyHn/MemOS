"""Tests for skill file storage: per-user layout, atomic publish, safe deletes, unique names."""

import hashlib
import zipfile

from pathlib import Path

import pytest

from memos.mem_reader.read_skill_memory import process_skill_memory as psm
from memos.mem_reader.read_skill_memory import skill_package as sp
from memos.mem_reader.read_skill_memory import skill_store as store


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    monkeypatch.delenv("FILE_LOCAL_PATH", raising=False)
    monkeypatch.delenv("SKILLS_DOWNLOAD_BASE_URL", raising=False)
    monkeypatch.setenv("SKILLS_REPO_BACKEND", "LOCAL")
    config = {
        "skills_local_tmp_dir": str(tmp_path / "tmp"),
        "skills_local_dir": str(tmp_path / "local"),
        "skills_oss_dir": "skill_memory/",
    }
    return tmp_path, config


def _make_zip(path: Path, body: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("s/SKILL.md", f"---\nname: s\ndescription: d\n---\n{body}")
    return path


def test_user_dir_is_a_stable_hash_without_path_characters():
    assert store.user_dir_name("../evil") == hashlib.sha256(b"../evil").hexdigest()[:16]
    assert store.user_dir_name("u1") == store.user_dir_name("u1")
    assert store.user_dir_name("u1") != store.user_dir_name("u2")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("Weekly Report", "weekly_report"), ("pdf-toolkit_v2.1", "pdf-toolkit_v2.1")],
)
def test_slug_keeps_ascii_names_recognisable(raw, expected):
    assert store.skill_slug(raw) == expected


@pytest.mark.parametrize(
    "raw", ["../../etc/passwd", "..", ".", "周报生成", "", "a\nb/../c", "x" * 200]
)
def test_slug_is_always_a_safe_single_path_segment(raw):
    slug = store.skill_slug(raw)

    assert slug
    assert "/" not in slug
    assert "\\" not in slug
    assert ".." not in slug
    assert not slug.startswith(".")
    assert len(slug) <= 48


def test_unique_zip_name_differs_between_calls():
    names = {store.unique_zip_name("report") for _ in range(20)}

    assert len(names) == 20
    assert all(n.startswith("report-") and n.endswith(".zip") for n in names)


def test_local_publish_writes_under_download_root_and_url_matches_path(dirs, monkeypatch):
    tmp_path, config = dirs
    serve_root = tmp_path / "files"
    monkeypatch.setenv("FILE_LOCAL_PATH", str(serve_root))
    monkeypatch.setenv("SKILLS_DOWNLOAD_BASE_URL", "http://memos.example:8001/")
    src = _make_zip(tmp_path / "work" / "report-ab12cd34.zip")

    url = store.publish_local_skill(src, "u1", config)

    udir = store.user_dir_name("u1")
    target = serve_root / "skills" / udir / "report-ab12cd34.zip"
    assert url == f"http://memos.example:8001/download/skills/{udir}/report-ab12cd34.zip"
    assert target.read_bytes() == src.read_bytes()
    assert list(target.parent.glob("*.part")) == []


def test_local_publish_without_file_local_path_uses_skills_local_dir(dirs):
    tmp_path, config = dirs
    src = _make_zip(tmp_path / "work" / "a-11111111.zip")

    url = store.publish_local_skill(src, "u1", config)

    udir = store.user_dir_name("u1")
    assert url.endswith(f"/download/{udir}/a-11111111.zip")
    assert (tmp_path / "local" / udir / "a-11111111.zip").is_file()


def test_two_users_with_the_same_file_name_do_not_overwrite_each_other(dirs):
    tmp_path, config = dirs
    one = _make_zip(tmp_path / "w1" / "same.zip", "one")
    two = _make_zip(tmp_path / "w2" / "same.zip", "two")

    store.publish_local_skill(one, "u1", config)
    store.publish_local_skill(two, "u2", config)

    root = tmp_path / "local"
    assert (root / store.user_dir_name("u1") / "same.zip").read_bytes() == one.read_bytes()
    assert (root / store.user_dir_name("u2") / "same.zip").read_bytes() == two.read_bytes()


def test_publish_replaces_an_existing_target_whole(dirs):
    tmp_path, config = dirs
    old = _make_zip(tmp_path / "w1" / "same.zip", "old")
    new = _make_zip(tmp_path / "w2" / "same.zip", "new body that is longer")
    store.publish_local_skill(old, "u1", config)

    store.publish_local_skill(new, "u1", config)

    target = tmp_path / "local" / store.user_dir_name("u1") / "same.zip"
    assert target.read_bytes() == new.read_bytes()
    assert list(target.parent.glob("*.part")) == []


def test_local_path_for_url_round_trips_and_guards_owner(dirs):
    tmp_path, config = dirs
    url = store.publish_local_skill(_make_zip(tmp_path / "w" / "a-1.zip"), "u1", config)

    assert store.local_path_for_url(url, "u1", config) == (
        tmp_path / "local" / store.user_dir_name("u1") / "a-1.zip"
    )
    assert store.local_path_for_url(url, "u2", config) is None


@pytest.mark.parametrize(
    "tail",
    ["{udir}/a.txt", "{udir}/../other/a.zip", "{udir}/sub/a.zip", "someone-else/a.zip", "a.zip"],
)
def test_local_path_for_url_rejects_unsafe_or_foreign_urls(dirs, tail):
    _, config = dirs
    udir = store.user_dir_name("u1")

    url = "http://h:8000/download/" + tail.format(udir=udir)

    assert store.local_path_for_url(url, "u1", config) is None


def test_local_path_for_url_rejects_paths_outside_the_download_prefix(dirs):
    _, config = dirs
    udir = store.user_dir_name("u1")

    assert store.local_path_for_url(f"http://h/other/{udir}/a.zip", "u1", config) is None
    assert store.local_path_for_url("", "u1", config) is None


def test_delete_local_skill_url_removes_only_the_owners_file(dirs):
    tmp_path, config = dirs
    mine = store.publish_local_skill(_make_zip(tmp_path / "w1" / "a.zip"), "u1", config)
    theirs = store.publish_local_skill(_make_zip(tmp_path / "w2" / "a.zip"), "u2", config)

    assert store.delete_local_skill_url(theirs, "u1", config) is False
    assert (tmp_path / "local" / store.user_dir_name("u2") / "a.zip").is_file()
    assert store.delete_local_skill_url(mine, "u1", config) is True
    assert not (tmp_path / "local" / store.user_dir_name("u1") / "a.zip").exists()
    assert store.delete_local_skill_url(mine, "u1", config) is False


def test_oss_key_uses_a_safe_user_segment():
    assert store.oss_key("skill_memory/", "u1", "a.zip") == "skill_memory/u1/a.zip"
    key = store.oss_key("skill_memory/", "../other", "a.zip")
    assert key.startswith("skill_memory/")
    assert ".." not in key
    assert key.count("/") == 2


def test_oss_key_for_url_checks_prefix_owner_and_suffix():
    base = "https://bkt.oss-cn.aliyuncs.com/"

    assert (
        store.oss_key_for_url(base + "skill_memory/u1/a-1.zip", "skill_memory/", "u1")
        == "skill_memory/u1/a-1.zip"
    )
    assert store.oss_key_for_url(base + "skill_memory/u2/a.zip", "skill_memory/", "u1") is None
    assert store.oss_key_for_url(base + "skill_memory/u1/a.txt", "skill_memory/", "u1") is None
    assert store.oss_key_for_url(base + "skill_memory/u1/x/a.zip", "skill_memory/", "u1") is None
    assert store.oss_key_for_url("", "skill_memory/", "u1") is None


def _skill(name="Weekly Report", **extra):
    return {"name": name, "description": "Build weekly reports", "procedure": "1. do it", **extra}


def test_write_skills_to_file_stays_inside_tmp_root_and_names_are_unique(dirs):
    tmp_path, config = dirs
    info = {"user_id": "../../escape"}

    first = Path(psm._write_skills_to_file(_skill("../../Evil Skill"), info, config))
    second = Path(psm._write_skills_to_file(_skill("../../Evil Skill"), info, config))

    root = (tmp_path / "tmp").resolve()
    assert first.resolve().is_relative_to(root)
    assert second.resolve().is_relative_to(root)
    assert first.name != second.name
    assert first.exists()
    assert second.exists()


def test_write_skills_to_file_keeps_ascii_names_and_front_matter_valid(dirs):
    _, config = dirs

    zip_path = Path(psm._write_skills_to_file(_skill("Weekly\nReport"), {"user_id": "u1"}, config))

    parsed = sp.parse_skill_package(zip_path.read_bytes(), zip_path.name)
    assert parsed["name"] == "weekly_report"
    assert parsed["description"] == "Build weekly reports"
    assert zip_path.name.startswith("weekly_report-")


def test_upload_local_returns_a_url_that_matches_the_file(dirs, monkeypatch):
    tmp_path, config = dirs
    monkeypatch.setenv("FILE_LOCAL_PATH", str(tmp_path / "files"))
    zip_path = Path(psm._write_skills_to_file(_skill(), {"user_id": "u1"}, config))

    url = psm._upload_skills(
        skills_repo_backend="LOCAL",
        skills_oss_dir=config["skills_oss_dir"],
        local_tmp_file_path=str(zip_path),
        local_save_file_path=config["skills_local_dir"],
        client=None,
        user_id="u1",
    )

    published = store.local_path_for_url(url, "u1", config)
    assert published is not None
    assert published.is_file()
    assert published.parent.parent.name == "skills"


def _publish(config, skill_memory, zip_path, user_id="u1"):
    return psm._publish_skill(
        skill_memory,
        str(zip_path),
        skills_repo_backend="LOCAL",
        oss_client=None,
        skills_dir_config=config,
        user_id=user_id,
    )


def test_first_publish_sets_url_and_cleans_tmp_files(dirs, monkeypatch):
    tmp_path, config = dirs
    monkeypatch.setenv("FILE_LOCAL_PATH", str(tmp_path / "files"))
    skill = _skill()
    zip_path = Path(psm._write_skills_to_file(skill, {"user_id": "u1"}, config))

    ok = _publish(config, skill, zip_path)

    assert ok is True
    assert store.local_path_for_url(skill["url"], "u1", config).is_file()
    assert not zip_path.exists()
    assert not (zip_path.parent / zip_path.stem).exists()


def test_update_publishes_the_new_file_and_leaves_the_old_one_to_the_caller(dirs, monkeypatch):
    tmp_path, config = dirs
    monkeypatch.setenv("FILE_LOCAL_PATH", str(tmp_path / "files"))
    old_zip = Path(psm._write_skills_to_file(_skill(), {"user_id": "u1"}, config))
    old_skill = _skill()
    _publish(config, old_skill, old_zip)
    old_path = store.local_path_for_url(old_skill["url"], "u1", config)
    new_skill = _skill(update=True, old_memory_id="m-old")
    new_zip = Path(psm._write_skills_to_file(new_skill, {"user_id": "u1"}, config))

    ok = _publish(config, new_skill, new_zip)

    assert ok is True
    assert new_skill["url"] != old_skill["url"]
    assert store.local_path_for_url(new_skill["url"], "u1", config).is_file()
    assert old_path.is_file()


def test_update_whose_upload_fails_keeps_old_file_and_node(dirs, monkeypatch):
    tmp_path, config = dirs
    monkeypatch.setenv("FILE_LOCAL_PATH", str(tmp_path / "files"))
    old_zip = Path(psm._write_skills_to_file(_skill(), {"user_id": "u1"}, config))
    old_skill = _skill()
    _publish(config, old_skill, old_zip)
    old_path = store.local_path_for_url(old_skill["url"], "u1", config)
    new_skill = _skill(update=True, old_memory_id="m-old")
    new_zip = Path(psm._write_skills_to_file(new_skill, {"user_id": "u1"}, config))

    def boom(**_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(psm, "_upload_skills", boom)

    ok = _publish(config, new_skill, new_zip)

    assert ok is False
    assert old_path.is_file()
    assert not new_zip.exists()


def test_first_publish_failure_still_returns_the_skill_with_an_empty_url(dirs, monkeypatch):
    _, config = dirs
    skill = _skill()
    zip_path = Path(psm._write_skills_to_file(skill, {"user_id": "u1"}, config))

    def boom(**_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(psm, "_upload_skills", boom)

    assert _publish(config, skill, zip_path) is True
    assert skill["url"] == ""


def test_write_skills_to_file_clamps_script_and_reference_names_to_the_skill_dir(dirs):
    tmp_path, config = dirs
    skill = _skill(
        scripts={"../../escape.py": "print(1)\n"},
        others={"../../notes.md": "# notes\n"},
    )

    zip_path = Path(psm._write_skills_to_file(skill, {"user_id": "u1"}, config))

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
    assert any(n.endswith("scripts/escape.py") for n in names)
    assert any(n.endswith("reference/notes.md") for n in names)
    assert not any(".." in n for n in names)
    assert not (tmp_path / "escape.py").exists()

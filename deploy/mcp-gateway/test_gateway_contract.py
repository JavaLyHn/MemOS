#!/usr/bin/env python3
"""网关契约锁：工具名 / 签名 / docstring / 对外文案都不能 silently drift。

不依赖 fastmcp、也不起服务。改工具描述（那是 prompt 的一部分）或对外错误文案，本测试会红。

    python3 test_gateway_contract.py
"""
from __future__ import annotations

import ast
import hashlib
import pathlib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
TOOLS = HERE / "gateway" / "mcp_api" / "tools.py"
HTTP = HERE / "gateway" / "mcp_api" / "http.py"
APP = HERE / "gateway" / "app.py"
CONFIG = HERE / "gateway" / "config.py"
ERRORS = HERE / "gateway" / "errors.py"
IDENTITY = HERE / "gateway" / "identity.py"
BACKEND = HERE / "gateway" / "backend.py"
SERVICE = HERE / "gateway" / "service.py"
SHAPE = HERE / "gateway" / "domain" / "shape.py"
SESSION = HERE / "gateway" / "domain" / "session.py"
TENANTS = HERE / "gateway" / "domain" / "tenants.py"


def _mod(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _fn(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"找不到函数 {name}")


def _doc(fn: ast.FunctionDef) -> str:
    return ast.get_docstring(fn, clean=False) or ""


def _ann(node) -> str:
    if node is None:
        return ""
    return ast.unparse(node)


def _args_sig(fn: ast.FunctionDef) -> list[tuple]:
    a = fn.args
    n_pos = len(a.args)
    n_defaults = len(a.defaults)
    defaults = [None] * (n_pos - n_defaults) + list(a.defaults)
    out = []
    for arg, default in zip(a.args, defaults):
        if arg.arg in {"self", "cls"}:
            continue
        out.append((arg.arg, _ann(arg.annotation), ast.unparse(default) if default is not None else "MISSING"))
    return out


class Contract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tools = _mod(TOOLS)
        cls.http = _mod(HTTP)
        cls.app = _mod(APP)
        cls.config = _mod(CONFIG)
        cls.errors = _mod(ERRORS)
        cls.identity = _mod(IDENTITY)
        cls.backend = _mod(BACKEND)
        cls.service = _mod(SERVICE)
        cls.shape = _mod(SHAPE)
        cls.session = _mod(SESSION)
        cls.tenants = _mod(TENANTS)

    def test_five_tools_in_order(self):
        want = ["add_message", "search_memory", "delete_memory", "add_feedback", "get_user_profile"]
        funcs = [n for n in self.tools.body if isinstance(n, ast.FunctionDef) and n.name in want]
        self.assertEqual([f.name for f in funcs], want)

    def test_tool_signatures(self):
        expected = {
            "add_message": [
                ("conversation_first_message", "str", "MISSING"),
                ("messages", "list[dict | str] | str", "MISSING"),
                ("tags", "list[str] | None", "None"),
            ],
            "search_memory": [
                ("query", "str", "MISSING"),
                ("filter", "dict | None", "None"),
                ("top_k", "int", "10"),
                ("conversation_first_message", "str | None", "None"),
            ],
            "delete_memory": [
                ("memory_ids", "list[str]", "MISSING"),
            ],
            "add_feedback": [
                ("feedback_content", "str", "MISSING"),
                ("conversation_first_message", "str", "''"),
                ("retrieved_memory_ids", "list[str] | None", "None"),
            ],
            "get_user_profile": [
                ("include_preference", "bool", "True"),
                ("include_tool_memory", "bool", "False"),
                ("current", "int", "1"),
                ("size", "int", "20"),
            ],
        }
        for name, sig in expected.items():
            fn = _fn(self.tools, name)
            self.assertEqual(_args_sig(fn), sig, msg=name)
            self.assertEqual(_ann(fn.returns), "str", msg=name)

    def test_tool_docstrings_locked(self):
        expected = {
            "add_message": "02b01bc4190c987ddf4d77d27e0fcab23c15b516ab90dcbf0a59d1afd7ac0346",
            "search_memory": "7c0bc42265e1f714c28ef66c340c29bfcda899813d9c4f741f79edb0f4148d06",
            "delete_memory": "cd7397129df0df2cad2daca268a1b559bca69436dd13c22df33934a371cc38f6",
            "add_feedback": "cd3e4133711f5ef7e17eb76c54bc4f23db22e31b9890a8893bd1907a5d4d4812",
            "get_user_profile": "d23f0ef07b38ba1ebceb329333830f06c2525bd27696adff82b7cb9f62122994",
        }
        for name, digest in expected.items():
            doc = _doc(_fn(self.tools, name))
            got = hashlib.sha256(doc.encode()).hexdigest()
            self.assertEqual(got, digest, msg=f"{name} docstring 已漂移（{len(doc)} bytes）")

    def test_instructions_and_service_name_default(self):
        src = APP.read_text(encoding="utf-8")
        self.assertIn("长期记忆服务。回答用户前先调用 search_memory 检索相关记忆；", src)
        self.assertIn("写入只沉淀可泛化的口径/规则/流程/偏好，个案判定结论与过程流水不要写入；", src)
        cfg = CONFIG.read_text(encoding="utf-8")
        self.assertIn('os.getenv("MEMORY_SERVICE_NAME", "MemoryService")', cfg)

    def test_no_memos_leak_in_user_facing_strings(self):
        blobs = [
            HTTP.read_text(encoding="utf-8"),
            APP.read_text(encoding="utf-8"),
            ERRORS.read_text(encoding="utf-8"),
            IDENTITY.read_text(encoding="utf-8"),
        ]
        for blob in blobs:
            self.assertNotRegex(blob, r"(?i)memtensor")
        self.assertIn("<title>长期记忆服务</title>", HTTP.read_text(encoding="utf-8"))
        self.assertIn("暂时连不上记忆服务，请稍后重试。", BACKEND.read_text(encoding="utf-8"))
        # 对外文案里不要写死后端地址（地址一律由 MEMOS_API_BASE_URL 注入）
        for src in (IDENTITY, ERRORS, HTTP):
            self.assertNotRegex(
                src.read_text(encoding="utf-8"),
                r"://[a-z0-9][a-z0-9.-]*:\d{4}",
                msg=f"{src.name} 里写死了后端地址",
            )

    def test_session_hash_stable(self):
        src = ast.get_source_segment(
            SESSION.read_text(encoding="utf-8"),
            _fn(self.session, "session_id_from_first_message"),
        )
        ns = {}
        exec("import hashlib\n" + src, ns)
        fn = ns["session_id_from_first_message"]
        self.assertEqual(fn("hello"), "conv_" + hashlib.sha1(b"hello").hexdigest()[:16])
        self.assertEqual(fn("  hello  "), fn("hello"))
        self.assertEqual(fn(""), "")
        self.assertEqual(fn("   "), "")

    def test_parse_tenants_compact_and_json(self):
        src = TENANTS.read_text(encoding="utf-8")
        ns = {}
        exec(compile(self.tenants, str(TENANTS), "exec"), ns)
        parse = ns["parse_tenants"]
        compact = parse("tok-a:alice,tok-b:bob")
        self.assertEqual(compact["tok-a"].user_id, "alice")
        self.assertEqual(compact["tok-a"].cube_id, "alice")
        self.assertEqual(compact["tok-b"].user_id, "bob")
        colon = parse("sk-ab:cd:user1")
        self.assertEqual(colon["sk-ab:cd"].user_id, "user1")
        js = parse('{"tok-a": {"user_id": "alice", "cube_id": "cube-x"}, "tok-b": "bob"}')
        self.assertEqual(js["tok-a"].cube_id, "cube-x")
        self.assertEqual(js["tok-b"].user_id, "bob")
        self.assertEqual(parse(""), {})
        with self.assertRaises(ValueError):
            parse("nocolon")
        with self.assertRaises(ValueError):
            parse('{"tok-a": {}}')

    def test_live_sorted_filters_and_dedups(self):
        src = SHAPE.read_text(encoding="utf-8")
        names = ("metadata_of", "is_deleted", "relativity", "live_sorted")
        chunks = ["from __future__ import annotations\n"]
        for name in names:
            chunks.append(ast.get_source_segment(src, _fn(self.shape, name)))
        ns = {}
        exec("\n\n".join(chunks), ns)
        rows = [
            {"id": "a", "metadata": {"status": "deleted", "relativity": 0.9}},
            {"id": "b", "metadata": {"relativity": 0.2}},
            {"id": "b", "metadata": {"relativity": 0.2}},
            {"id": "c", "metadata": {"relativity": 0.8}},
            {"id": "d", "metadata": {"relativity": 0.5}},
        ]
        live = ns["live_sorted"](rows)
        self.assertEqual([r["id"] for r in live], ["c", "d", "b"])
        self.assertEqual([r["id"] for r in ns["live_sorted"](rows, 2)], ["c", "d"])

    def test_drop_none_and_dump(self):
        src = SHAPE.read_text(encoding="utf-8")
        chunks = ["from __future__ import annotations\nimport json\n"]
        for name in ("drop_none", "dump_json"):
            chunks.append(ast.get_source_segment(src, _fn(self.shape, name)))
        ns = {}
        exec("\n\n".join(chunks), ns)
        obj = {"a": 1, "b": None, "c": [1, None, {"d": None, "e": 2}]}
        self.assertEqual(ns["drop_none"](obj), {"a": 1, "c": [1, None, {"e": 2}]})
        dumped = ns["dump_json"]({"status": "success", "x": None})
        self.assertIn('"status"', dumped)
        self.assertNotIn("null", dumped)

    def test_backend_error_messages_unchanged(self):
        src = BACKEND.read_text(encoding="utf-8")
        self.assertIn("暂时连不上记忆服务，请稍后重试。", src)
        self.assertIn("后端拒绝了该请求:", src)
        self.assertIn("后端返回 HTTP", src)
        self.assertIn('data.get("status") == "failure"', src)

    def test_delete_is_fail_closed(self):
        src = ast.get_source_segment(SERVICE.read_text(encoding="utf-8"), _fn(self.service, "delete_memory"))
        self.assertIn("foreign", src)
        self.assertIn("不属于当前调用方的记忆空间，未做任何删除。", src)
        self.assertIn("self._client.delete(mine)", src)

    def test_add_message_payload_contract(self):
        src = ast.get_source_segment(SERVICE.read_text(encoding="utf-8"), _fn(self.service, "add_message"))
        for needle in ('"user_id"', '"mem_cube_id"', '"session_id"', '"messages"', '"async_mode": "sync"',
                       '"custom_tags"', "self._client.add"):
            self.assertIn(needle, src)

    def test_search_uses_query_prefix_and_buckets(self):
        src = ast.get_source_segment(SERVICE.read_text(encoding="utf-8"), _fn(self.service, "search_memory"))
        self.assertIn("query_prefix", src)
        self.assertIn("self._client.search", src)
        self.assertIn("cloud_lists", src)

    def test_health_and_landing_routes_exist(self):
        src = HTTP.read_text(encoding="utf-8")
        self.assertIn('"/health"', src)
        self.assertIn('methods=["GET"]', src)
        self.assertIn('"/", methods=["GET"]', src)
        self.assertIn("uptime_seconds", src)
        self.assertIn("已配空间", src)

    def test_first_line_skips_section_headers(self):
        src = HTTP.read_text(encoding="utf-8")
        body = ast.get_source_segment(src, _fn(self.http, "first_line"))
        ns = {
            "_BARE_HEADERS": {
                "trigger:", "purpose:", "strict rules:", "parameters:", "notes:",
                "returns:", "rule:", "usage requirements:",
            }
        }
        exec("from __future__ import annotations\n" + body, ns)
        self.assertEqual(ns["first_line"]("Trigger:\nPurpose: 检索相关记忆\n"), "检索相关记忆")
        self.assertEqual(ns["first_line"]("Trigger: MUST be auto-invoked"), "MUST be auto-invoked")
        self.assertEqual(ns["first_line"](""), "—")

    def test_mask_token(self):
        src = TENANTS.read_text(encoding="utf-8")
        body = ast.get_source_segment(src, _fn(self.tenants, "mask_token"))
        ns = {}
        exec("from __future__ import annotations\n" + body, ns)
        self.assertIsNone(ns["mask_token"](None))
        self.assertEqual(ns["mask_token"]("short"), "shor…")
        self.assertEqual(ns["mask_token"]("sk-1234567890abcdefghij"), "sk-123456789…ghij")

    def test_register_binds_toolset_not_schema_stubs(self):
        src = TOOLS.read_text(encoding="utf-8")
        self.assertIn("bound = Toolset(memory, identity)", src)
        self.assertIn("mcp.tool()(tool_logger.wrap(_as_mcp_tool(schema, getattr(bound, schema.__name__))))", src)
        self.assertIn("SCHEMAS = (add_message, search_memory, delete_memory, add_feedback, get_user_profile)", src)
        toolset = next(n for n in self.tools.body if isinstance(n, ast.ClassDef) and n.name == "Toolset")
        methods = {n.name for n in toolset.body if isinstance(n, ast.FunctionDef)}
        self.assertTrue({"add_message", "search_memory", "delete_memory", "add_feedback", "get_user_profile"} <= methods)
        # 模块级 schema 只是未绑定占位，真正干活的是 Toolset
        schemas = [n for n in self.tools.body if isinstance(n, ast.FunctionDef) and n.name in methods]
        for fn in schemas:
            body = ast.get_source_segment(src, fn)
            self.assertIn('raise RuntimeError("tool not bound")', body)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""工具行为测试：直接打 MemoryService，不依赖 fastmcp。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from gateway.config import Settings
from gateway.domain.caller import Caller
from gateway.domain.session import session_id_from_first_message
from gateway.errors import MemoryServiceError
from gateway.service import MemoryService


class FakeClient:
    def __init__(self):
        self.calls = []
        self.owner = {}
        self.search_data = {"text_mem": [], "pref_mem": [], "tool_mem": []}
        self.get_memory_data = {"text_mem": [], "pref_mem": [], "tool_mem": []}
        self.feedback_data = None

    def add(self, payload):
        self.calls.append({"path": "/product/add", "payload": payload})

    def search(self, payload):
        self.calls.append({"path": "/product/search", "payload": payload})
        return self.search_data

    def delete(self, memory_ids):
        self.calls.append({"path": "/product/delete_memory", "payload": {"memory_ids": memory_ids}})

    def feedback(self, payload):
        self.calls.append({"path": "/product/feedback", "payload": payload})
        return self.feedback_data

    def get_memory(self, payload):
        self.calls.append({"path": "/product/get_memory", "payload": payload})
        return self.get_memory_data

    def owner_of(self, mid):
        return self.owner.get(mid)


def _settings(query_prefix: str = "") -> Settings:
    return Settings(
        service_name="MemoryService",
        api_base="http://unused",
        timeout=120,
        host="0.0.0.0",
        port=8002,
        allowed_cubes=frozenset(),
        call_log_dir="/tmp",
        audit_log_dir="/tmp",
        query_prefix=query_prefix,
        tenants_raw="",
        started_at=0.0,
    )


class ToolBehavior(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.svc = MemoryService(self.client, _settings())
        self.me = Caller(user_id="alice", cube_id="alice")

    def test_add_message_payload(self):
        out = self.svc.add_message(
            self.me,
            "hello",
            [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hey"}],
            tags=["t1"],
        )
        self.assertEqual(json.loads(out)["status"], "success")
        sent = self.client.calls[-1]
        self.assertEqual(sent["path"], "/product/add")
        self.assertEqual(sent["payload"]["user_id"], "alice")
        self.assertEqual(sent["payload"]["mem_cube_id"], "alice")
        self.assertEqual(sent["payload"]["async_mode"], "sync")
        self.assertEqual(sent["payload"]["session_id"], session_id_from_first_message("hello"))
        self.assertEqual(sent["payload"]["custom_tags"], ["t1"])
        self.assertEqual(sent["payload"]["messages"][0]["role"], "user")

    def test_add_message_rejects_empty(self):
        with self.assertRaises(MemoryServiceError):
            self.svc.add_message(self.me, "hello", [])
        with self.assertRaises(MemoryServiceError):
            self.svc.add_message(self.me, "hello", ["not-a-dict"])

    def test_add_message_accepts_a_json_encoded_conversation(self):
        """客户端有时把整段对话先 json.dumps 再传，长成 `['[{...}]']`。
        实测这一种占 add_message 调用的 10%~23%，每次都是一个静默丢掉的写入。"""
        encoded = json.dumps(
            [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hey"}],
            ensure_ascii=False,
        )

        self.svc.add_message(self.me, "hello", [encoded])

        sent = self.client.calls[-1]
        self.assertEqual(
            sent["payload"]["messages"],
            [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hey"}],
        )

    def test_add_message_accepts_a_bare_json_string(self):
        encoded = json.dumps([{"role": "user", "content": "裸字符串"}], ensure_ascii=False)

        self.svc.add_message(self.me, "hello", encoded)

        self.assertEqual(
            self.client.calls[-1]["payload"]["messages"],
            [{"role": "user", "content": "裸字符串"}],
        )

    def test_add_message_still_rejects_undecodable_strings(self):
        with self.assertRaises(MemoryServiceError):
            self.svc.add_message(self.me, "hello", ["{不是 JSON"])

    def test_add_message_repairs_unescaped_inner_quotes(self):
        """实测那次的原样形状：用户侧内容里自带的引号没转义（整段 JSON 因此
        不合法），助手侧是 json.dumps 过的、引号带反斜杠。"""
        broken = (
            '[{"role":"user","content":"请查看记录 12345678，这是"某个名称"的记录。"},'
            '{"role":"assistant","content":"{\\"category_id\\":\\"3\\",'
            '\\"category_name\\":\\"示例分类\\"}"}]'
        )

        self.svc.add_message(self.me, "hello", [broken])

        self.assertEqual(
            self.client.calls[-1]["payload"]["messages"],
            [
                {"role": "user", "content": '请查看记录 12345678，这是"某个名称"的记录。'},
                {
                    "role": "assistant",
                    "content": '{"category_id":"3","category_name":"示例分类"}',
                },
            ],
        )

    def test_repair_leaves_valid_json_alone(self):
        from gateway.service import _repair_unescaped_quotes

        good = '[{"role":"user","content":"普通内容"}]'

        self.assertEqual(_repair_unescaped_quotes(good), good)

    def test_repair_keeps_escaped_quotes_and_backslashes(self):
        from gateway.service import _repair_unescaped_quotes

        # 已经是合法 JSON 的转义引号与反斜杠不能被再动一次
        good = '[{"role":"user","content":"他说\\"你好\\"，路径 C:\\\\tmp"}]'

        self.assertEqual(json.loads(_repair_unescaped_quotes(good)), json.loads(good))

    def test_search_filters_deleted_and_caps_topk(self):
        self.client.search_data = {
            "text_mem": [{
                "memories": [
                    {"id": "del", "memory": "gone", "metadata": {"status": "deleted", "relativity": 0.99, "key": "k"}},
                    {"id": "a", "memory": "keep-a", "metadata": {"relativity": 0.4, "key": "ka"}},
                    {"id": "b", "memory": "keep-b", "metadata": {"relativity": 0.8, "key": "kb"}},
                    {"id": "a", "memory": "dup", "metadata": {"relativity": 0.4, "key": "ka"}},
                ]
            }],
            "pref_mem": [],
            "tool_mem": [],
        }
        out = json.loads(self.svc.search_memory(self.me, "q", top_k=1))
        facts = out["memory_detail_list"]
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["memory_id"], "b")
        self.assertEqual(facts[0]["memory_value"], "keep-b")
        sent = self.client.calls[-1]
        self.assertEqual(sent["path"], "/product/search")
        self.assertEqual(sent["payload"]["query"], "q")
        self.assertEqual(sent["payload"]["top_k"], 1)

    def test_search_query_prefix(self):
        svc = MemoryService(self.client, _settings("Query: "))
        svc.search_memory(self.me, "hello")
        self.assertEqual(self.client.calls[-1]["payload"]["query"], "Query: hello")

    def test_delete_fail_closed_on_foreign(self):
        self.client.owner = {"m1": "alice", "m2": "bob"}
        with self.assertRaises(MemoryServiceError) as ctx:
            self.svc.delete_memory(self.me, ["m1", "m2"])
        self.assertIn("不属于当前调用方", str(ctx.exception))
        self.assertFalse(any(c["path"] == "/product/delete_memory" for c in self.client.calls))

    def test_delete_only_sends_memory_ids(self):
        self.client.owner = {"m1": "alice"}
        out = json.loads(self.svc.delete_memory(self.me, ["m1"]))
        sent = [c for c in self.client.calls if c["path"] == "/product/delete_memory"][-1]
        self.assertEqual(sent["payload"], {"memory_ids": ["m1"]})
        self.assertNotIn("user_id", sent["payload"])
        self.assertEqual(out["deleted_ids"], ["m1"])

    def test_delete_all_missing_is_success(self):
        out = json.loads(self.svc.delete_memory(self.me, ["nope"]))
        self.assertEqual(out["deleted_ids"], [])
        self.assertEqual(out["not_found_ids"], ["nope"])
        self.assertFalse(any(c["path"] == "/product/delete_memory" for c in self.client.calls))

    def test_add_feedback_payload(self):
        self.svc.add_feedback(self.me, "User wants Y", conversation_first_message="hello", retrieved_memory_ids=["m1"])
        sent = self.client.calls[-1]
        self.assertEqual(sent["path"], "/product/feedback")
        self.assertEqual(sent["payload"]["async_mode"], "sync")
        self.assertEqual(sent["payload"]["feedback_content"], "User wants Y")
        self.assertEqual(sent["payload"]["retrieved_memory_ids"], ["m1"])
        self.assertEqual(sent["payload"]["session_id"], session_id_from_first_message("hello"))

    def test_add_feedback_surfaces_added_and_updated(self):
        """后端 `/product/feedback` 会返回这次纠错到底改了哪几条（record.add / record.update），
        网关以前连返回值都不接，调用方只能拿到一句无条件的 "success"：改没改、改了几条、
        还是后端超时静默返回了空，全都分辨不出来。"""
        self.client.feedback_data = [{
            "answer": "好的",
            "record": {
                "add": [{"id": "n1", "text": "新增的一条", "source_doc_id": None}],
                "update": [{
                    "id": "u1", "text": "改后", "archived_id": "old1",
                    "origin_memory": "改前", "source_doc_id": None,
                }],
            },
        }]

        out = json.loads(self.svc.add_feedback(self.me, "把 X 改成 Y"))

        self.assertEqual(out["status"], "success")
        self.assertEqual([m["id"] for m in out["added"]], ["n1"])
        self.assertEqual([m["id"] for m in out["updated"]], ["u1"])
        self.assertEqual(out["updated"][0]["archived_id"], "old1")
        self.assertEqual(out["updated"][0]["text"], "改后")

    def test_add_feedback_reports_no_change_instead_of_faking_success(self):
        """后端 30s 超时（process_feedback 里 wait(timeout=30)）或无有效判定时返回空 record，
        这时必须如实说没有产生任何改动。实测一次 feedback 调用耗时 29.6s，
        正贴着这条超时线 —— 那次很可能什么都没改，却照旧回了 "success"。"""
        self.client.feedback_data = [{"answer": "", "record": {"add": [], "update": []}}]

        out = json.loads(self.svc.add_feedback(self.me, "随便说说"))

        self.assertEqual(out["status"], "success")
        self.assertEqual(out["added"], [])
        self.assertEqual(out["updated"], [])
        self.assertIn("no memory", out["message"].lower())

    def test_add_feedback_tolerates_odd_backend_shapes(self):
        """record 缺失 / data 为空 / 后端返回 None（异常路径）都不能让工具崩掉 ——
        审计是旁路，但工具本身的返回值是契约。"""
        for shape in (None, [], {}, [{}], [{"record": None}], "not-a-list"):
            self.client.feedback_data = shape
            out = json.loads(self.svc.add_feedback(self.me, "x"))
            self.assertEqual(out["status"], "success", msg=repr(shape))
            self.assertEqual(out["added"], [], msg=repr(shape))
            self.assertEqual(out["updated"], [], msg=repr(shape))

    def test_get_user_profile_omits_pref_when_asked(self):
        self.client.get_memory_data = {
            "text_mem": [{"memories": [
                {"id": "a", "memory": "fact", "metadata": {"relativity": 0.1, "key": "k", "created_at": "t"}},
            ], "total_nodes": 1}],
            "pref_mem": [{"memories": [
                {"id": "p", "memory": "pref", "metadata": {"relativity": 0.2, "type": "explicit"}},
            ], "total_nodes": 1}],
            "tool_mem": [{"memories": [
                {"id": "t", "memory": "tool", "metadata": {"relativity": 0.3}},
            ], "total_nodes": 1}],
        }
        out = json.loads(self.svc.get_user_profile(self.me, include_preference=False, include_tool_memory=False))
        self.assertEqual(len(out["memory_detail_list"]), 1)
        self.assertEqual(out["preference_detail_list"], [])
        self.assertEqual(out["tool_memory_detail_list"], [])
        self.assertEqual(out["total"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)

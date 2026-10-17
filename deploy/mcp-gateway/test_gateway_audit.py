#!/usr/bin/env python3
"""审计落盘：截断、入参折叠、JSONL fsync。不依赖 fastmcp。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from gateway.audit.extract import args_for_audit, clip
from gateway.audit.sink import JsonlSink
from gateway.log import logger


class Clip(unittest.TestCase):
    def test_short_passthrough(self):
        self.assertEqual(clip("hello"), "hello")
        self.assertEqual(clip({"a": 1}), {"a": 1})
        self.assertIsNone(clip(None))

    def test_long_string_truncated(self):
        out = clip("x" * 20, limit=8)
        self.assertEqual(out["truncated"], True)
        self.assertEqual(out["chars"], 20)
        self.assertEqual(out["text"], "x" * 8)

    def test_long_object_truncated(self):
        out = clip({"k": "v" * 50}, limit=10)
        self.assertTrue(out["truncated"])
        self.assertEqual(out["text"][:2], '{"')


def _add(conversation_first_message: str, messages: list, tags=None):
    return "ok"


class ArgsForAudit(unittest.TestCase):
    def test_bound_args(self):
        got = args_for_audit(
            _add,
            ("hello", [{"role": "user", "content": "hi"}]),
            {"tags": ["t1"]},
        )
        self.assertEqual(got["conversation_first_message"], "hello")
        self.assertEqual(got["messages"][0]["content"], "hi")
        self.assertEqual(got["tags"], ["t1"])


class Sink(unittest.TestCase):
    def test_write_fsync_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            sink = JsonlSink(td, "calls")
            sink.write({"tool": "search_memory", "ok": True})
            files = list(Path(td).glob("calls-*.jsonl"))
            self.assertEqual(len(files), 1)
            line = files[0].read_text(encoding="utf-8").strip()
            self.assertEqual(json.loads(line)["tool"], "search_memory")

    def test_write_failure_increments_and_does_not_raise(self):
        sink = JsonlSink("/proc/this-cannot-exist-as-dir", "calls")
        with patch.object(logger, "warning") as warn:
            sink.write({"x": 1})
        self.assertEqual(sink.failures, 1)
        self.assertTrue(warn.called)


if __name__ == "__main__":
    unittest.main(verbosity=2)

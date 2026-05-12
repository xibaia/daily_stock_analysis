# -*- coding: utf-8 -*-
"""
Regression tests for TaskService failure handling.
"""

import os
import sys
import unittest
import threading
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

fake_storage = ModuleType("src.storage")
fake_storage.get_db = lambda: None
sys.modules.setdefault("src.storage", fake_storage)

fake_bot = ModuleType("bot")
fake_bot_models = ModuleType("bot.models")
fake_bot_models.BotMessage = SimpleNamespace
sys.modules.setdefault("bot", fake_bot)
sys.modules.setdefault("bot.models", fake_bot_models)

from src.services.task_service import TaskService


def _make_failed_result(code: str) -> SimpleNamespace:
    return SimpleNamespace(
        code=code,
        name=f"股票{code}",
        sentiment_score=80,
        trend_prediction="看多",
        operation_advice="持有",
        analysis_summary="解析失败",
        success=False,
        error_message="JSON 解析失败",
    )


class _FakePipeline:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def process_single_stock(self, *args, **kwargs):
        return _make_failed_result(kwargs["code"])


class TestTaskService(unittest.TestCase):
    def test_run_analysis_marks_failed_for_unsuccessful_result(self):
        service = TaskService()
        service._tasks = {}
        service._tasks_lock = threading.Lock()

        fake_main = ModuleType("main")
        fake_main.StockAnalysisPipeline = _FakePipeline
        fake_config = ModuleType("src.config")
        fake_config.get_config = lambda: SimpleNamespace()

        with patch.dict("sys.modules", {"main": fake_main, "src.config": fake_config}):
            result = service._run_analysis(code="600519", task_id="task-1")

        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "JSON 解析失败")
        task = service.get_task_status("task-1")
        self.assertIsNotNone(task)
        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["error"], "JSON 解析失败")
        self.assertIsNone(task["result"])

    def test_prune_tasks_keeps_running_tasks(self):
        service = TaskService()
        service._max_tasks_cache = 3
        service._tasks = {
            "running-old": {
                "task_id": "running-old",
                "status": "running",
                "start_time": "2026-01-01T00:00:00",
            },
            "failed-old": {
                "task_id": "failed-old",
                "status": "failed",
                "start_time": "2026-01-01T00:00:01",
            },
            "completed-new": {
                "task_id": "completed-new",
                "status": "completed",
                "start_time": "2026-01-01T00:00:02",
            },
            "running-new": {
                "task_id": "running-new",
                "status": "running",
                "start_time": "2026-01-01T00:00:03",
            },
        }

        service._prune_tasks()

        self.assertIn("running-old", service._tasks)
        self.assertIn("running-new", service._tasks)
        self.assertIn("completed-new", service._tasks)
        self.assertNotIn("failed-old", service._tasks)
        self.assertEqual(len(service._tasks), 3)


if __name__ == "__main__":
    import unittest

    unittest.main()

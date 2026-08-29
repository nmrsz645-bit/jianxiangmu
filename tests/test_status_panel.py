import json
import tempfile
import unittest
from pathlib import Path

from app.status_panel import collect_account_status, collect_status, console_safe, hidden_subprocess_kwargs, parse_args, render_account_status, render_status


class StatusPanelTests(unittest.TestCase):
    def test_hidden_subprocess_kwargs_hides_windows(self):
        kwargs = hidden_subprocess_kwargs()
        self.assertTrue(kwargs["creationflags"])
        self.assertEqual(kwargs["startupinfo"].wShowWindow, 0)

    def test_collect_status_summarizes_scan_failures_and_processes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / "data").mkdir()
            (base / "logs").mkdir()
            (base / "data" / "last_project_monitor_scan.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-05T12:00:00",
                        "accounts": [
                            {
                                "advertiser_id": "1",
                                "advertiser_name": "A",
                                "project_count": 2,
                                "groups": [
                                    {"highest_name": "p1", "highest_unit_count": 88, "highest_project_id": 11},
                                    {"highest_name": "p2", "highest_unit_count": 80, "highest_project_id": 12},
                                ],
                            },
                            {"advertiser_id": "2", "advertiser_name": "B", "project_count": 1, "groups": []},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (base / "data" / "failure_queue.json").write_text(
                json.dumps([{"stage": "scan_account", "advertiser_id": "1", "last_error": "boom", "retry_count": 2}]),
                encoding="utf-8",
            )
            (base / "logs" / "project_monitor.log").write_text("line1\nline2\n", encoding="utf-8")

            status = collect_status(
                base,
                threshold=88,
                near_threshold=80,
                process_rows=[{"pid": "123", "command": "python app\\project_monitor.py"}],
            )

        self.assertTrue(status["running"])
        self.assertEqual(status["worker_pids"], ["123"])
        self.assertEqual(status["account_count"], 2)
        self.assertEqual(status["project_count"], 3)
        self.assertEqual(len(status["full_projects"]), 1)
        self.assertEqual(len(status["near_projects"]), 1)
        self.assertEqual(status["failure_count"], 1)
        self.assertEqual(status["recent_logs"], ["line1", "line2"])

    def test_render_status_contains_key_numbers(self):
        text = render_status(
            {
                "running": True,
                "worker_pids": ["123"],
                "generated_at": "2026-07-05T12:00:00",
                "account_count": 2,
                "project_count": 3,
                "full_projects": [{"account": "A", "name": "p1", "units": 88}],
                "near_projects": [{"account": "A", "name": "p2", "units": 80}],
                "failure_count": 1,
                "failures": [{"stage": "scan_account", "advertiser_id": "1", "last_error": "boom", "retry_count": 2}],
                "recent_logs": ["line1"],
            }
        )
        self.assertIn("运行中: 是", text)
        self.assertIn("账户数: 2", text)
        self.assertIn("已满项目: 1", text)
        self.assertIn("接近满额项目: 1", text)
        self.assertIn("失败队列: 1", text)

    def test_collect_account_status_uses_saved_project_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / "data").mkdir()
            (base / "data" / "last_project_monitor_scan.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-07-05T12:00:00",
                        "accounts": [
                            {
                                "advertiser_id": "1",
                                "advertiser_name": "A",
                                "project_count": 12,
                                "projects": [
                                    {"name": "p1", "project_id": 11, "unit_count": 3},
                                    {"name": "p2", "project_id": 12, "unit_count": 4},
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            status = collect_account_status(base)

        self.assertEqual(status["account_count"], 1)
        self.assertEqual(status["accounts"][0]["project_count"], 12)
        self.assertEqual(status["accounts"][0]["projects"][0]["unit_count"], 3)

    def test_render_account_status_contains_account_and_unit_counts(self):
        text = render_account_status(
            {
                "generated_at": "2026-07-05T12:00:00",
                "account_count": 1,
                "accounts": [
                    {
                        "advertiser_id": "1",
                        "advertiser_name": "A",
                        "project_count": 2,
                        "projects": [{"name": "p1", "project_id": 11, "unit_count": 3}],
                    }
                ],
            }
        )
        self.assertIn("检测账户数: 1", text)
        self.assertIn("A | 1 | 项目数=2", text)
        self.assertIn("p1 | 单元=3", text)

    def test_parse_args_does_not_treat_accounts_flag_as_base_dir(self):
        base_dir, account_mode = parse_args(["status_panel.py", "--accounts"], Path("default"))
        self.assertEqual(base_dir, Path("default"))
        self.assertTrue(account_mode)

    def test_console_safe_replaces_text_the_console_cannot_encode(self):
        text = console_safe("bad\ufffdtext", encoding="gbk")
        text.encode("gbk")
        self.assertEqual(text, "bad?text")

    def test_collect_status_uses_worker_state_from_current_base_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / "data").mkdir()
            (base / "data" / "worker_state.json").write_text('{"pid": 456}', encoding="utf-8")

            status = collect_status(base, process_rows=None, process_finder=lambda _base: [{"pid": "456"}])

        self.assertTrue(status["running"])
        self.assertEqual(status["worker_pids"], ["456"])


if __name__ == "__main__":
    unittest.main()

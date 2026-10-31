import tempfile
import unittest
from pathlib import Path

from app.manager_gui import auth_import_succeeded, auth_is_ready, clear_scan_cache, extract_callback, extract_setting, load_account_ids, save_account_ids, save_interface_settings


class ManagerGuiTests(unittest.TestCase):
    def test_extract_settings_supports_line_below_values(self):
        text = "APP_ID\ntest-app-id\nSecret\ntest-secret-value\n"
        self.assertEqual(extract_setting(text, "APP_ID"), "test-app-id")
        self.assertEqual(extract_setting(text, "Secret"), "test-secret-value")

    def test_extract_callback_uses_full_url(self):
        text = "callback_url: https://example.com/?app_id=1&auth_code=abc&scope=x"
        self.assertEqual(extract_callback(text), "https://example.com/?app_id=1&auth_code=abc&scope=x")

    def test_save_interface_and_account_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            save_interface_settings(base, "0000000000", "a" * 32, "https://example.com/?auth_code=abc")
            ids = save_account_ids(base, "0000000000\n0000000000\n0000000001")
            self.assertEqual(ids, ["0000000000", "0000000001"])
            self.assertEqual(load_account_ids(base), ids)
            self.assertIn("APP_ID", (base / "千川接口.txt").read_text(encoding="utf-8"))

    def test_save_account_ids_allows_clearing_manual_override(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            self.assertEqual(save_account_ids(base, ""), [])
            self.assertEqual(load_account_ids(base), [])

    def test_auth_is_ready_requires_config_and_tokens(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            self.assertFalse(auth_is_ready(base))
            (base / "config").mkdir()
            (base / "data").mkdir()
            (base / "config" / "qianchuan_config.json").write_text("{}", encoding="utf-8")
            self.assertFalse(auth_is_ready(base))
            (base / "data" / "tokens.json").write_text("{}", encoding="utf-8")
            self.assertTrue(auth_is_ready(base))

    def test_auth_import_accepts_success_marker_or_saved_auth_code_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / "config").mkdir()
            (base / "data").mkdir()
            (base / "config" / "qianchuan_config.json").write_text("{}", encoding="utf-8")
            (base / "data" / "tokens.json").write_text("{}", encoding="utf-8")
            self.assertTrue(auth_import_succeeded(0, "token_mode=auth_code", base))
            self.assertTrue(auth_import_succeeded(0, "auth_import_done=true", base))
            self.assertFalse(auth_import_succeeded(1, "auth_import_done=true", base))

    def test_clear_scan_cache_removes_old_dashboard_results_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            data = base / "data"
            data.mkdir()
            (data / "last_project_monitor_scan.json").write_text("{}", encoding="utf-8")
            (data / "last_project_monitor_report.json").write_text("[]", encoding="utf-8")
            (data / "failure_queue.json").write_text("[]", encoding="utf-8")
            clear_scan_cache(base)
            self.assertFalse((data / "last_project_monitor_scan.json").exists())
            self.assertFalse((data / "last_project_monitor_report.json").exists())
            self.assertTrue((data / "failure_queue.json").exists())


if __name__ == "__main__":
    unittest.main()

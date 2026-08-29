import json
import os
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
from pathlib import Path

from app.project_monitor import (
    FAILURE_RETRY_SECONDS,
    QianchuanClient,
    build_create_body,
    build_promotion_create_body,
    choose_next_projects,
    cleanup_old_logs,
    enqueue_failure,
    extract_customer_center_accounts,
    remove_failure,
    is_retryable_url_error,
    latest_promotion,
    keep_direct_account_failures,
    next_project_name,
    read_account_id_file,
    retry_failed_task,
    run_once,
    summarize_groups,
    top_project_rows,
    write_worker_state,
)


class ProjectMonitorTests(unittest.TestCase):
    def test_next_project_name_increments_suffix(self):
        self.assertEqual(next_project_name("project[2]_1"), "project[2]_2")
        self.assertEqual(next_project_name("project[2]"), "project[2]_1")

    def test_choose_only_highest_suffix_per_project_group(self):
        projects = [
            {"name": "project[2]", "project_id": 1, "unit_count": 99},
            {"name": "project[2]_1", "project_id": 2, "unit_count": 99},
            {"name": "project[2]_2", "project_id": 3, "unit_count": 1},
        ]
        self.assertEqual(choose_next_projects(projects, 88), [])
        projects[2]["unit_count"] = 88
        chosen = choose_next_projects(projects, 88)
        self.assertEqual(len(chosen), 1)
        self.assertEqual(chosen[0]["new_name"], "project[2]_3")

    def test_build_create_body_removes_list_only_fields(self):
        source = {
            "advertiser_id": 123,
            "name": "project[2]_1",
            "ad_type": "ALL",
            "marketing_goal": "VIDEO_AND_IMAGE",
            "landing_type": "MICRO_GAME",
            "delivery_mode": "PROCEDURAL",
            "delivery_range": {
                "inventory_catalog": "UNIVERSAL_SMART",
                "inventory_type": ["INVENTORY_UNIVERSAL"],
            },
            "delivery_setting": {
                "bid_type": "NO_BID",
                "budget_mode": "BUDGET_MODE_DAY",
                "deep_bid_type": "DEEP_BID_DEFAULT",
                "start_time": "2026-07-04 13:12:48",
                "end_time": "2036-07-04 13:12:48",
            },
            "internal_advertiser_info": {"classify": "CLASSIFY_SALE"},
        }
        body = build_create_body(source, "project[2]_2")
        self.assertEqual(body["name"], "project[2]_2")
        self.assertNotIn("inventory_type", body["delivery_range"])
        self.assertNotIn("deep_bid_type", body["delivery_setting"])
        self.assertEqual(body["delivery_setting"]["start_time"], "2026-07-04")
        self.assertEqual(body["delivery_setting"]["end_time"], "2036-07-04")
        self.assertEqual(body["classify"], "CLASSIFY_SALE")

    def test_summarize_groups_reports_highest_suffix(self):
        projects = [
            {"name": "project[2]_1", "project_id": 2, "unit_count": 99},
            {"name": "project[2]_2", "project_id": 3, "unit_count": 1},
        ]
        summary = summarize_groups(projects)
        self.assertEqual(summary[0]["base_name"], "project[2]")
        self.assertEqual(summary[0]["highest_name"], "project[2]_2")
        self.assertEqual(summary[0]["highest_unit_count"], 1)

    def test_top_project_rows_keeps_first_ten_with_unit_counts(self):
        projects = [{"name": f"p{i}", "project_id": i, "unit_count": i + 1} for i in range(12)]
        rows = top_project_rows(projects, 10)
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0], {"name": "p0", "project_id": 0, "unit_count": 1})
        self.assertEqual(rows[-1], {"name": "p9", "project_id": 9, "unit_count": 10})

    def test_extract_customer_center_accounts_uses_accounts_key(self):
        response = {
            "data": {
                "accounts": [
                    {"account_id": 1869328458020864, "account_name": "ZK-11", "account_type": "AD"}
                ]
            }
        }
        self.assertEqual(
            extract_customer_center_accounts(response),
            [{"advertiser_id": "1869328458020864", "name": "ZK-11"}],
        )

    def test_latest_promotion_uses_create_time(self):
        promotions = [
            {"promotion_name": "old", "promotion_create_time": "2026-07-04 13:14:04"},
            {"promotion_name": "new", "promotion_create_time": "2026-07-04 13:15:04"},
        ]
        self.assertEqual(latest_promotion(promotions)["promotion_name"], "new")

    def test_build_promotion_create_body_copies_to_new_project(self):
        source = {
            "advertiser_id": 123,
            "project_id": 111,
            "promotion_id": 999,
            "promotion_name": "unit",
            "promotion_create_time": "2026-07-04 13:14:04",
            "opt_status": "DISABLE",
            "is_comment_disable": "ON",
            "native_setting": {"aweme_id": "89334594253", "is_feed_and_fav_see": "ON"},
            "promotion_materials": {"video_material_list": [{"video_id": "v1"}]},
            "source": "source",
        }
        body = build_promotion_create_body(source, 222)
        self.assertEqual(body["advertiser_id"], 123)
        self.assertEqual(body["project_id"], 222)
        self.assertEqual(body["name"], "unit**1")
        self.assertEqual(body["is_comment_disable"], "ON")
        self.assertEqual(body["promotion_materials"]["video_material_list"][0]["video_id"], "v1")
        self.assertNotIn("promotion_id", body)
        self.assertNotIn("promotion_create_time", body)
        self.assertNotIn("opt_status", body)

    def test_ssl_eof_url_error_is_retryable(self):
        err = urllib.error.URLError("[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred")
        self.assertTrue(is_retryable_url_error(err))

    def test_enqueue_failure_retries_after_three_minutes(self):
        queue = []
        task = {"stage": "create_project_and_promotion", "advertiser_id": "1"}
        enqueue_failure(queue, task, RuntimeError("boom"), now=1000)
        self.assertEqual(queue[0]["retry_count"], 1)
        self.assertEqual(queue[0]["next_retry_at"], 1000 + FAILURE_RETRY_SECONDS)
        self.assertIn("boom", queue[0]["last_error"])

    def test_retry_existing_project_only_creates_missing_unit(self):
        class FakeClient:
            def __init__(self):
                self.created_projects = 0
                self.created_promotions = 0

            def list_projects(self, advertiser_id):
                return [
                    {"project_id": 11, "name": "old"},
                    {"project_id": 22, "name": "old_1"},
                ]

            def list_promotions(self, advertiser_id, project_id):
                return [] if project_id == 22 else [{"promotion_name": "unit", "promotion_create_time": "2026-01-01"}]

            def create_project(self, source_project, new_name):
                self.created_projects += 1
                return {"data": {"project_id": 22}}

            def create_promotion_from_latest(self, advertiser_id, source_project_id, new_project_id):
                self.created_promotions += 1
                return {"data": {"promotion_id": 33}}

        client = FakeClient()
        task = {
            "stage": "create_project_and_promotion",
            "advertiser_id": "1",
            "source_project_id": 11,
            "new_name": "old_1",
        }
        result = retry_failed_task(client, task)
        self.assertEqual(result["project_id"], 22)
        self.assertEqual(result["promotion_id"], 33)
        self.assertEqual(client.created_projects, 0)
        self.assertEqual(client.created_promotions, 1)

    def test_retry_skips_when_target_already_has_unit(self):
        class FakeClient:
            def list_projects(self, advertiser_id):
                return [{"project_id": 22, "name": "old_1"}]

            def list_promotions(self, advertiser_id, project_id):
                return [{"promotion_name": "exists"}]

            def create_promotion_from_latest(self, *args):
                raise AssertionError("should not create duplicate unit")

        task = {
            "stage": "create_project_and_promotion",
            "advertiser_id": "1",
            "source_project_id": 11,
            "new_name": "old_1",
            "new_project_id": 22,
        }
        self.assertEqual(retry_failed_task(FakeClient(), task), {"skipped": "target_has_promotions"})

    def test_retry_failed_task_can_retry_account_discovery(self):
        class FakeClient:
            def discover_ad_accounts(self, root_account):
                self.root_account = root_account
                return [{"advertiser_id": "1"}, {"advertiser_id": "2"}]

        client = FakeClient()
        result = retry_failed_task(client, {"stage": "discover_accounts", "root_account": "root"})
        self.assertEqual(client.root_account, "root")
        self.assertEqual(result, {"discovered_accounts": 2})

    def test_run_once_uses_authorized_account_ids_as_roots(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / "data").mkdir()
            (base / "logs").mkdir()
            (base / "data" / "tokens.json").write_text(
                json.dumps({"advertiser_ids": ["root-a", "root-b"]}), encoding="utf-8"
            )

            class FakeClient:
                roots = []

                def __init__(self, base_dir):
                    self.tokens = json.loads((Path(base_dir) / "data" / "tokens.json").read_text(encoding="utf-8"))

                def root_accounts(self, explicit_roots=None):
                    return self.tokens["advertiser_ids"]

                def discover_ad_accounts(self, root_account):
                    self.roots.append(root_account)
                    return [{"advertiser_id": f"ad-{root_account}", "name": root_account}]

                def list_projects(self, advertiser_id):
                    return []

            with patch("app.project_monitor.QianchuanClient", FakeClient):
                run_once(base)

        self.assertEqual(FakeClient.roots, ["root-a", "root-b"])

    def test_read_account_id_file_reads_one_id_per_line_and_commas(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / "账户ID.txt").write_text(
                "1764073167595592\n1869407725856841, 1869328450104332\nabc\n",
                encoding="utf-8",
            )

            ids = read_account_id_file(base)

        self.assertEqual(ids, ["1764073167595592", "1869407725856841", "1869328450104332"])

    def test_manual_account_ids_are_a_strict_direct_allowlist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / "data").mkdir()
            (base / "logs").mkdir()
            class FakeClient:
                listed = []

                def __init__(self, _base_dir):
                    pass

                def discover_ad_accounts(self, _root):
                    raise AssertionError("manual account IDs must not discover child accounts")

                def list_projects(self, advertiser_id):
                    self.listed.append(advertiser_id)
                    return []

            with patch("app.project_monitor.QianchuanClient", FakeClient), patch(
                "app.project_monitor.read_account_id_file", return_value=["1000000001", "1000000002", "1000000003"]
            ):
                run_once(base)

        self.assertEqual(FakeClient.listed, ["1000000001", "1000000002", "1000000003"])

    def test_direct_mode_removes_old_discovery_failures(self):
        queue = [
            {"stage": "discover_accounts", "root_account": "old"},
            {"stage": "scan_account", "advertiser_id": "keep"},
            {"stage": "scan_account", "advertiser_id": "drop"},
        ]
        self.assertEqual(keep_direct_account_failures(queue, ["keep"]), [{"stage": "scan_account", "advertiser_id": "keep"}])

    def test_remove_failure_drops_matching_task_only(self):
        queue = [
            {"stage": "scan_account", "advertiser_id": "1", "retry_count": 3},
            {"stage": "scan_account", "advertiser_id": "2", "retry_count": 3},
        ]

        remaining = remove_failure(queue, {"stage": "scan_account", "advertiser_id": "1"})

        self.assertEqual(remaining, [{"stage": "scan_account", "advertiser_id": "2", "retry_count": 3}])

    def test_auth_headers_refresh_before_authed_request(self):
        class FakeClient:
            refreshed = False

            @property
            def access_token(self):
                self.refreshed = True
                return "fresh-token"

        fake = FakeClient()
        self.assertEqual(QianchuanClient._auth_headers(fake, True), {"Access-Token": "fresh-token"})
        self.assertTrue(fake.refreshed)
        self.assertEqual(QianchuanClient._auth_headers(fake, False), {})

    def test_request_refreshes_and_retries_when_api_says_access_token_expired(self):
        class FakeResponse:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / "config").mkdir()
            (base / "data").mkdir()
            (base / "logs").mkdir()
            (base / "config" / "qianchuan_config.json").write_text(
                json.dumps({"app_id": "app", "secret": "secret"}), encoding="utf-8"
            )
            (base / "data" / "tokens.json").write_text(
                json.dumps(
                    {
                        "access_token": "old-token",
                        "refresh_token": "refresh-token",
                        "expires_at": 4_102_444_800,
                        "refresh_expires_at": 4_102_444_800,
                    }
                ),
                encoding="utf-8",
            )
            responses = [
                FakeResponse({"code": 40100, "message": "access_token已过期"}),
                FakeResponse(
                    {
                        "code": 0,
                        "data": {
                            "access_token": "new-token",
                            "refresh_token": "new-refresh-token",
                            "expires_in": 86400,
                            "refresh_token_expires_in": 2592000,
                        },
                    }
                ),
                FakeResponse({"code": 0, "data": {"ok": True}}),
            ]

            with patch("app.project_monitor.urllib.request.urlopen", side_effect=responses) as urlopen:
                result = QianchuanClient(base).request("GET", "/open_api/v3.0/project/list/", auth=True)

        self.assertEqual(result, {"code": 0, "data": {"ok": True}})
        self.assertEqual(urlopen.call_count, 3)

    def test_cleanup_old_logs_removes_only_old_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            log_dir = Path(temp_dir) / "logs"
            log_dir.mkdir()
            old_file = log_dir / "old.log"
            new_file = log_dir / "new.log"
            old_file.write_text("old", encoding="utf-8")
            new_file.write_text("new", encoding="utf-8")
            now = 10_000
            os.utime(old_file, (now - 73 * 3600, now - 73 * 3600))
            os.utime(new_file, (now - 2 * 3600, now - 2 * 3600))

            removed = cleanup_old_logs(temp_dir, now=now)

            self.assertEqual(removed, 1)
            self.assertFalse(old_file.exists())
            self.assertTrue(new_file.exists())

    def test_write_worker_state_records_pid(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            write_worker_state(temp_dir, pid=123, now=1000)
            state = (Path(temp_dir) / "data" / "worker_state.json").read_text(encoding="utf-8")
        self.assertIn('"pid": 123', state)
        self.assertIn('"updated_at": 1000', state)


if __name__ == "__main__":
    unittest.main()

import argparse
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from datetime import datetime
from pathlib import Path


API = "https://api.oceanengine.com"
DEFAULT_ROOT_ACCOUNT = "1861246396475463"
DEFAULT_THRESHOLD = 88
DEFAULT_INTERVAL_SECONDS = 600
FAILURE_RETRY_SECONDS = 180
LOG_RETENTION_HOURS = 72


CREATE_FIELDS = {
    "ad_type",
    "advertiser_id",
    "advertising_volume",
    "aigc_dynamic_creative_switch",
    "app_name",
    "app_promotion_type",
    "asset_type",
    "audience",
    "audience_extend",
    "auto_extend_traffic",
    "blue_flow_package",
    "budget_group_id",
    "classify",
    "delivery_mode",
    "delivery_range",
    "delivery_setting",
    "delivery_type",
    "download_mode",
    "download_type",
    "download_url",
    "dpa_adtype",
    "dpa_product_target",
    "item_number",
    "keywords",
    "landing_page_stay_time",
    "landing_type",
    "launch_type",
    "marketing_goal",
    "micro_app_instance_id",
    "micro_promotion_type",
    "multi_asset_type",
    "name",
    "native_setting",
    "open_url",
    "open_url_field",
    "open_url_params",
    "open_url_type",
    "operation",
    "optimize_goal",
    "promotion_type",
    "quick_app_id",
    "related_product",
    "rta_id",
    "search_bid_ratio",
    "star_auto_delivery_switch",
    "star_auto_material_addition_switch",
    "star_task_id",
    "subscribe_url",
    "track_url_setting",
    "ulink_url",
    "ulink_url_type",
    "value_optimized_type",
    "yuntu_5a_brand_id",
    "yuntu_5a_brand_main_industry_id",
}

PROMOTION_CREATE_FIELDS = {
    "7d_retention",
    "ad_download_status",
    "advertiser_id",
    "auto_extend_traffic",
    "bid",
    "brand_info",
    "budget",
    "budget_mode",
    "config_id",
    "cpa_bid",
    "creative_auto_generate_switch",
    "deep_cpabid",
    "first_roi_goal",
    "is_comment_disable",
    "keywords",
    "materials_type",
    "name",
    "native_setting",
    "operation",
    "project_id",
    "promotion_materials",
    "promotion_related_product",
    "roi_goal",
    "source",
    "union_bid_ratio",
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_account_id_file(base_dir):
    path = Path(base_dir) / "账户ID.txt"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return re.findall(r"\b\d{10,}\b", text)


def direct_account_ids(base_dir, explicit_roots=None):
    if explicit_roots:
        return [str(item).strip() for item in explicit_roots if str(item).strip()]
    return read_account_id_file(base_dir)


def keep_direct_account_failures(queue, account_ids):
    allowed = {str(item) for item in account_ids}
    return [
        task
        for task in queue
        if task.get("stage") != "discover_accounts" and str(task.get("advertiser_id") or "") in allowed
    ]


def failure_queue_path(base_dir):
    return Path(base_dir) / "data" / "failure_queue.json"


def load_failure_queue(base_dir):
    path = failure_queue_path(base_dir)
    if not path.exists():
        return []
    try:
        queue = read_json(path)
        if not isinstance(queue, list):
            raise ValueError("failure queue must be a list")
        return queue
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        backup = path.with_name(f"{path.stem}.{stamp}.bad")
        try:
            path.replace(backup)
            write_json(path, [])
            logging.warning("recovered corrupt failure queue backup=%s error=%s", backup, exc)
        except OSError as backup_exc:
            logging.error("failed to recover corrupt failure queue path=%s error=%s", path, backup_exc)
        return []


def save_failure_queue(base_dir, queue):
    path = failure_queue_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, queue)


def write_worker_state(base_dir, pid=None, now=None):
    now = int(time.time()) if now is None else int(now)
    data_dir = Path(base_dir) / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        data_dir / "worker_state.json",
        {
            "pid": os.getpid() if pid is None else int(pid),
            "updated_at": now,
        },
    )


def cleanup_old_logs(base_dir, hours=LOG_RETENTION_HOURS, now=None):
    log_dir = Path(base_dir) / "logs"
    if not log_dir.exists():
        return 0
    cutoff = (time.time() if now is None else now) - hours * 3600
    removed = 0
    for path in log_dir.rglob("*"):
        if not path.is_file():
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError as exc:
            logging.warning("failed to cleanup old log path=%s error=%s", path, exc)
    return removed


def failure_key(task):
    return (
        task.get("stage"),
        str(task.get("advertiser_id")),
        str(task.get("source_project_id")),
        str(task.get("new_name")),
        str(task.get("new_project_id")),
    )


def enqueue_failure(queue, task, error, now=None):
    now = int(time.time()) if now is None else int(now)
    key = failure_key(task)
    existing = next((item for item in queue if failure_key(item) == key), None)
    target = existing if existing is not None else dict(task)
    target["retry_count"] = int(target.get("retry_count") or 0) + 1
    target["last_error"] = str(error)
    target["next_retry_at"] = now + FAILURE_RETRY_SECONDS
    target["updated_at"] = now
    if existing is None:
        queue.append(target)
    return target


def remove_failure(queue, task):
    key = failure_key(task)
    return [item for item in queue if failure_key(item) != key]


def is_retryable_url_error(error):
    text = str(error).lower()
    return any(
        marker in text
        for marker in (
            "unexpected_eof",
            "timed out",
            "connection reset",
            "connection aborted",
            "remote end closed",
        )
    )


def is_access_token_expired_response(result):
    if not isinstance(result, dict):
        return False
    message = str(result.get("message") or "").lower()
    return "access_token" in message and ("过期" in message or "expired" in message)


def prune(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            pruned = prune(item)
            if pruned in (None, [], {}):
                continue
            out[key] = pruned
        return out or None
    if isinstance(value, list):
        out = []
        for item in value:
            pruned = prune(item)
            if pruned not in (None, {}):
                out.append(pruned)
        return out
    return value


def split_project_suffix(name):
    match = re.search(r"_(\d+)$", name or "")
    if match:
        return name[: match.start()], int(match.group(1))
    return name or "", 0


def next_project_name(name):
    base, suffix = split_project_suffix(name)
    return f"{base}_{suffix + 1}"


def choose_next_projects(projects, threshold=DEFAULT_THRESHOLD):
    by_base = {}
    names = {p.get("name") for p in projects}
    for project in projects:
        base, suffix = split_project_suffix(project.get("name"))
        current = by_base.get(base)
        if current is None or suffix > current["suffix"]:
            by_base[base] = {"suffix": suffix, "project": project}

    chosen = []
    for item in by_base.values():
        project = item["project"]
        if int(project.get("unit_count") or 0) < threshold:
            continue
        new_name = next_project_name(project.get("name"))
        if new_name in names:
            continue
        selected = dict(project)
        selected["new_name"] = new_name
        chosen.append(selected)
    return chosen


def summarize_groups(projects):
    by_base = {}
    for project in projects:
        base, suffix = split_project_suffix(project.get("name"))
        current = by_base.get(base)
        if current is None or suffix > current["suffix"]:
            by_base[base] = {"suffix": suffix, "project": project}
    summary = []
    for base, item in sorted(by_base.items(), key=lambda pair: pair[0]):
        project = item["project"]
        summary.append(
            {
                "base_name": base,
                "highest_name": project.get("name"),
                "highest_project_id": project.get("project_id"),
                "highest_suffix": item["suffix"],
                "highest_unit_count": int(project.get("unit_count") or 0),
            }
        )
    return summary


def top_project_rows(projects, limit=10):
    rows = []
    for project in projects[:limit]:
        rows.append(
            {
                "name": project.get("name") or project.get("project_name") or "",
                "project_id": project.get("project_id"),
                "unit_count": int(project.get("unit_count") or 0),
            }
        )
    return rows


def extract_customer_center_accounts(result):
    raw_accounts = result.get("data", {}).get("accounts")
    if raw_accounts is None:
        raw_accounts = result.get("data", {}).get("list") or []
    accounts = []
    for item in raw_accounts:
        account_id = str(item.get("account_id") or item.get("advertiser_id") or "")
        name = item.get("account_name") or item.get("advertiser_name") or item.get("name") or account_id
        if account_id:
            accounts.append({"advertiser_id": account_id, "name": name})
    return accounts


def latest_promotion(promotions):
    if not promotions:
        return None
    return max(promotions, key=lambda item: item.get("promotion_create_time") or "")


def build_promotion_create_body(source_promotion, new_project_id):
    body = {key: deepcopy(source_promotion.get(key)) for key in PROMOTION_CREATE_FIELDS if key in source_promotion}
    if "promotion_name" in source_promotion:
        body["name"] = f"{source_promotion['promotion_name']}**1"
    elif body.get("name"):
        body["name"] = f"{body['name']}**1"
    body["project_id"] = int(new_project_id)
    body["advertiser_id"] = int(source_promotion["advertiser_id"])
    return prune(body) or {}


def retry_failed_task(client, task):
    stage = task.get("stage")
    advertiser_id = str(task.get("advertiser_id") or "")
    if stage == "discover_accounts":
        accounts = client.discover_ad_accounts(task.get("root_account") or DEFAULT_ROOT_ACCOUNT)
        return {"discovered_accounts": len(accounts)}
    if stage == "scan_account":
        projects = client.list_projects(advertiser_id)
        for project in projects:
            client.count_units(advertiser_id, project["project_id"])
        return {"rescanned_projects": len(projects)}
    if stage != "create_project_and_promotion":
        raise RuntimeError(f"unknown failure stage: {stage}")

    new_project_id = task.get("new_project_id")
    projects = client.list_projects(advertiser_id)
    if not new_project_id:
        existing = next((p for p in projects if p.get("name") == task.get("new_name")), None)
        if existing:
            new_project_id = existing["project_id"]
    if new_project_id and client.list_promotions(advertiser_id, new_project_id):
        return {"skipped": "target_has_promotions"}

    if not new_project_id:
        source_project_id = int(task["source_project_id"])
        source = next((p for p in projects if int(p.get("project_id") or 0) == source_project_id), None)
        if not source:
            raise RuntimeError(f"source project not found: {source_project_id}")
        project_result = client.create_project(source, task["new_name"])
        new_project_id = project_result.get("data", {}).get("project_id")
    promotion_result = client.create_promotion_from_latest(advertiser_id, int(task["source_project_id"]), int(new_project_id))
    return {
        "project_id": int(new_project_id),
        "promotion_id": promotion_result.get("data", {}).get("promotion_id"),
    }


def build_create_body(source_project, new_name):
    body = {key: deepcopy(source_project.get(key)) for key in CREATE_FIELDS if key in source_project}
    internal = source_project.get("internal_advertiser_info") or {}
    for key in ("advertising_volume", "classify", "item_number"):
        if not body.get(key):
            body[key] = internal.get(key)
    body["name"] = new_name
    body = prune(body) or {}

    delivery_setting = body.get("delivery_setting") or {}
    for key in ("start_time", "end_time"):
        value = delivery_setting.get(key)
        if isinstance(value, str) and len(value) >= 10:
            delivery_setting[key] = value[:10]
    delivery_setting.pop("deep_bid_type", None)
    body["delivery_setting"] = delivery_setting

    delivery_range = body.get("delivery_range") or {}
    delivery_range.pop("inventory_type", None)
    body["delivery_range"] = delivery_range
    return body


class QianchuanClient:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.config_path = self.base_dir / "config" / "qianchuan_config.json"
        self.tokens_path = self.base_dir / "data" / "tokens.json"
        self.log_dir = self.base_dir / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.config = read_json(self.config_path)
        self.tokens = read_json(self.tokens_path)

    @property
    def access_token(self):
        self.refresh_if_needed()
        return self.tokens["access_token"]

    def refresh_if_needed(self):
        if int(self.tokens.get("expires_at") or 0) - int(time.time()) > 600:
            return
        body = {
            "app_id": self.config["app_id"],
            "secret": self.config["secret"],
            "grant_type": "refresh_token",
            "refresh_token": self.tokens["refresh_token"],
        }
        result = self.request("POST", "/open_api/oauth2/refresh_token/", body=body, auth=False)
        if result.get("code") != 0:
            raise RuntimeError(f"refresh token failed: {result.get('message')}")
        data = result["data"]
        now = int(time.time())
        self.tokens.update(
            {
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "expires_at": now + int(data["expires_in"]),
                "refresh_expires_at": now + int(data["refresh_token_expires_in"]),
                "updated_at": now,
                "token_mode": "refresh_token",
            }
        )
        write_json(self.tokens_path, self.tokens)

    def _auth_headers(self, auth):
        if not auth:
            return {}
        return {"Access-Token": self.access_token}

    def root_accounts(self, explicit_roots=None):
        roots = []
        if explicit_roots:
            roots.extend(explicit_roots if isinstance(explicit_roots, (list, tuple)) else [explicit_roots])
        roots.extend(read_account_id_file(self.base_dir))
        for key in ("root_account_ids", "root_accounts"):
            roots.extend(self.config.get(key) or [])
        for key in ("root_account_id", "root_account"):
            if self.config.get(key):
                roots.append(self.config[key])
        roots.extend(self.tokens.get("advertiser_ids") or [])
        roots.append(DEFAULT_ROOT_ACCOUNT)

        seen = set()
        out = []
        for item in roots:
            value = str(item).strip()
            if value and value not in seen:
                seen.add(value)
                out.append(value)
        return out

    def request(self, method, path, params=None, body=None, auth=True):
        url = API + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = self._auth_headers(auth)
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        refreshed_after_expiry = False
        for attempt in range(3):
            request = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=80) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    if auth and not refreshed_after_expiry and is_access_token_expired_response(result):
                        self.tokens["expires_at"] = 0
                        self.refresh_if_needed()
                        headers = self._auth_headers(auth)
                        if body is not None:
                            headers["Content-Type"] = "application/json"
                        refreshed_after_expiry = True
                        continue
                    return result
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="replace")
                try:
                    result = json.loads(raw)
                except json.JSONDecodeError:
                    result = {"code": exc.code, "message": raw}
                if auth and not refreshed_after_expiry and is_access_token_expired_response(result):
                    self.tokens["expires_at"] = 0
                    self.refresh_if_needed()
                    headers = self._auth_headers(auth)
                    if body is not None:
                        headers["Content-Type"] = "application/json"
                    refreshed_after_expiry = True
                    continue
                return result
            except urllib.error.URLError as exc:
                if attempt == 2 or not is_retryable_url_error(exc):
                    raise
                logging.warning("retryable request error attempt=%s path=%s error=%s", attempt + 1, path, exc)
                time.sleep(3 * (attempt + 1))

    def discover_ad_accounts(self, root_account=DEFAULT_ROOT_ACCOUNT):
        result = self.request(
            "GET",
            "/open_api/v3.0/customer_center/account/list/",
            params={
                "account_id": root_account,
                "filter": json.dumps({"account_type": "AD"}, ensure_ascii=False),
                "page": 1,
                "page_size": 100,
            },
        )
        if result.get("code") != 0:
            raise RuntimeError(f"account list failed: {result.get('message')}")
        return extract_customer_center_accounts(result)

    def list_projects(self, advertiser_id):
        projects = []
        page = 1
        while True:
            result = self.request(
                "GET",
                "/open_api/v3.0/project/list/",
                params={"advertiser_id": advertiser_id, "page": page, "page_size": 100},
            )
            if result.get("code") != 0:
                raise RuntimeError(f"project list failed for {advertiser_id}: {result.get('message')}")
            items = result.get("data", {}).get("list") or []
            projects.extend(items)
            if len(items) < 100:
                return projects
            page += 1

    def count_units(self, advertiser_id, project_id):
        return len(self.list_promotions(advertiser_id, project_id))

    def list_promotions(self, advertiser_id, project_id):
        promotions = []
        page = 1
        filtering = json.dumps({"project_id": project_id}, ensure_ascii=False)
        while True:
            result = self.request(
                "GET",
                "/open_api/v3.0/promotion/list/",
                params={
                    "advertiser_id": advertiser_id,
                    "filtering": filtering,
                    "page": page,
                    "page_size": 20,
                },
            )
            if result.get("code") != 0:
                raise RuntimeError(f"promotion list failed for {project_id}: {result.get('message')}")
            items = result.get("data", {}).get("list") or []
            promotions.extend(items)
            if len(items) < 20:
                return promotions
            page += 1

    def create_project(self, source_project, new_name):
        body = build_create_body(source_project, new_name)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        write_json(self.log_dir / f"create_project_{stamp}_request.json", body)
        result = self.request("POST", "/open_api/v3.0/project/create/", body=body)
        write_json(self.log_dir / f"create_project_{stamp}_response.json", result)
        if result.get("code") != 0:
            raise RuntimeError(f"project create failed for {new_name}: {result.get('message')}")
        return result

    def create_promotion_from_latest(self, advertiser_id, source_project_id, new_project_id):
        source = latest_promotion(self.list_promotions(advertiser_id, source_project_id))
        if not source:
            raise RuntimeError(f"source project has no promotion: {source_project_id}")
        body = build_promotion_create_body(source, new_project_id)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        write_json(self.log_dir / f"create_promotion_{stamp}_request.json", body)
        result = self.request("POST", "/open_api/v3.0/promotion/create/", body=body)
        write_json(self.log_dir / f"create_promotion_{stamp}_response.json", result)
        if result.get("code") != 0:
            raise RuntimeError(f"promotion create failed for {body.get('name')}: {result.get('message')}")
        return result


def run_once(base_dir, threshold=DEFAULT_THRESHOLD, root_account=None, dry_run=False):
    cleanup_old_logs(base_dir)
    client = QianchuanClient(base_dir)
    direct_ids = direct_account_ids(base_dir, root_account)
    if direct_ids:
        # A non-empty account ID file is an explicit allowlist, never an organization discovery seed.
        save_failure_queue(base_dir, keep_direct_account_failures(load_failure_queue(base_dir), direct_ids))
    process_failure_queue(client, base_dir, dry_run=dry_run)
    queue = load_failure_queue(base_dir)
    accounts = []
    seen_accounts = set()
    if direct_ids:
        discovered_groups = [direct_ids]
    else:
        discovered_groups = []
        for root in client.root_accounts(root_account):
            try:
                discovered = client.discover_ad_accounts(root)
                queue = remove_failure(queue, {"stage": "discover_accounts", "root_account": root})
            except Exception as exc:
                enqueue_failure(queue, {"stage": "discover_accounts", "root_account": root}, exc)
                logging.exception("queued account discovery failure root_account=%s", root)
                discovered = [{"advertiser_id": root, "name": root}]
            discovered_groups.append(discovered)
    for discovered in discovered_groups:
        if direct_ids:
            discovered = [{"advertiser_id": account_id, "name": account_id} for account_id in discovered]
        for account in discovered:
            advertiser_id = str(account.get("advertiser_id") or "")
            if advertiser_id and advertiser_id not in seen_accounts:
                seen_accounts.add(advertiser_id)
                accounts.append(account)
    scan = {"generated_at": datetime.now().isoformat(timespec="seconds"), "accounts": []}
    report = []
    for account in accounts:
        advertiser_id = account["advertiser_id"]
        try:
            projects = client.list_projects(advertiser_id)
            queue = remove_failure(queue, {"stage": "scan_account", "advertiser_id": advertiser_id})
        except Exception as exc:
            enqueue_failure(queue, {"stage": "scan_account", "advertiser_id": advertiser_id}, exc)
            logging.exception("queued account scan failure advertiser=%s", advertiser_id)
            continue
        enriched = []
        for project in projects:
            item = dict(project)
            try:
                item["unit_count"] = client.count_units(advertiser_id, project["project_id"])
            except Exception as exc:
                enqueue_failure(queue, {"stage": "scan_account", "advertiser_id": advertiser_id}, exc)
                logging.exception("queued promotion scan failure advertiser=%s project=%s", advertiser_id, project.get("project_id"))
                continue
            enriched.append(item)
        account_summary = {
            "advertiser_id": advertiser_id,
            "advertiser_name": account.get("name"),
            "project_count": len(enriched),
            "projects": top_project_rows(enriched, 10),
            "groups": summarize_groups(enriched),
        }
        scan["accounts"].append(account_summary)
        for selected in choose_next_projects(enriched, threshold):
            new_name = selected["new_name"]
            if dry_run:
                source_promotion = latest_promotion(client.list_promotions(advertiser_id, selected["project_id"]))
                promotion_name = source_promotion.get("promotion_name") if source_promotion else None
                logging.info("dry_run create advertiser=%s source=%s new=%s units=%s clone_unit=%s", advertiser_id, selected.get("name"), new_name, selected.get("unit_count"), promotion_name)
                report.append({"advertiser_id": advertiser_id, "source": selected.get("name"), "new_name": new_name, "clone_unit": promotion_name, "dry_run": True})
                continue
            failure_task = {
                "stage": "create_project_and_promotion",
                "advertiser_id": advertiser_id,
                "source_project_id": selected["project_id"],
                "source_project_name": selected.get("name"),
                "new_name": new_name,
            }
            project_id = None
            try:
                result = client.create_project(selected, new_name)
                project_id = result.get("data", {}).get("project_id")
                failure_task["new_project_id"] = project_id
                promotion_result = client.create_promotion_from_latest(advertiser_id, selected["project_id"], project_id)
                promotion_id = promotion_result.get("data", {}).get("promotion_id")
                logging.info("created advertiser=%s source=%s new=%s project_id=%s promotion_id=%s", advertiser_id, selected.get("name"), new_name, project_id, promotion_id)
                report.append({"advertiser_id": advertiser_id, "source": selected.get("name"), "new_name": new_name, "project_id": project_id, "promotion_id": promotion_id})
            except Exception as exc:
                enqueue_failure(queue, failure_task, exc)
                logging.exception("queued create failure advertiser=%s source=%s new=%s project_id=%s", advertiser_id, selected.get("name"), new_name, project_id)
                continue
    save_failure_queue(base_dir, queue)
    write_json(Path(base_dir) / "data" / "last_project_monitor_scan.json", scan)
    write_json(Path(base_dir) / "data" / "last_project_monitor_report.json", report)
    return report


def process_failure_queue(client, base_dir, dry_run=False, now=None):
    now = int(time.time()) if now is None else int(now)
    queue = load_failure_queue(base_dir)
    if not queue:
        return []
    remaining = []
    completed = []
    for task in queue:
        if int(task.get("next_retry_at") or 0) > now:
            remaining.append(task)
            continue
        if dry_run:
            remaining.append(task)
            logging.info("dry_run pending failure stage=%s advertiser=%s", task.get("stage"), task.get("advertiser_id"))
            continue
        try:
            result = retry_failed_task(client, task)
            completed.append({"task": task, "result": result})
            logging.info("failure retry succeeded stage=%s advertiser=%s result=%s", task.get("stage"), task.get("advertiser_id"), result)
        except Exception as exc:
            enqueue_failure(remaining, task, exc, now=now)
            logging.exception("failure retry still failing stage=%s advertiser=%s", task.get("stage"), task.get("advertiser_id"))
    save_failure_queue(base_dir, remaining)
    return completed


def has_failure_queue(base_dir):
    return bool(load_failure_queue(base_dir))


def stop_file_path(base_dir):
    return Path(base_dir) / "data" / "stop_monitor.flag"


def wait_for_next_scan(stop_file, seconds):
    """Return True when a requested stop interrupts the wait."""
    deadline = time.time() + max(0, int(seconds))
    while time.time() < deadline:
        if stop_file.exists():
            return True
        time.sleep(min(1, max(0.1, deadline - time.time())))
    return stop_file.exists()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS)
    parser.add_argument("--root-account", action="append", default=None)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    base_dir = Path(args.base_dir)
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stop_file = stop_file_path(base_dir)
    logging.basicConfig(
        filename=log_dir / "project_monitor.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger().addHandler(logging.StreamHandler())

    while True:
        if stop_file.exists():
            logging.info("monitor stop requested")
            stop_file.unlink(missing_ok=True)
            break
        try:
            write_worker_state(base_dir)
            report = run_once(base_dir, args.threshold, root_account=args.root_account, dry_run=args.dry_run)
            logging.info("scan finished created=%s dry_run=%s", len(report), args.dry_run)
        except Exception:
            logging.exception("scan failed")
        if args.once:
            break
        sleep_seconds = min(args.interval, FAILURE_RETRY_SECONDS) if has_failure_queue(base_dir) else args.interval
        if wait_for_next_scan(stop_file, sleep_seconds):
            logging.info("monitor stop requested during wait")
            stop_file.unlink(missing_ok=True)
            break


if __name__ == "__main__":
    main()

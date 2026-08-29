import json
import subprocess
import sys
from pathlib import Path


DEFAULT_THRESHOLD = 88
DEFAULT_NEAR_THRESHOLD = 80


def hidden_subprocess_kwargs():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": startupinfo}


def read_json(path, default):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def tail_lines(path, limit=10):
    path = Path(path)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-limit:]


def console_safe(text, encoding=None):
    encoding = encoding or sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def process_exists(pid):
    if not pid:
        return False
    command = (
        f"$p = Get-CimInstance Win32_Process -Filter \"ProcessId = {int(pid)}\"; "
        "if ($p -and (($p.Name -like 'python*' -and $p.CommandLine -like '*project_monitor.py*') -or "
        "($p.Name -like '*建项目监控*.exe' -and $p.CommandLine -like '*--worker*'))) "
        "{ $p | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress }"
    )
    try:
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            **hidden_subprocess_kwargs(),
        ).strip()
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    return bool(raw)


def find_worker_processes(base_dir):
    state = read_json(Path(base_dir) / "data" / "worker_state.json", {})
    pid = state.get("pid")
    if pid and process_exists(pid):
        return [{"pid": str(pid), "command": "project_monitor.py"}]

    command = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { ($_.Name -like 'python*' -and $_.CommandLine -like '*project_monitor.py*') -or "
        "($_.Name -like '*建项目监控*.exe' -and $_.CommandLine -like '*--worker*') } | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    )
    try:
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
            **hidden_subprocess_kwargs(),
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return []
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    return [{"pid": str(item.get("ProcessId")), "command": item.get("CommandLine") or ""} for item in data]


def collect_status(
    base_dir,
    threshold=DEFAULT_THRESHOLD,
    near_threshold=DEFAULT_NEAR_THRESHOLD,
    process_rows=None,
    process_finder=find_worker_processes,
):
    base_dir = Path(base_dir)
    scan = read_json(base_dir / "data" / "last_project_monitor_scan.json", {})
    failures = read_json(base_dir / "data" / "failure_queue.json", [])
    process_rows = process_finder(base_dir) if process_rows is None else process_rows

    accounts = scan.get("accounts") or []
    full_projects = []
    near_projects = []
    project_count = 0
    for account in accounts:
        account_name = account.get("advertiser_name") or account.get("advertiser_id") or ""
        project_count += int(account.get("project_count") or 0)
        for group in account.get("groups") or []:
            units = int(group.get("highest_unit_count") or 0)
            item = {
                "account": account_name,
                "name": group.get("highest_name") or group.get("base_name") or "",
                "project_id": group.get("highest_project_id"),
                "units": units,
            }
            if units >= threshold:
                full_projects.append(item)
            elif units >= near_threshold:
                near_projects.append(item)

    return {
        "running": bool(process_rows),
        "worker_pids": [row["pid"] for row in process_rows if row.get("pid")],
        "generated_at": scan.get("generated_at") or "none",
        "account_count": len(accounts),
        "project_count": project_count,
        "full_projects": sorted(full_projects, key=lambda item: item["units"], reverse=True),
        "near_projects": sorted(near_projects, key=lambda item: item["units"], reverse=True),
        "failure_count": len(failures),
        "failures": failures[:10],
        "recent_logs": tail_lines(base_dir / "logs" / "project_monitor.log", 10),
    }


def collect_account_status(base_dir):
    base_dir = Path(base_dir)
    scan = read_json(base_dir / "data" / "last_project_monitor_scan.json", {})
    accounts = []
    for account in scan.get("accounts") or []:
        projects = []
        for project in (account.get("projects") or [])[:10]:
            projects.append(
                {
                    "name": project.get("name") or project.get("project_name") or "",
                    "project_id": project.get("project_id"),
                    "unit_count": int(project.get("unit_count") or 0),
                }
            )
        accounts.append(
            {
                "advertiser_id": account.get("advertiser_id") or "",
                "advertiser_name": account.get("advertiser_name") or "",
                "project_count": int(account.get("project_count") or 0),
                "projects": projects,
            }
        )
    return {
        "generated_at": scan.get("generated_at") or "none",
        "account_count": len(accounts),
        "accounts": accounts,
    }


def render_project_line(item):
    return f"- {item.get('account')} | {item.get('name')} | 单元={item.get('units')} | 项目ID={item.get('project_id')}"


def render_status(status):
    lines = [
        "项目监控状态",
        "=" * 22,
        f"运行中: {'是' if status['running'] else '否'}",
        f"Worker PID: {', '.join(status['worker_pids']) if status['worker_pids'] else '无'}",
        f"最近扫描: {status['generated_at']}",
        f"账户数: {status['account_count']}",
        f"项目数: {status['project_count']}",
        f"已满项目: {len(status['full_projects'])}",
        f"接近满额项目: {len(status['near_projects'])}",
        f"失败队列: {status['failure_count']}",
        "",
        "已满项目 (>=88):",
    ]
    lines.extend(render_project_line(item) for item in status["full_projects"][:10])
    if not status["full_projects"]:
        lines.append("- 无")
    lines.append("")
    lines.append("接近满额项目 (>=80):")
    lines.extend(render_project_line(item) for item in status["near_projects"][:10])
    if not status["near_projects"]:
        lines.append("- 无")
    lines.append("")
    lines.append("失败队列明细:")
    if status["failures"]:
        for item in status["failures"]:
            lines.append(
                f"- stage={item.get('stage')} advertiser={item.get('advertiser_id')} "
                f"retry={item.get('retry_count')} error={item.get('last_error')}"
            )
    else:
        lines.append("- 无")
    lines.append("")
    lines.append("最近日志:")
    lines.extend(status["recent_logs"] or ["- 无"])
    return "\n".join(lines)


def render_account_status(status):
    lines = [
        "账户项目状态",
        "=" * 22,
        f"最近扫描: {status['generated_at']}",
        f"检测账户数: {status['account_count']}",
        "",
    ]
    if not status["accounts"]:
        lines.append("未找到扫描结果。请先启动程序，等它完成一次扫描。")
        return "\n".join(lines)

    for account in status["accounts"]:
        account_name = account.get("advertiser_name") or account.get("advertiser_id")
        lines.append(f"{account_name} | {account.get('advertiser_id')} | 项目数={account.get('project_count')}")
        projects = account.get("projects") or []
        if not projects:
            lines.append("  - 前十项目: 无")
            lines.append("")
            continue
        for index, project in enumerate(projects, start=1):
            lines.append(
                f"  {index}. {project.get('name')} | 单元={project.get('unit_count')} | 项目ID={project.get('project_id')}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def parse_args(argv, default_base_dir):
    account_mode = "--accounts" in argv[1:]
    base_args = [arg for arg in argv[1:] if arg != "--accounts"]
    base_dir = Path(base_args[0]) if base_args else Path(default_base_dir)
    return base_dir, account_mode


def main():
    base_dir, account_mode = parse_args(sys.argv, Path(__file__).resolve().parents[1])
    if account_mode:
        print(console_safe(render_account_status(collect_account_status(base_dir))))
    else:
        print(console_safe(render_status(collect_status(base_dir))))


if __name__ == "__main__":
    main()

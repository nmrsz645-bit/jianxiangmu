import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import project_monitor, status_panel


APP_TITLE = "建项目监控"
WINDOW_COLOR = "#f4f7f8"
PANEL_COLOR = "#ffffff"
TEXT_COLOR = "#1f2933"
MUTED_COLOR = "#607080"
ACCENT_COLOR = "#0f766e"
WARNING_COLOR = "#b45309"
DANGER_COLOR = "#b42318"


def application_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def extract_setting(text, name):
    for index, raw_line in enumerate(text.splitlines()):
        line = raw_line.strip()
        if not line.startswith(name):
            continue
        tail = line[len(name) :].lstrip(" :：\t")
        if tail:
            return tail
        lines = text.splitlines()
        if index + 1 < len(lines):
            return lines[index + 1].strip()
    return ""


def extract_callback(text):
    matches = re.findall(r"https?://[^\s\]\)]+auth_code=[^\s\]\)]+", text)
    return matches[-1].strip() if matches else ""


def interface_path(base_dir):
    candidates = sorted(Path(base_dir).glob("*.txt"))
    for path in candidates:
        content = read_text(path)
        if "APP_ID" in content and "Secret" in content:
            return path
    return Path(base_dir) / "千川接口.txt"


def load_interface_settings(base_dir):
    content = read_text(interface_path(base_dir))
    return {
        "app_id": extract_setting(content, "APP_ID"),
        "secret": extract_setting(content, "Secret"),
        "callback": extract_callback(content),
    }


def save_interface_settings(base_dir, app_id, secret, callback):
    app_id = app_id.strip()
    secret = secret.strip()
    callback = callback.strip()
    if not re.fullmatch(r"\d{10,}", app_id):
        raise ValueError("APP_ID 应为数字")
    if len(secret) < 16:
        raise ValueError("Secret 长度不正确")
    if not re.match(r"^https?://.+[?&]auth_code=[^&\s]+", callback):
        raise ValueError("请粘贴包含 auth_code 的完整回调地址")
    content = f"APP_ID\n{app_id}\nSecret\n{secret}\ncallback_url: {callback}\n"
    interface_path(base_dir).write_text(content, encoding="utf-8")


def load_account_ids(base_dir):
    return re.findall(r"\b\d{10,}\b", read_text(Path(base_dir) / "账户ID.txt"))


def save_account_ids(base_dir, text):
    ids = []
    for item in re.findall(r"\b\d{10,}\b", text):
        if item not in ids:
            ids.append(item)
    content = "\n".join(ids) + "\n" if ids else "# 留空时使用本次授权自动返回的账户\n"
    (Path(base_dir) / "账户ID.txt").write_text(content, encoding="utf-8")
    return ids


def append_ui_log(base_dir, message):
    log_dir = Path(base_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "desktop_ui.log").open("a", encoding="utf-8") as handle:
        handle.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}\n")


def worker_command(base_dir, once=False):
    args = ["--worker", "--base-dir", str(base_dir)]
    if once:
        args.append("--once")
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, str(Path(__file__).resolve()), *args]


def hidden_subprocess_kwargs():
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {"creationflags": subprocess.CREATE_NO_WINDOW, "startupinfo": startupinfo}


def auth_is_ready(base_dir):
    base_dir = Path(base_dir)
    return (base_dir / "config" / "qianchuan_config.json").is_file() and (base_dir / "data" / "tokens.json").is_file()


def auth_import_succeeded(returncode, output, base_dir):
    if returncode != 0:
        return False
    return "auth_import_done=true" in output or ("token_mode=auth_code" in output and auth_is_ready(base_dir))


def clear_scan_cache(base_dir):
    data_dir = Path(base_dir) / "data"
    for filename in ("last_project_monitor_scan.json", "last_project_monitor_report.json"):
        (data_dir / filename).unlink(missing_ok=True)


class ManagerApp(tk.Tk):
    def __init__(self, base_dir):
        super().__init__()
        self.base_dir = Path(base_dir)
        self.title(APP_TITLE)
        self.geometry("1160x760")
        self.minsize(1000, 680)
        self.configure(bg=WINDOW_COLOR)
        self._build_style()
        self._build_shell()
        self.show_page("overview")
        self.refresh_all()
        self.after(10000, self.auto_refresh)

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", background=PANEL_COLOR, fieldbackground=PANEL_COLOR, foreground=TEXT_COLOR, rowheight=28)
        style.configure("Treeview.Heading", background="#e8eef0", foreground=TEXT_COLOR, relief="flat")
        style.map("Treeview", background=[("selected", "#d7f0eb")], foreground=[("selected", TEXT_COLOR)])

    def _build_shell(self):
        sidebar = tk.Frame(self, bg="#12343b", width=210)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="建项目监控", bg="#12343b", fg="white", font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w", padx=22, pady=(28, 4))
        tk.Label(sidebar, text="千川项目自动扩容", bg="#12343b", fg="#b5ced1", font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=22, pady=(0, 24))
        self.nav_buttons = {}
        for key, label in (("overview", "总览"), ("accounts", "账户与项目"), ("auth", "授权配置"), ("control", "监控控制"), ("logs", "运行日志")):
            button = tk.Button(sidebar, text=label, anchor="w", relief="flat", borderwidth=0, padx=22, pady=12, bg="#12343b", fg="#d9ecee", activebackground="#1c545b", activeforeground="white", font=("Microsoft YaHei UI", 11), command=lambda item=key: self.show_page(item))
            button.pack(fill="x")
            self.nav_buttons[key] = button
        tk.Label(sidebar, text="v2.0 本地桌面版", bg="#12343b", fg="#83a5a9", font=("Microsoft YaHei UI", 9)).pack(side="bottom", anchor="w", padx=22, pady=22)

        self.body = tk.Frame(self, bg=WINDOW_COLOR)
        self.body.pack(side="right", fill="both", expand=True)
        self.pages = {}
        self._build_overview()
        self._build_accounts()
        self._build_auth()
        self._build_control()
        self._build_logs()

    def page_frame(self, key, title, subtitle):
        page = tk.Frame(self.body, bg=WINDOW_COLOR)
        header = tk.Frame(page, bg=WINDOW_COLOR)
        header.pack(fill="x", padx=32, pady=(26, 16))
        tk.Label(header, text=title, bg=WINDOW_COLOR, fg=TEXT_COLOR, font=("Microsoft YaHei UI", 21, "bold")).pack(anchor="w")
        tk.Label(header, text=subtitle, bg=WINDOW_COLOR, fg=MUTED_COLOR, font=("Microsoft YaHei UI", 10)).pack(anchor="w", pady=(4, 0))
        self.pages[key] = page
        return page

    def card(self, parent):
        frame = tk.Frame(parent, bg=PANEL_COLOR, highlightbackground="#dce5e7", highlightthickness=1)
        return frame

    def action_button(self, parent, text, command, color=ACCENT_COLOR):
        return tk.Button(parent, text=text, command=command, bg=color, fg="white", activebackground=color, activeforeground="white", relief="flat", borderwidth=0, padx=15, pady=8, font=("Microsoft YaHei UI", 10, "bold"), cursor="hand2")

    def _build_overview(self):
        page = self.page_frame("overview", "运行总览", "监控状态每 10 秒自动刷新")
        actions = tk.Frame(page, bg=WINDOW_COLOR)
        actions.pack(fill="x", padx=32, pady=(0, 14))
        self.action_button(actions, "启动后台监控", self.start_monitor).pack(side="left")
        self.action_button(actions, "刷新状态", self.refresh_all, "#2f6570").pack(side="left", padx=10)
        self.overview_status = tk.Label(actions, text="", bg=WINDOW_COLOR, fg=MUTED_COLOR, font=("Microsoft YaHei UI", 10))
        self.overview_status.pack(side="right")
        metrics = tk.Frame(page, bg=WINDOW_COLOR)
        metrics.pack(fill="x", padx=32)
        self.metric_vars = {}
        for key, label in (("running", "监控状态"), ("accounts", "已检测账户"), ("projects", "项目数量"), ("full", "已满项目"), ("failures", "失败队列")):
            box = self.card(metrics)
            box.pack(side="left", fill="x", expand=True, padx=(0 if key == "running" else 10, 0), ipady=12)
            tk.Label(box, text=label, bg=PANEL_COLOR, fg=MUTED_COLOR, font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=16)
            var = tk.StringVar(value="--")
            tk.Label(box, textvariable=var, bg=PANEL_COLOR, fg=TEXT_COLOR, font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w", padx=16, pady=(5, 0))
            self.metric_vars[key] = var
        content = tk.Frame(page, bg=WINDOW_COLOR)
        content.pack(fill="both", expand=True, padx=32, pady=18)
        left = self.card(content)
        left.pack(side="left", fill="both", expand=True, padx=(0, 9))
        tk.Label(left, text="接近或达到上限的项目", bg=PANEL_COLOR, fg=TEXT_COLOR, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        self.risk_tree = ttk.Treeview(left, columns=("account", "project", "units"), show="headings")
        for column, label, width in (("account", "账户", 150), ("project", "项目", 260), ("units", "单元数", 80)):
            self.risk_tree.heading(column, text=label)
            self.risk_tree.column(column, width=width, anchor="w")
        self.risk_tree.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        right = self.card(content)
        right.pack(side="right", fill="both", expand=True, padx=(9, 0))
        tk.Label(right, text="最近运行记录", bg=PANEL_COLOR, fg=TEXT_COLOR, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        self.recent_log = tk.Text(right, bg=PANEL_COLOR, fg=TEXT_COLOR, relief="flat", borderwidth=0, wrap="word", font=("Consolas", 9), state="disabled")
        self.recent_log.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def _build_accounts(self):
        page = self.page_frame("accounts", "账户与项目", "每行一个账户 ID。保存后，下一次监控将按此列表检测。")
        top = self.card(page)
        top.pack(fill="x", padx=32, pady=(0, 14))
        tk.Label(top, text="账户 ID", bg=PANEL_COLOR, fg=TEXT_COLOR, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=16, pady=(14, 6))
        self.account_text = tk.Text(top, height=4, bg="#fbfcfc", fg=TEXT_COLOR, relief="solid", borderwidth=1, font=("Consolas", 10))
        self.account_text.pack(fill="x", padx=16)
        actions = tk.Frame(top, bg=PANEL_COLOR)
        actions.pack(fill="x", padx=16, pady=12)
        self.action_button(actions, "保存账户 ID", self.save_accounts).pack(side="left")
        self.action_button(actions, "立即刷新列表", self.refresh_all, "#2f6570").pack(side="left", padx=10)
        self.account_hint = tk.Label(actions, text="", bg=PANEL_COLOR, fg=MUTED_COLOR, font=("Microsoft YaHei UI", 9))
        self.account_hint.pack(side="right")
        card = self.card(page)
        card.pack(fill="both", expand=True, padx=32, pady=(0, 22))
        tk.Label(card, text="各账户前 10 个项目", bg=PANEL_COLOR, fg=TEXT_COLOR, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        self.account_tree = ttk.Treeview(card, columns=("account", "project", "units", "project_id"), show="headings")
        for column, label, width in (("account", "账户", 200), ("project", "项目", 300), ("units", "单元数", 85), ("project_id", "项目 ID", 170)):
            self.account_tree.heading(column, text=label)
            self.account_tree.column(column, width=width, anchor="w")
        self.account_tree.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    def _build_auth(self):
        page = self.page_frame("auth", "授权配置", "首次使用或更换千川接口时，在这里填写并导入授权。")
        card = self.card(page)
        card.pack(fill="x", padx=32, pady=(0, 14))
        form = tk.Frame(card, bg=PANEL_COLOR)
        form.pack(fill="x", padx=20, pady=18)
        self.auth_vars = {"app_id": tk.StringVar(), "secret": tk.StringVar(), "callback": tk.StringVar()}
        for row, (key, label, secret) in enumerate((("app_id", "APP_ID", False), ("secret", "Secret", True), ("callback", "完整回调地址", False))):
            tk.Label(form, text=label, bg=PANEL_COLOR, fg=TEXT_COLOR, width=13, anchor="w", font=("Microsoft YaHei UI", 10)).grid(row=row, column=0, sticky="w", pady=7)
            entry = tk.Entry(form, textvariable=self.auth_vars[key], show="*" if secret else "", bg="#fbfcfc", fg=TEXT_COLOR, relief="solid", borderwidth=1, font=("Microsoft YaHei UI", 10))
            entry.grid(row=row, column=1, sticky="ew", pady=7)
        form.grid_columnconfigure(1, weight=1)
        actions = tk.Frame(card, bg=PANEL_COLOR)
        actions.pack(fill="x", padx=20, pady=(0, 18))
        self.action_button(actions, "保存并导入授权", self.import_auth).pack(side="left")
        self.auth_status = tk.Label(actions, text="", bg=PANEL_COLOR, fg=MUTED_COLOR, font=("Microsoft YaHei UI", 9))
        self.auth_status.pack(side="left", padx=12)
        output = self.card(page)
        output.pack(fill="both", expand=True, padx=32, pady=(0, 22))
        tk.Label(output, text="授权结果", bg=PANEL_COLOR, fg=TEXT_COLOR, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=16, pady=(14, 8))
        self.auth_output = tk.Text(output, bg=PANEL_COLOR, fg=TEXT_COLOR, relief="flat", borderwidth=0, wrap="word", font=("Consolas", 9), state="disabled")
        self.auth_output.pack(fill="both", expand=True, padx=14, pady=(0, 12))

    def _build_control(self):
        page = self.page_frame("control", "监控控制", "后台运行不显示命令窗口；停止会在当前扫描结束后生效。")
        card = self.card(page)
        card.pack(fill="x", padx=32, pady=(0, 14))
        buttons = tk.Frame(card, bg=PANEL_COLOR)
        buttons.pack(fill="x", padx=20, pady=20)
        self.action_button(buttons, "启动后台监控", self.start_monitor).pack(side="left")
        self.action_button(buttons, "安全停止", self.stop_monitor, DANGER_COLOR).pack(side="left", padx=10)
        self.action_button(buttons, "立即扫描一次", self.scan_once, "#2f6570").pack(side="left")
        tk.Label(card, text="立即扫描会按当前规则自动创建达到阈值的项目，请只在确认配置后使用。", bg=PANEL_COLOR, fg=WARNING_COLOR, font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=20, pady=(0, 18))
        startup = self.card(page)
        startup.pack(fill="x", padx=32, pady=(0, 14))
        tk.Label(startup, text="开机自启", bg=PANEL_COLOR, fg=TEXT_COLOR, font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=20, pady=(18, 5))
        tk.Label(startup, text="登录 Windows 后自动启动后台监控。软件会优先使用计划任务，权限不足时自动改用启动文件夹。", bg=PANEL_COLOR, fg=MUTED_COLOR, font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=20)
        startup_actions = tk.Frame(startup, bg=PANEL_COLOR)
        startup_actions.pack(fill="x", padx=20, pady=16)
        self.action_button(startup_actions, "安装开机自启", self.install_startup).pack(side="left")
        self.action_button(startup_actions, "取消开机自启", self.uninstall_startup, "#6b7280").pack(side="left", padx=10)
        self.startup_status = tk.Label(startup_actions, text="", bg=PANEL_COLOR, fg=MUTED_COLOR, font=("Microsoft YaHei UI", 9))
        self.startup_status.pack(side="left", padx=12)

    def _build_logs(self):
        page = self.page_frame("logs", "运行日志", "日志默认保留 72 小时。")
        card = self.card(page)
        card.pack(fill="both", expand=True, padx=32, pady=(0, 22))
        actions = tk.Frame(card, bg=PANEL_COLOR)
        actions.pack(fill="x", padx=16, pady=14)
        self.action_button(actions, "刷新日志", self.refresh_logs, "#2f6570").pack(side="left")
        self.action_button(actions, "打开日志文件夹", self.open_logs, "#6b7280").pack(side="left", padx=10)
        self.log_text = tk.Text(card, bg=PANEL_COLOR, fg=TEXT_COLOR, relief="flat", borderwidth=0, wrap="none", font=("Consolas", 9), state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    def show_page(self, key):
        for name, page in self.pages.items():
            page.pack_forget()
            self.nav_buttons[name].configure(bg="#12343b")
        self.pages[key].pack(fill="both", expand=True)
        self.nav_buttons[key].configure(bg="#1c545b")

    def set_text(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def refresh_all(self):
        self.refresh_dashboard()
        self.refresh_accounts()
        self.refresh_auth_fields()
        self.refresh_logs()
        self.refresh_startup_status()

    def auto_refresh(self):
        self.refresh_dashboard()
        self.refresh_accounts()
        self.refresh_logs()
        self.after(10000, self.auto_refresh)

    def refresh_dashboard(self):
        status = status_panel.collect_status(self.base_dir)
        self.metric_vars["running"].set("运行中" if status["running"] else "未运行")
        self.metric_vars["accounts"].set(str(status["account_count"]))
        self.metric_vars["projects"].set(str(status["project_count"]))
        self.metric_vars["full"].set(str(len(status["full_projects"])))
        self.metric_vars["failures"].set(str(status["failure_count"]))
        self.overview_status.configure(text=f"最近扫描：{status['generated_at']}")
        for item in self.risk_tree.get_children():
            self.risk_tree.delete(item)
        risk_rows = status["full_projects"] + status["near_projects"]
        for row in risk_rows:
            self.risk_tree.insert("", "end", values=(row.get("account"), row.get("name"), row.get("units")))
        if not risk_rows:
            self.risk_tree.insert("", "end", values=("", "当前没有单元数达到 80 的项目", ""))
        self.set_text(self.recent_log, "\n".join(status["recent_logs"] or ["暂无日志"]))

    def refresh_accounts(self):
        ids = load_account_ids(self.base_dir)
        current = self.account_text.get("1.0", "end").strip()
        if not current:
            self.account_text.insert("1.0", "\n".join(ids))
        self.account_hint.configure(text=f"当前保存 {len(ids)} 个账户 ID")
        status = status_panel.collect_account_status(self.base_dir)
        for item in self.account_tree.get_children():
            self.account_tree.delete(item)
        for account in status["accounts"]:
            account_name = account.get("advertiser_name") or account.get("advertiser_id")
            for project in account.get("projects") or []:
                self.account_tree.insert("", "end", values=(account_name, project.get("name"), project.get("unit_count"), project.get("project_id")))

    def refresh_auth_fields(self):
        settings = load_interface_settings(self.base_dir)
        for key, value in settings.items():
            if not self.auth_vars[key].get():
                self.auth_vars[key].set(value)

    def refresh_logs(self):
        parts = []
        for filename in ("project_monitor.log", "desktop_ui.log"):
            path = self.base_dir / "logs" / filename
            lines = status_panel.tail_lines(path, 80)
            if lines:
                parts.append(f"[{filename}]\n" + "\n".join(lines))
        if hasattr(self, "log_text"):
            self.set_text(self.log_text, "\n\n".join(parts) if parts else "暂无日志")

    def refresh_startup_status(self):
        script = self.base_dir / "scripts" / "startup_status.ps1"
        if not script.exists():
            self.startup_status.configure(text="当前软件版未生成开机自启脚本")
            return
        try:
            output = subprocess.check_output(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-BaseDir", str(self.base_dir)], text=True, encoding="utf-8", errors="replace", timeout=12, **hidden_subprocess_kwargs())
            self.startup_status.configure(text="已启用" if "True" in output else "未启用")
        except (OSError, subprocess.SubprocessError):
            self.startup_status.configure(text="状态读取失败")

    def save_accounts(self):
        try:
            ids = save_account_ids(self.base_dir, self.account_text.get("1.0", "end"))
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        append_ui_log(self.base_dir, f"account ids saved count={len(ids)}")
        clear_scan_cache(self.base_dir)
        self.refresh_dashboard()
        self.refresh_accounts()
        if ids:
            self.account_hint.configure(text=f"已保存 {len(ids)} 个账户 ID")
            messagebox.showinfo(APP_TITLE, "账户 ID 已保存，下次扫描将按新列表执行。")
        else:
            self.account_hint.configure(text="未手动指定账户，将使用授权账户")
            messagebox.showinfo(APP_TITLE, "已清空手动账户 ID。请重新导入授权，软件将使用本次授权返回的账户。")

    def import_auth(self):
        try:
            save_interface_settings(self.base_dir, self.auth_vars["app_id"].get(), self.auth_vars["secret"].get(), self.auth_vars["callback"].get())
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        self.auth_status.configure(text="正在导入授权，请稍候…")
        self.set_text(self.auth_output, "正在向千川验证授权…")
        threading.Thread(target=self._import_auth_worker, daemon=True).start()

    def _import_auth_worker(self):
        script = self.base_dir / "scripts" / "import_qianchuan_auth.ps1"
        command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-BaseDir", str(self.base_dir)]
        try:
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, **hidden_subprocess_kwargs())
            output = (result.stdout + "\n" + result.stderr).strip()
            ok = auth_import_succeeded(result.returncode, output, self.base_dir)
            append_ui_log(self.base_dir, f"auth import exit={result.returncode}")
        except (OSError, subprocess.SubprocessError) as exc:
            output, ok = str(exc), False
            append_ui_log(self.base_dir, f"auth import error={exc}")
        self.after(0, lambda: self._finish_auth_import(ok, output))

    def _finish_auth_import(self, ok, output):
        self.set_text(self.auth_output, output or "未返回结果")
        has_account_warning = "ERROR project list failed" in output
        self.auth_status.configure(text="授权已导入，账户列表有警告" if ok and has_account_warning else "授权导入成功" if ok else "授权导入失败，请查看结果")
        if ok:
            detail = "授权导入成功。现在可以启动后台监控。"
            if has_account_warning:
                detail += "\n\n账户 ID 列表中有当前授权无权限的账户，请在“账户与项目”中删除或替换这些账户 ID。"
            messagebox.showinfo(APP_TITLE, detail)
        else:
            messagebox.showerror(APP_TITLE, "授权导入失败，请查看页面中的错误信息。")

    def start_monitor(self):
        if not auth_is_ready(self.base_dir):
            messagebox.showerror(APP_TITLE, "尚未导入授权。请先在“授权配置”保存并导入授权。")
            self.show_page("auth")
            return
        stop_file = project_monitor.stop_file_path(self.base_dir)
        stop_file.unlink(missing_ok=True)
        status = status_panel.collect_status(self.base_dir)
        if status["running"]:
            messagebox.showinfo(APP_TITLE, "后台监控已经在运行。")
            return
        try:
            subprocess.Popen(worker_command(self.base_dir), cwd=self.base_dir, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"启动失败：{exc}")
            append_ui_log(self.base_dir, f"monitor start failed error={exc}")
            return
        append_ui_log(self.base_dir, "monitor start requested")
        self.overview_status.configure(text="后台监控正在启动，首次扫描约需 1 分钟")
        self.after(1500, self.refresh_dashboard)

    def stop_monitor(self):
        stop_file = project_monitor.stop_file_path(self.base_dir)
        stop_file.parent.mkdir(parents=True, exist_ok=True)
        stop_file.write_text("stop\n", encoding="utf-8")
        append_ui_log(self.base_dir, "monitor stop requested")
        messagebox.showinfo(APP_TITLE, "已请求停止。当前 API 扫描结束后，后台监控会安全退出。")

    def scan_once(self):
        if not auth_is_ready(self.base_dir):
            messagebox.showerror(APP_TITLE, "尚未导入授权。请先在“授权配置”保存并导入授权。")
            self.show_page("auth")
            return
        if not messagebox.askyesno(APP_TITLE, "立即扫描将按规则创建达到阈值的项目。确认继续？"):
            return
        try:
            subprocess.Popen(worker_command(self.base_dir, once=True), cwd=self.base_dir, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), close_fds=True)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"启动扫描失败：{exc}")
            return
        append_ui_log(self.base_dir, "one-time scan requested")
        self.overview_status.configure(text="已启动一次扫描")

    def run_startup_script(self, name, success_text):
        script = self.base_dir / "scripts" / name
        if not script.exists():
            messagebox.showerror(APP_TITLE, "开机自启脚本不存在。")
            return
        def worker():
            try:
                result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), "-BaseDir", str(self.base_dir)], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45, **hidden_subprocess_kwargs())
                output = (result.stdout + "\n" + result.stderr).strip()
                ok = result.returncode == 0
            except (OSError, subprocess.SubprocessError) as exc:
                output, ok = str(exc), False
            append_ui_log(self.base_dir, f"startup script={name} exit={int(ok)} output={output[:180]}")
            self.after(0, lambda: self._finish_startup(ok, success_text, output))
        threading.Thread(target=worker, daemon=True).start()

    def _finish_startup(self, ok, success_text, output):
        self.refresh_startup_status()
        if ok:
            messagebox.showinfo(APP_TITLE, success_text)
        else:
            messagebox.showerror(APP_TITLE, f"操作失败：{output}")

    def install_startup(self):
        self.run_startup_script("install_startup.ps1", "开机自启已安装。")

    def uninstall_startup(self):
        self.run_startup_script("uninstall_startup.ps1", "开机自启已取消。")

    def open_logs(self):
        log_dir = self.base_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(log_dir)


def main():
    if "--worker" in sys.argv:
        sys.argv = [arg for arg in sys.argv if arg != "--worker"]
        project_monitor.main()
        return
    ManagerApp(application_base_dir()).mainloop()


if __name__ == "__main__":
    main()

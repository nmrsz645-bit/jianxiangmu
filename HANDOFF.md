# 建项目监控交接文档

本文档对应 `v2.0.6` 发布线。权威代码版本由 `main` 与 `v2.0.6` tag 指向的提交决定；接手时先运行 `git fetch --tags origin`、`git status --short --branch` 和 `git show --no-patch v2.0.6`，不要仅凭 EXE 修改时间或目录名称判断版本。

## 1. 用途、边界与架构

这是 Windows 本地 Tkinter 桌面程序，不是云服务。它读取当前电脑上由使用者自行导入的千川授权，扫描目标账户的项目和单元；最高 `_数字` 尾缀项目达到默认阈值 88 时，创建下一个项目并复制源项目最新单元。

流程为：桌面界面保存本机配置并调用授权脚本 → 授权脚本向千川接口交换 Token → 后台 worker 定期调用项目/单元接口 → 状态和失败队列写入本机 `data/`，日志写入本机 `logs/` → 界面读取这些本地状态并展示。

本仓库不保存也不应获取任何真实 APP_ID、Secret、回调地址、Token、账户 ID、浏览器登录资料、业务数据或日志。当前版本已移除源码内置账户 ID；无手动账户列表时，只使用本次授权返回的账户数据或使用者本机配置的账户字段。

## 2. 目录与关键模块

| 位置 | 作用 |
| --- | --- |
| `app/manager_gui.py` | Tkinter 界面、授权和账户输入、启动/停止 worker、开机自启操作。冻结后的 EXE 从自身目录作为数据根目录。 |
| `app/project_monitor.py` | 千川 HTTP 客户端、项目组/尾缀规则、项目与单元创建、失败队列、worker CLI。默认扫描间隔 600 秒、失败重试间隔 180 秒。 |
| `app/status_panel.py` | 读取本机扫描快照、失败队列和日志，识别 worker 进程并生成状态数据。 |
| `scripts/import_qianchuan_auth.ps1` | 从本机接口文本读取授权信息、换取 Token，并将结果写入被忽略的 `config/` 与 `data/`。只能由当前使用者在本机运行。 |
| `scripts/probe_qianchuan.ps1` | 授权导入过程调用的千川 API 探测和本机状态写入。 |
| `scripts/build_desktop_release.ps1` | 使用 PyInstaller 生成 `release/建项目监控-<版本>`，复制 EXE、`_internal/`、`scripts/`、使用说明和版本文件。 |
| `scripts/install_startup.ps1`、`uninstall_startup.ps1`、`startup_status.ps1` | 当前 Windows 用户的开机自启管理；优先计划任务，失败时使用启动文件夹。 |
| `scripts/watchdog*.bat`、`scripts/watchdog_mutex.ps1` | 源码模式下的 watchdog 和单实例锁；Release GUI 启动 worker 时不依赖它们。 |
| `tests/` | `unittest` 风格测试，由 pytest 运行。 |
| `release_template/` | 会被复制到 Release 的 `使用说明.txt` 和 `version.json`；不得放入任何本机配置文本。 |

## 3. 环境、启动、测试与构建

经本轮验证的环境是 Windows、Python `3.13.15`、pytest `9.2.0`、PyInstaller `6.22.3`。应用运行时只使用 Python 标准库；开发依赖为 pytest 和 PyInstaller。

```powershell
py -3.13 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt
.\\.venv\\Scripts\\python.exe -m pip check
.\\.venv\\Scripts\\python.exe -m pytest -q
.\\.venv\\Scripts\\python.exe app\\manager_gui.py

$env:PATH = "$PWD\\.venv\\Scripts;$env:PATH"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\build_desktop_release.ps1
```

本轮针对发布线运行的测试结果为 `39 passed`。GitHub Actions 在推送到 `main` 或向 `main` 提交 PR 时，会使用 Windows + Python 3.13 运行同一测试命令并在 Runner 临时目录执行构建。该工作流不部署、不发布到下载站，也不改线上更新清单。

## 4. 本机安全配置与获取方式

使用者在 GUI 的 **授权配置** 输入以下内容，程序在本机根目录创建被 `.gitignore` 排除的接口文本，并在导入后创建私密配置与 Token 文件：

```text
APP_ID
<使用者本人在千川/OceanEngine 已获授权应用中取得的数字 APP_ID>
Secret
<同一应用的 Secret>
callback_url: <该应用登记的完整回调 URL，且带 auth_code 参数>
```

APP_ID、Secret 和完整回调地址只能由有权管理该千川/OceanEngine 应用的当前使用者从其官方应用配置和授权流程取得。维护者不得索要、伪造、猜测、提交或迁移这些值。账户 ID 由使用者在 GUI 的 **账户与项目** 自行填写；留空时程序使用当前授权返回的账户。

以下路径永远不应被读取、打印、提交、上传、打进 Release 或在升级时覆盖：`config/`、`data/`（尤其 `tokens.json`、失败队列、扫描快照）、`logs/`、根目录及 `release_template/` 中的 `千川接口.txt`、`账户ID.txt`、`项目名称.txt`。任何创建项目请求/响应日志也可能含业务信息。

## 5. 发布与升级流程

1. 从干净工作树确认 `main`、`origin/main` 和版本文件；不要覆盖他人未提交的改动。
2. 使用 Python 3.13 创建 `.venv`，安装 `requirements-dev.txt`，执行完整测试和 `pip check`。
3. 审查 Git 已跟踪文件、历史变更和候选包，确认没有凭据、真实账户/业务数据、浏览器资料或私密文件。
4. 执行 `scripts/build_desktop_release.ps1`，并检查候选目录至少包含 `建项目监控/建项目监控.exe`、`建项目监控/_internal/`、`scripts/`、`使用说明.txt`、`version.json`。
5. 在无真实授权的隔离目录做受控启动检查；构建或启动失败必须如实记录，不得把未验证包标为可运行。
6. 用 SHA-256 记录整个 ZIP 附件校验值。仅在源码提交、tag、测试、包内容和附件都对应同一版本后创建 GitHub Release。
7. 升级已安装客户端时只替换程序、`_internal/`、脚本和说明；保留用户的私密目录和根目录配置文本。不得静默替换旧 Release、发布包、线上更新清单或下载站内容。

## 6. 已完成、未完成与已知限制

已完成：源码测试、Release 构建脚本、GitHub Actions 验证工作流、`v2.0.6` 文档和安装包发布流程。本轮删除了内置账户 ID，并用测试保证未配置账户时不会再自动使用源码中的账户。

未完成或需人工处理：本轮不使用真实授权，因此未对真实千川 API 做端到端创建验证；旧客户端升级到本版本仍需要在隔离副本上做一次保留用户数据的实际升级回读验证。若账户达到千川项目数上限，程序只记录失败，不会自动删除项目。

已知运行限制：本版 EXE 没有商业代码签名，Windows 可能显示 SmartScreen 提示；不要通过关闭系统安全功能规避。失败队列 JSON 损坏时，程序会将原文件改名为带时间戳的 `.bad` 文件并重建空队列。日志默认清理 72 小时前的文件。

## 7. 后续修改入口

- 修改项目命名、阈值、重试或 API 调用：从 `app/project_monitor.py` 和对应 `tests/test_project_monitor.py` 开始；先写失败测试。
- 修改桌面界面或本机配置校验：从 `app/manager_gui.py` 和 `tests/test_manager_gui.py` 开始。
- 修改状态展示或进程识别：从 `app/status_panel.py` 和 `tests/test_status_panel.py` 开始。
- 修改打包内容：同时更新 `scripts/build_desktop_release.ps1`、`release_template/` 与 README，并重新验证候选目录。
- 修改发布版本：先更新 `release_template/version.json`，再测试、构建、审计、tag 和创建新 Release；不要伪造版本或覆盖旧附件。

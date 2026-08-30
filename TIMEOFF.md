# 交接说明：建项目监控

最后更新：2026-08-31。此文件用于让新的 Codex 会话脱离聊天历史继续工作。

## 当前交接基线

- Git 仓库：`https://github.com/nmrsz645-bit/jianxiangmu.git`；工作分支：`main`。
- 交接基线：以 `main` 的当前 `HEAD` 与 `origin/main` 为准；接手前必须运行 `git status --short --branch` 和 `git log -1 --oneline`。
- 最后一次本地自动化测试：`python -m pytest -q`，结果为 `38 passed`。
- 远端自动化测试：`.github/workflows/tests.yml` 已随仓库提交；推送到 `main` 或提交 Pull Request 时，GitHub Actions 会在 Windows + Python 3.13 上运行测试。
- 本交接只包含代码与说明；授权、账户 ID、令牌、用户配置、运行状态和日志均不在 Git 中，且不得通过 Git 迁移。

## 接手顺序

1. 先阅读 `README.md`、`AGENTS.md`、本文件 `TIMEOFF.md`，再执行“下一步具体操作”中的第一步。
2. 先确认仓库状态、最近提交、测试结果和发布模板版本；不要仅根据目录名、EXE 修改时间或界面版本号判断新版来源。
3. 只有定位并核实用户实际安装版本的源码来源后，才可以修复、打包或发布；涉及发布时必须保护用户本地数据并做可回退验证。

## 当前目标

维护 Windows 本地桌面程序“建项目监控”。程序定期扫描指定千川账户的项目单元数；当同一项目组中最高尾缀项目达到 88 个单元时，创建名称尾缀加 1 的新项目，并复制源项目的最新单元。程序需要支持安全的云端更新，更新不得破坏用户本机授权和运行数据。

## 已完成并验证

- Git 仓库已初始化并推送：`https://github.com/nmrsz645-bit/jianxiangmu.git`，分支 `main`。
- 已加入 `.gitignore`，授权、账户、运行状态、日志和本地构建产物均不提交。
- 已新增 `README.md`、`AGENTS.md`、`requirements-dev.txt`。
- 已新增 GitHub Actions 工作流 `.github/workflows/tests.yml`：每次推送到 `main` 或提交 Pull Request 时，使用 Windows + Python 3.13 自动执行 `python -m pytest -q`。
- 源码默认扫描间隔为 600 秒（10 分钟），位置：`app/project_monitor.py` 中的 `DEFAULT_INTERVAL_SECONDS`。
- 已运行 `python -m pytest -q`，结果：`38 passed`。
- 已修复失败队列容错：`data/failure_queue.json` 为空、JSON 损坏或内容不是数组时，程序会将原文件改名为带时间戳的 `.bad` 备份并初始化空队列，不再因该文件直接崩溃；对应测试已通过。
- 已新增 `scripts/build_desktop_release.ps1` 并做过一次真实构建验证。候选包包含 `建项目监控\建项目监控.exe`、`建项目监控\_internal\`、`scripts\`、`使用说明.txt` 和 `version.json`，不包含用户授权或运行数据。
- 当前发布版可执行文件曾在 `E:\自动化\建项目_软件版_20260719_004450\建项目监控.exe` 验证，构建时间为 2026-07-24；该文件与 `E:\自动化\建项目\_software_dist_10min_20260724\建项目监控\建项目监控.exe` 哈希一致。
- 已知云端发布包位置：`E:\自动化\gengxin\releases\packages\jian-xiang-mu-2.0.4.zip`。不在本次交接中重新发布或覆盖它。

## 未完成事项

1. **版本一致性核查**：`release_template/version.json` 当前为 `2.0.1`，但用户实际安装界面曾显示 `v2.0.5`。在任何构建、发布或云端更新前必须先确认哪个代码目录对应 `2.0.5`，避免将旧源码重新发布为新版。
2. **云端更新验证**：云端更新机制由另一会话维护。更新必须只替换程序和依赖，不得覆盖用户数据；需要一次真实的“旧版更新到新版”验证并回读用户文件。

## 下一步具体操作

**第一步（直接照做，不修改任何文件）：**

```powershell
cd E:\自动化\建项目
git status --short --branch
git log -1 --oneline
python -m pytest -q
Get-Content .\release_template\version.json -Raw
```

确认仓库干净、测试仍通过，并记录源码版本号。随后在修改前，定位用户实际 `v2.0.5` 安装包或其构建来源，与本仓库 `app/` 逐文件比较；若来源不明，先停在此处向用户确认，不要发布。

## 关键文件与路径

- 主逻辑：`app/project_monitor.py`
- 桌面 GUI：`app/manager_gui.py`
- 状态面板：`app/status_panel.py`
- 单元测试：`tests/test_project_monitor.py`、`tests/test_manager_gui.py`、`tests/test_status_panel.py`
- 授权导入：`scripts/import_qianchuan_auth.ps1`
- 账户/API 探测：`scripts/probe_qianchuan.ps1`
- 守护进程：`scripts/watchdog.bat`、`scripts/watchdog_loop.bat`
- 桌面包构建：`scripts/build_desktop_release.ps1`
- Windows 启动入口：`启动项目监控.bat`、`守护启动.bat`、`导入授权.bat`
- 发布模板：`release_template/`
- 当前源码目录：`E:\自动化\建项目`
- 当前 Git 远端：`origin = https://github.com/nmrsz645-bit/jianxiangmu.git`

## 运行与验证命令

```powershell
# 开发依赖与测试
python -m pip install -r requirements-dev.txt
python -m pytest -q

# 本地启动桌面程序
python app\manager_gui.py

# 构建候选桌面包（不发布）
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_desktop_release.ps1

# Git 检查
git status --short --branch
git log -1 --oneline
```

桌面版使用 PyInstaller 打包；`_software_build*` 和 `_software_dist*` 是历史本机构建/输出目录，不是唯一发布物。新构建请使用 `scripts/build_desktop_release.ps1`，交付时必须复制生成目录的全部内容，不得只复制 EXE。发布前在新目录构建、验证后再交给云端更新流程。

## 已知问题与运行事实

- 失败队列文件损坏会自动备份为 `.bad` 并重建空队列；不要手动改动 `tokens.json`。
- 千川账户达到 30 个项目上限时，接口拒绝创建项目。这是当前接受的业务限制，不做自动删除、自动绕过或额外优化；需要继续创建时由用户自行处理账户中的旧项目。
- 常规扫描是每 10 分钟；失败队列存在时重试可能早于 10 分钟。
- 任何旧验证目录、旧构建输出或云端发布目录都可能被用于回滚。未确认云端更新机制前不要清理它们。

## 绝对不能误动的数据和配置

以下均为每台电脑独立数据，严禁读取内容、提交到 Git、上传、删除、覆盖或在更新时替换：

- `config/`
- `data/`，尤其是 `data/tokens.json`、`failure_queue.json`、运行状态和扫描快照
- `logs/`
- 根目录 `千川接口.txt`、`账户ID.txt`、`项目名称.txt`
- 用户自建的同目录配置/文本文件
- 云端当前发布包和唯一备份

`.gitignore` 已排除上述内容。新电脑必须重新授权或由用户自行安全迁移本地数据；不要通过 Git 迁移凭据。

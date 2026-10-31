# 新 Windows 接手、更新与发布指南

本指南只描述 `nmrsz645-bit/jianxiangmu` 已存在并经源码核对的流程。当前正式发布线为 `main` + GitHub Release/tag；`v2.0.6` 是现有正式 Release。不要把一次 `git push` 误认为客户端已经更新：本项目的 GitHub Actions 只测试和在 Runner 临时目录构建，不会上传安装包、部署网站、写 OSS 或修改任何线上更新清单。

## 1. 分支与新机器接手

正式源码以 `main` 为准；对功能或发布流程的实验应在主题分支或 Pull Request 进行。向 `main` 推送会触发 `.github/workflows/tests.yml` 的 Windows + Python 3.13 测试和临时构建，成功并不自动创建 Release。新电脑只从 GitHub 克隆源码或从对应 GitHub Release 下载完整安装包，不从旧电脑复制任何文件。

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.13 -e

git clone https://github.com/nmrsz645-bit/jianxiangmu.git
cd jianxiangmu
git fetch --tags origin
git status --short --branch
git log -1 --oneline
git show --no-patch v2.0.6
```

本轮实际验证的工具版本为 Git `2.53.0.windows.3` 与 Python `3.13.15`。系统默认 `python` 可能仍指向其他版本，因此所有开发、测试和构建命令都应使用本仓库的 Python 3.13 虚拟环境：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe app\manager_gui.py
```

`app\project_monitor.py --help` 当前提供 `--base-dir`、`--threshold`、`--interval`、`--root-account`、`--once` 和 `--dry-run`。这些是本地 worker 参数，不是发布或上传参数。

## 2. 可迁移与不可迁移的数据

可迁移的只有 Git 源码和 GitHub Release 中的程序文件。每台电脑都必须由当前使用者在程序“授权配置”中重新完成授权并按需填写账户 ID。

严禁复制、上传、提交或把以下内容打进安装包：`config/`、`data/`、`logs/`、`千川接口.txt`、`账户ID.txt`、`项目名称.txt`、`tokens.json`、`.env`、浏览器登录态、Cookie、DPAPI 保护的数据、浏览器 Profile、真实回调地址、任何 Token/Secret 或业务数据。仓库没有用于导出或导入这些资料的安全迁移脚本；不要自行发明迁移方式。

## 3. 修改版本与构建完整包

版本的唯一源码位置是 `release_template\version.json` 的 `version` 字段。变更正式版本时，先在干净工作树更新该字段以及与版本有关的说明，再重新测试和构建；不得仅修改 EXE 文件名或 Release 标题来伪造版本。

现有构建脚本只有 `scripts\build_desktop_release.ps1`，可选参数仅为 `-OutputDir`。它生成完整目录 `release\建项目监控-<version>`，并复制 `建项目监控\建项目监控.exe`、`建项目监控\_internal\`、`scripts\`、`使用说明.txt` 与 `version.json`。没有增量包、补丁包或差分包生成器。

```powershell
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build_desktop_release.ps1

# 只在确认同名 ZIP 不存在时执行；压缩包根目录应为上述五类交付文件。
Compress-Archive -Path .\release\建项目监控-<version>\* -DestinationPath .\release\建项目监控-<version>.zip -CompressionLevel Optimal
Get-FileHash .\release\建项目监控-<version>.zip -Algorithm SHA256
```

构建脚本会拒绝覆盖已有同版本目录。不要通过删除未知旧包来绕过该保护；请使用新的干净构建目录或先明确确认旧包的归属和可回滚性。

## 4. 实际客户端更新方式

截至本指南提交时，源码中不存在自动更新客户端、更新 manifest、OSS bucket/key、catalog、下载站发布脚本或增量更新协议。可行且已验证的交付方式只有：上传完整 ZIP 到同版本 GitHub Release，然后由使用者手工解压并替换程序文件。

未来创建新版本 Release 的顺序如下。第 5 步是有权限的发布者在确认前四步后执行的生产动作，本轮文档更新未执行该命令。

1. 在主题分支或干净的 `main` 工作树完成代码/文档，审查已跟踪文件和候选包，排除私密数据。
2. 使用 Python 3.13 虚拟环境运行 `.\\.venv\\Scripts\\python.exe -m pytest -q` 与 `.\\.venv\\Scripts\\python.exe -m pip check`，再执行构建和 SHA-256 核验。
3. 确认 `version.json`、ZIP 名称、Release tag 和提交描述使用同一新版本号；不要覆盖已有 tag 或旧 Release 附件。
4. 普通提交并推送源码与新 tag；推送后确认 GitHub Actions 测试和临时构建完成。
5. 使用已登录且有仓库 Release 权限的 GitHub CLI 上传已核验 ZIP，例如：

```powershell
gh release create v<version> .\release\建项目监控-<version>.zip --repo nmrsz645-bit/jianxiangmu --title "建项目监控 <version>" --verify-tag --notes "SHA-256: <hash>"
```

当前 `v2.0.6` 的完整包在 GitHub Release 中；其校验值以 Release 说明和 `Get-FileHash` 的一致结果为准。GitHub Release 是本项目当前唯一的已验证发布目标，不是 OSS 或网站 catalog 的替代实现。

## 5. 网站与下载站边界

本仓库不包含网站静态 `index.html`、下载卡片 ID、运行时 catalog/manifest 字段，因而不能在这里配置或验证下载站映射。也不要据此推断存在 OSS bucket/key 或自动更新端点。

共享网站由另一个会话维护；其通用发布指南的预定地址是 [PUBLISHING.md](https://github.com/nmrsz645-bit/software-download-center/blob/docs-cross-pc-handoff/docs/PUBLISHING.md)，其中的相关锚点为 `#website`、`#catalog`、`#client-update`、`#verify-rollback` 与 `#credentials`。本轮只读核验时，该指定分支在 GitHub 返回 404，故没有确认任何建项目监控卡片 ID、index 字段或外部 catalog 对象。网站维护会话完成并使链接可读前，不得把本项目的 GitHub Release 假定为已出现在下载站。

如果将来该网站分支可用，网站维护者仍须按其指南单独把本项目的版本、GitHub Release 下载地址与 SHA-256 映射到网站；本项目仓库不提供该动作的脚本或凭据。本轮未修改网站仓库、OSS、catalog 或生产下载页。

## 6. 发布后验证、手工升级与回滚

发布后必须从 GitHub 远端核验 tag 指向预期提交、Release 不是 draft、附件名称/大小/SHA-256 已上传。随后在隔离目录下载 ZIP 并检查 `version.json`，再验证哈希：

```powershell
Get-FileHash .\jianxiangmu-monitor-<version>-windows.zip -Algorithm SHA256
```

在没有真实授权的隔离目录中启动 EXE，确认界面可存活后受控退出；不要在该检查中导入任何账户、Secret 或浏览器资料。真实千川 API 的授权、扫描和创建行为必须由有权使用者另行验证。

升级已安装客户端时，先关闭后台监控并备份原有程序文件，然后只替换 `建项目监控\建项目监控.exe`、`建项目监控\_internal\`、`scripts\`、`使用说明.txt` 和 `version.json`。保留本机的 `config/`、`data/`、`logs/` 与根目录用户配置文本。若新包不能启动，停止其进程并恢复先前验证过的完整程序文件，同时仍保留这些私密目录；不要用旧包覆盖用户授权或运行数据。

## 7. 权限与凭据

源码推送和 Release 上传需要仓库内容写入与 Release 权限；在本机只可通过 `gh auth status` 确认登录状态，不得输出或复制访问 Token。当前 GitHub Actions 工作流不引用仓库 Secrets，也不含 OSS 凭据名称。

应用运行所需的 APP_ID、Secret、完整回调地址和账户 ID 由当前使用者从自己有权管理的千川/OceanEngine 应用和授权流程取得，并只在本机 GUI 中填写。它们不是 GitHub 发布凭据，也不能被写入 README、HANDOFF、Release notes、测试样例或网站内容。

## 8. 已知缺项与未验证事项

- 没有自动更新、增量包、manifest、OSS/cdn 发布脚本或可验证的网站卡片配置。
- 本轮没有执行任何生产上传命令、OSS 操作、网站修改或线上更新清单修改。
- 当前共享网站指南链接的指定分支返回 404；其字段、catalog 和卡片映射未验证。
- 本项目未在真实授权下做端到端扫描/创建验证；Release GUI 只能在无授权隔离环境进行受控启动检查。
- EXE 尚未使用商业代码签名，Windows 可能显示 SmartScreen 提示；不得通过关闭系统防护规避。

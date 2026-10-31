# 交接入口

本文件保留给旧会话和旧链接。完整、当前且可维护的交接文档已迁移至 [HANDOFF.md](HANDOFF.md)。

接手前请依次阅读 `README.md`、`AGENTS.md` 和 `HANDOFF.md`，并在不改动任何文件的前提下运行：

```powershell
git status --short --branch
git log -1 --oneline
Get-Content .\\release_template\\version.json -Raw
```

完成 Python 3.13 虚拟环境和开发依赖安装后，再运行：

```powershell
.\\.venv\\Scripts\\python.exe -m pytest -q
```

不要从旧电脑迁移或读取授权、Token、Secret、账户 ID、配置、运行数据或日志。新电脑只能从源码或对应 GitHub Release 安装程序，并由当前使用者在软件内重新完成授权。

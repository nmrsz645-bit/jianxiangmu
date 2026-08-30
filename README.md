# 建项目监控

Windows 本地桌面程序。它定期检查指定千川账户的项目单元数；项目达到 88 条时，按项目名称尾缀新建下一个项目并复制最新单元。

## 开发环境

需要 Windows、Python 3.13+ 和 PowerShell。安装开发依赖：

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

推送到 `main` 或创建 Pull Request 时，GitHub Actions 会在 Windows + Python 3.13 环境自动执行同一套测试。

本地运行桌面程序：

```powershell
python app\manager_gui.py
```

## 用户数据与授权

以下内容是每台电脑独立的私密运行数据，不在 Git 中保存：`config/`、`data/`、`logs/`、`千川接口.txt`、`账户ID.txt`、`项目名称.txt`。

新电脑需要通过桌面程序重新导入授权并填写账户 ID。不要复制或提交 `data/tokens.json`、接口 Secret、完整回调链接。

## 当前行为

- 常规扫描间隔：10 分钟。
- 项目达到 88 条时才尝试新建；新名称为最高尾缀加 1。
- 单账户项目数受千川接口限制。接口返回“已创建 30 个项目”时，无法继续新建，需人工清理旧项目。
- 失败任务会写入本机 `data/failure_queue.json` 并重试。

## 发布

桌面包由 PyInstaller 生成。构建产物不提交 Git；发布前在干净目录构建并验证。云端更新只能替换程序文件与依赖，必须保留用户数据目录和根目录用户配置文件。

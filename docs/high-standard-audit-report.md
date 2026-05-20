# 高标准审计报告

当前仓库级验收入口是 GitHub Actions `Windows Acceptance`。此文档不固定最新 run id，因为任何新的 push 都会刷新该记录；如需查看当前状态，以 `main` 分支上的最新 workflow 记录为准。当前人工封版 tag 使用 `acceptance-20260518-r2`，历史封版 `acceptance-20260518`（commit `7e2fdb3`）继续保留；`main` 在封版后又合入了任务/模型路由错误 JSON 化与严格审计瞬时静态资源失败重试两项硬化，当前主线收口摘要见 [acceptance-handoff-20260519.md](./acceptance-handoff-20260519.md)。当前 CI 基线固定 Python `3.11` / Node `24`，补充说明见 [acceptance-latest.md](./acceptance-latest.md)

## 审计目标

本轮审计按答辩现场风险优先级检查：

- 账号未初始化、弱管理员输入、未登录访问的安全边界。
- 图片、批量、帧检测、任务详情、批量报告、摄像头停止等错误输入是否给出明确失败。
- 单图样本是否能完成真实识别、详情读取和报告生成。
- 登录页、主工作台、报告页是否能由真实浏览器渲染，不出现空白页或错误页。
- 审计过程是否隔离真实数据库、上传目录和输出目录。

## 当前结论

通过。

- `scripts/audit_readiness.py` 已通过，且确认真实 `data/admin_config.json`、`data/user_config.json`、`data/detections.db`、`uploads`、`outputs` 状态未被审计脚本改变。
- `scripts/browser_visual_audit.ps1` 已通过，使用本机 Edge headless 生成真实浏览器截图。
- `scripts/strict_system_audit.py` 已通过，`docs/_artifacts/strict-system-audit.json` 当前为 `overall_status=passed`、`issues=[]`，覆盖 14 条真实浏览器流转，包含 1440 / 1366 / 390 三种视口。
- 2026-05-19 合入后的 `main` commit `ad9c2e0` 已在 GitHub Actions `Windows Acceptance` 上通过，说明主线在补入路由错误 JSON 化与严格审计重试硬化后仍保持仓库级总验收绿色。
- `scripts/webcam_probe.py --live-seconds 2` 已复跑通过，本机 `0` 号摄像头可通过 `CAP_DSHOW` 打开并读取 `640x480` 画面，实时任务可启动、停止并保存原图/结果图；当前脚本默认写入隔离临时目录，不污染正式项目状态。
- 批量上传“不支持文件格式时静默跳过”的风险已修复为明确返回 `400 unsupported_file`。
- 当前 GitHub Actions `Windows Acceptance` 验收链覆盖 `healthcheck`、`startup_smoke`、`frontend_service_tests`、`ui_smoke`、`interaction_smoke`、`regression_smoke`、`hardening_contracts`、`audit_readiness`、`strict_system_audit`、`browser_visual_audit`；精确到某一次通过记录时，以 `main` 分支上的最新 workflow 结果为准。
- 真实 `start_demo_session.bat` 入口的整链路演练结果已写入 `docs/_artifacts/real-demo-service-audit.json`，并补充了 `docs/_artifacts/real-demo-full-browser-summary.json` 与对应截图。
- 答辩启动入口会默认从 `models/behavior.pt` 与 `models/head.pt` 启动，同时保留运行时模型切换与其余界面功能；交互烟测已验证答辩入口下仍可切换到 `behavior02.pt`。

## 可复现命令

```powershell
.\.venv\Scripts\python.exe scripts\audit_readiness.py
```

```powershell
.\.venv\Scripts\python.exe scripts\strict_system_audit.py
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\browser_visual_audit.ps1
```

默认总验收也会运行边界审计：

```powershell
.\.venv\Scripts\python.exe scripts\verify_all.py
```

当前总验收会同时运行 `strict_system_audit.py` 与浏览器截图审计；若需要单独复现其中任一项，可直接执行上面的命令。

真实答辩入口整链路彩排：

```powershell
.\.venv\Scripts\python.exe scripts\real_demo_service_audit.py
```

摄像头硬件确认：

```powershell
.\.venv\Scripts\python.exe scripts\webcam_probe.py --live-seconds 2
```

如需保留隔离产物便于人工检查：

```powershell
.\.venv\Scripts\python.exe scripts\webcam_probe.py --live-seconds 2 --keep-temp
```

## 关键证据

`audit_readiness.py` 最近一次通过结果：

- 未初始化管理员时，`/api/auth/login` 返回 `503 setup_required`。
- 未登录访问仪表盘 API 会被重定向或拒绝。
- 管理员账号少于 3 个字符、密码少于 8 个字符会被拒绝。
- 单图缺文件返回 `400 missing_file`。
- 单图不支持扩展名返回 `400 unsupported_file`。
- 批量不支持扩展名返回 `400 unsupported_file`。
- 帧检测缺少 `image` 字段返回 `400 missing_image`。
- 不存在任务返回 `404 task_not_found`。
- 空批量报告选择返回 `400 bad_request`。
- 浏览器摄像头停止缺少任务 ID 返回 `400 webcam_unready`。
- 答辩入口启动后，学生模型初始来源显示为“启动入口默认”，并可切换到 `behavior02.pt`。
- 样本 `testfile\0014012.jpg` 完成识别，最近一次识别到 8 个目标，平均置信度约 77.7%。

真实浏览器截图产物：

- `docs/_artifacts/browser-audit-login.png`
- `docs/_artifacts/browser-audit-dashboard.png`
- `docs/_artifacts/browser-audit-webcam.png`
- `docs/_artifacts/browser-audit-report.png`
- `docs/_artifacts/browser-visual-audit.json`
- `docs/_artifacts/strict-system-audit.json`
- `docs/_artifacts/strict-system-audit-20260518-012619/`
- `docs/_artifacts/verify-all-summary.json`
- `docs/_artifacts/hardening-contracts.json`

## 变更点

- `config.py` 支持通过环境变量覆盖数据库、上传目录、输出目录、用户配置、管理员配置、运行时密钥和 YOLO 配置目录，便于隔离审计和可移植部署。
- `classroom_app/services/detection_service.py` 对批量上传中的不支持文件格式改为明确失败，避免现场误选文件后出现“假成功”。
- `classroom_app/routes/tasks.py` 与 `classroom_app/routes/models.py` 的失败分支已统一收口为 JSON 错误响应，避免前端落入不可解析的 HTML 错误页。
- `static/app/scripts/strict-system-audit.cjs` 已补入针对同源 `/static/` 瞬时加载失败的一次性 reload 重试，降低 GitHub Windows runner 网络抖动对严格审计结果的误伤。
- 新增 `scripts/audit_readiness.py`、`scripts/audit_server.py`、`scripts/strict_system_audit.py`、`static/app/scripts/strict-system-audit.cjs`、`scripts/browser_visual_audit.ps1`。
- `scripts/verify_all.py` 已纳入 `audit_readiness.py`、`strict_system_audit.py` 与 `browser_visual_audit.ps1`。

# 高标准审计报告

生成日期：以 `docs/_artifacts/verify-all-summary.json` 与 `docs/_artifacts/real-demo-service-audit.json` 为准

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
- `scripts/webcam_probe.py --live-seconds 2` 已复跑通过，本机 `0` 号摄像头可通过 `CAP_DSHOW` 打开并读取 `640x480` 画面，实时任务可启动、停止并保存原图/结果图；当前脚本默认写入隔离临时目录，不污染正式项目状态。
- 批量上传“不支持文件格式时静默跳过”的风险已修复为明确返回 `400 unsupported_file`。
- 最近一次一键总验收结果以 `docs/_artifacts/verify-all-summary.json` 为准；当前验收链覆盖 `healthcheck`、`startup_smoke`、`frontend_service_tests`、`ui_smoke`、`interaction_smoke`、`regression_smoke`、`hardening_contracts`、`audit_readiness`、`browser_visual_audit`。
- 真实 `start_demo_session.bat` 入口的整链路演练结果已写入 `docs/_artifacts/real-demo-service-audit.json`，并补充了 `docs/_artifacts/real-demo-full-browser-summary.json` 与对应截图。
- 答辩启动入口会默认从 `models/behavior.pt` 与 `models/head.pt` 启动，同时保留运行时模型切换与其余界面功能；交互烟测已验证答辩入口下仍可切换到 `behavior02.pt`。

## 可复现命令

```powershell
.\.venv\Scripts\python.exe scripts\audit_readiness.py
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\browser_visual_audit.ps1
```

默认总验收也会运行边界审计：

```powershell
.\.venv\Scripts\python.exe scripts\verify_all.py
```

当前总验收也会运行浏览器截图审计；若需要单独复现该项，仍可直接执行上面的 PowerShell 命令。

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
- `docs/_artifacts/verify-all-summary.json`
- `docs/_artifacts/hardening-contracts.json`

## 变更点

- `config.py` 支持通过环境变量覆盖数据库、上传目录、输出目录、用户配置、管理员配置、运行时密钥和 YOLO 配置目录，便于隔离审计和可移植部署。
- `classroom_app/services/detection_service.py` 对批量上传中的不支持文件格式改为明确失败，避免现场误选文件后出现“假成功”。
- 新增 `scripts/audit_readiness.py`、`scripts/audit_server.py`、`scripts/browser_visual_audit.ps1`。
- `scripts/verify_all.py` 已纳入 `audit_readiness.py` 与 `browser_visual_audit.ps1`。

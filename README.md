# 课堂行为检测系统

当前正式实现以 `app.py -> classroom_app -> templates/app_shell.html -> static/app/main.js` 为准。  
旧版原型文件已迁移到 `legacy/prototype/`，仅用于历史对照，不是当前运行入口。

## 当前功能

- 单张图片检测
- 批量图片检测
- 视频检测
- 实时摄像头检测
- 历史记录浏览
- 单任务 HTML 报告
- 批量报告 ZIP 导出，内含 `readme.txt` 与 `manifest.csv`

当前主实现**不包含双摄像头模式**。如需恢复该能力，需要同时补齐前端、路由、服务层、历史记录与回归验证。

## 环境要求

- Python 3.10+ 推荐
- Windows 10/11
- `node` 用于前端脚本语法检查与 `static/app/services/*.test.js` 原生单测
- 可选：本地摄像头设备
- 可选：YOLO `.pt` 模型文件放入 `models/`

安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 首次初始化

仓库不再内置默认管理员账号和固定 `SECRET_KEY`。

- `SECRET_KEY`：若未通过环境变量提供，应用会在本地生成 `data/runtime_secrets.json`
- 管理员账号：首次使用前执行

```powershell
.\.venv\Scripts\python.exe scripts\init_local_admin.py --username admin --password "your-password"
```

生成的 `data/admin_config.json` 已加入 `.gitignore`，不会作为仓库默认配置提交。  
`data/user_config.json` 也仅作为本机状态缓存存在，不参与仓库版本控制。

如果本地仍保留历史弱口令配置（例如旧版 `admin` 默认口令），系统会将其判定为需要重新初始化，而不是继续放行登录。

## 启动

答辩/演示推荐入口：

```bat
start_demo_session.bat
```

通用日志启动入口：

```bat
start_classroom_app.bat
```

底层直接启动方式：

```powershell
.\.venv\Scripts\python.exe app.py
```

访问：

- [http://127.0.0.1:5000](http://127.0.0.1:5000)

说明：

- `/uploads/*` 与 `/outputs/*` 现在要求登录后访问
- 模型路径会优先读取用户上次选择；若没有，则按 `models/` 目录扫描结果自动挑选
- 用户配置中保存的模型选择会优先写成相对于 `models/` 的路径，避免把本机绝对路径带入仓库

答辩前建议按顺序执行：

```bat
verify_classroom_app.bat
start_demo_session.bat
```

若只想在正式启动前做一次只读现场确认，可执行：

```bat
start_demo_session.bat --preflight-only
```

其中 `verify_classroom_app.bat` 已包含 `startup_smoke`、回归烟测、边界审计、严格浏览器链路审计与浏览器视觉审计；`start_demo_session.bat` 是答辩当天推荐的前台服务入口，终端保持打开时系统持续运行。

若要把真实答辩入口从启动到单图、批量、视频、历史导出、摄像头诊断/启停完整复跑，可执行：

```powershell
.\.venv\Scripts\python.exe scripts\real_demo_service_audit.py
```

或直接执行：

```bat
real_demo_service_audit.bat
```

该脚本会真实写入正式 `data/`、`uploads/`、`outputs/`，并生成 `docs/_artifacts/real-demo-service-audit.json`。

若要把当前答辩说明和关键验收产物打成一个可带走的包，可执行：

```bat
build_acceptance_package.bat
```

输出：

- `docs/_artifacts/acceptance-20260518-package.zip`
- `docs/_artifacts/acceptance-20260518-package.manifest.json`

如需在交付前独立验包，可执行：

```bat
verify_acceptance_package.bat --check-live-files
```

若要单独验证本机摄像头，也可以执行：

```powershell
.\.venv\Scripts\python.exe scripts\webcam_probe.py --live-seconds 2
```

这个脚本会真实启动一次本机摄像头任务，但默认使用隔离临时目录，不会修改正式 `data/`、`uploads/`、`outputs/`。

若你确实需要把摄像头探测结果写入正式项目目录，显式执行：

```powershell
.\.venv\Scripts\python.exe scripts\webcam_probe.py --live-seconds 2 --use-real-state
```

## 健康检查

项目提供正式的只读健康检查入口，不会写入正式数据库或正式上传/输出目录：

```powershell
.\.venv\Scripts\python.exe scripts\healthcheck.py
```

一键总验收：

```powershell
.\.venv\Scripts\python.exe scripts\verify_all.py
```

或：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_all.ps1
```

答辩前快速只读预检：

```bat
demo_preflight.bat
```

真实启动烟测：

```bat
startup_smoke.bat
```

答辩当天推荐入口：

```bat
start_demo_session.bat
```

或直接运行仓库根目录脚本：

```bat
verify_classroom_app.bat
```

当前检查项：

- 全量 Python 文件编译
- `static/app/main.js` 语法检查
- `static/app/services/task-services.test.js` 前端 service 单测
- 页面结构烟测
- 交互契约烟测
- 业务回归烟测
- 高标准边界审计
- 严格系统级浏览器审计
- 真实浏览器视觉审计

说明：

- `scripts/verify_all.py` 会优先使用系统 `node`
- 若当前 shell 环境未配置 `node`，会自动回退到 bundled runtime 的 `node.exe`
- `verify_all.py` 当前会串联 `healthcheck`、`startup_smoke`、前端 service 单测、UI/交互/回归烟测、边界审计、严格系统级浏览器审计和浏览器视觉审计
- `healthcheck.py` 与 `demo_preflight.py` 都会同时检查默认模型和当前用户配置里实际将加载的模型文件
- 前端 service 单测当前覆盖 `task-results.js` 与 `browser-webcam-session.js`
- 严格系统级浏览器审计会生成 `docs/_artifacts/strict-system-audit.json` 与对应的 trace / console / network / screenshot 产物目录
- 浏览器视觉审计会生成 `docs/_artifacts/browser-audit-*.png` 与 `docs/_artifacts/browser-visual-audit.json`
- 真实答辩入口服务演练会生成 `docs/_artifacts/real-demo-service-audit.json`
- `demo_preflight.bat` 会校验 `docs/_artifacts/` 下完整验收产物是否齐全，且生成时间/文件时间不超过 24 小时；不满足则直接失败
- `demo_preflight.bat` 不会跑真实检测任务，只检查答辩现场前提项是否齐全；其中会额外校验关键 Python 依赖、并检查 `127.0.0.1:5000` 是否可用于启动
- `start_demo_session.bat` 会先跑 `demo_preflight.bat`，通过后再前台启动应用；若 `5000` 上已是当前系统实例，且当前服务已满足答辩入口契约，则直接复用；若是当前系统实例但不满足答辩入口契约，则会要求先关闭现有服务后重新启动；该入口固定使用答辩端口 `5000`，并默认从已验收的 `models/behavior.pt` 与 `models/head.pt` 启动
- `start_demo_session.bat` 会把答辩首屏固定到“单图检测”，避免继承上次保存的模式
- `start_demo_session.bat` 只负责把答辩入口拉到已验收模型作为起点，不会禁用界面的运行时模型切换或其他功能
- `startup_smoke.bat` 会在临时数据目录和隔离端口上拉起真实应用进程，确认首页与会话接口可用后自动回收
- `start_classroom_app.bat` 是通用日志启动入口，会把输出写到 `outputs/classroom_app.out.log` 与 `outputs/classroom_app.err.log`，并支持通过 `APP_HOST` / `APP_PORT` 覆盖绑定地址

若只需快速回归前端 service：

```powershell
.\.venv\Scripts\python.exe scripts\frontend_service_tests.py
```

或：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\frontend_service_tests.ps1
```

页面结构烟测：

```powershell
.\.venv\Scripts\python.exe scripts\ui_smoke.py
```

当前覆盖：

- 未初始化管理员时的登录页提示
- 已登录工作台主页面关键 DOM 与静态资源入口

严格系统级浏览器审计：

```powershell
.\.venv\Scripts\python.exe scripts\strict_system_audit.py
```

当前覆盖：

- 登录页未初始化提示、错误登录、成功登录
- 工作台四种模式切换、主 CTA、弹窗焦点与通知反馈
- 单图 / 批量 / 视频 / 摄像头主链路与报告打开、ZIP 导出
- 1440 / 1366 / 390 三种固定视口下的布局与浏览器 console / network 问题

交互契约烟测：

```powershell
.\.venv\Scripts\python.exe scripts\interaction_smoke.py
```

当前覆盖：

- 登录 -> 会话生效 -> 退出 -> 会话清除
- 前端模式切换文案契约
- 实时摄像头模式按钮显隐契约
- 历史批量导出按钮状态与导出动作契约

业务回归烟测：

```powershell
.\.venv\Scripts\python.exe scripts\regression_smoke.py
```

当前覆盖：

- 单图、批量、视频检测主链路
- 历史记录、任务详情、检测明细
- 单任务报告与批量报告 ZIP 导出
- 浏览器摄像头会话与实时摄像头接口生命周期

## 功能说明

### 单图 / 批量

- 支持上传图片并生成标注结果
- 批量模式支持结果列表回看与批量报告打包

### 视频

- 支持启动视频检测
- 支持轮询进度指标
- 支持中途停止
- 停止中的任务会标记为 `failed`，用于区分未完整处理的结果

### 实时摄像头

- 支持摄像头诊断、启动、停止
- 支持实时指标与历史任务记录
- 支持从实时流中抓取原始帧详情

### 历史与报告

- 支持历史筛选、排序、定位最新/高检测任务
- 支持单任务 HTML 报告
- 支持多选历史任务后批量导出 ZIP
- ZIP 内清单：
  - `readme.txt`：面向人工阅读
  - `manifest.csv`：面向表格/机器处理

## 文档与遗留资产说明

- 正式检查清单见 [docs/system-audit-checklist.md](docs/system-audit-checklist.md)
- 答辩前检查清单见 [docs/demo-readiness-checklist.md](docs/demo-readiness-checklist.md)
- 答辩运行清单见 [docs/demo-runbook.md](docs/demo-runbook.md)
- 答辩讲解提纲见 [docs/demo-speaking-outline.md](docs/demo-speaking-outline.md)
- 脚本入口说明见 [scripts/README.md](scripts/README.md)
- 遗留资产说明见 [docs/legacy-assets.md](docs/legacy-assets.md)
- 原型归档目录说明见 [legacy/prototype/README.md](legacy/prototype/README.md)

## Git 提示

如果当前 Windows 环境报 `dubious ownership`，需要把当前正式仓库目录加入 `safe.directory`：

```powershell
git config --global --add safe.directory "D:/Classroom behavior detection system"
```

这是本机 Git 安全策略问题，不是项目代码问题。

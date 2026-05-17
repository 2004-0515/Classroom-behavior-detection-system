# 答辩前检查清单

本清单面向答辩/演示前的最后确认，目标是减少现场翻车概率。

正式运行入口以当前主实现为准：

- `app.py`
- `classroom_app/`
- `templates/app_shell.html`
- `static/app/main.js`

## 0. 30 秒操作版

答辩前一天：

```bat
verify_classroom_app.bat
```

如果只想单独确认真实进程能否拉起并自动回收：

```bat
startup_smoke.bat
```

答辩开始前如只做只读现场确认：

```bat
start_demo_session.bat --preflight-only
```

如果要对真实答辩入口做一遍完整彩排：

```powershell
.\.venv\Scripts\python.exe scripts\real_demo_service_audit.py
```

或：

```bat
real_demo_service_audit.bat
```

正式演示启动：

```bat
start_demo_session.bat
```

如果 `demo_preflight.bat` 提示 `127.0.0.1:5000` 端口被占用，先关闭占用该端口的程序，再重新执行。

如果提示该端口已经是当前系统实例，且当前服务已满足答辩入口契约，则可直接复用，不必重复启动。

如果提示该端口已经是当前系统实例，但不满足答辩入口契约，先关闭现有 `5000` 服务，再重新执行 `start_demo_session.bat`。

## 1. 演示前一天

- 确认可用 Python 运行时：优先 `CLASSROOM_PYTHON`，其次 `.\.venv\Scripts\python.exe`，再次是 PATH 中的 `python`
- 确认模型文件存在于 `models/`
- 确认演示素材存在于 `testfile/`
- 确认本地管理员账号已经初始化过
- 确认本机若需 Git 操作，已处理 `safe.directory`，并指向 `D:/Classroom behavior detection system`

建议先跑一次总验收：

```powershell
.\.venv\Scripts\python.exe scripts\verify_all.py
```

若只想先做答辩前提项检查，可运行：

```bat
demo_preflight.bat
```

若只用 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify_all.ps1
```

通过标准：

- `healthcheck` 通过
- `startup_smoke` 通过
- `healthcheck` 内的前端语法、关键路由、脚本运行时检查均通过
- `frontend_service_tests` 通过
- `ui_smoke` 通过
- `interaction_smoke` 通过
- `regression_smoke` 通过
- `audit_readiness` 通过
- `browser_visual_audit` 通过
- 如已执行真实答辩入口彩排，则 `docs/_artifacts/real-demo-service-audit.json` 已生成
- 摄像头若当前机器无设备，允许结果为 `blocked:no_camera`

## 2. 演示当天启动前

- 关闭无关占资源程序
- 确认摄像头未被其他软件占用
- 确认要演示的图片、视频素材能正常打开
- 若现场要演示实时摄像头，先在系统相机应用中确认设备可用
- 确认本机浏览器可正常打开本地页面
- 若 `start_demo_session.bat --preflight-only` 或 `demo_preflight.bat` 提示完整验收产物缺失或超过 24 小时，先重新执行 `verify_classroom_app.bat`
- 若已完成真实答辩入口彩排，可打开 `docs/_artifacts/real-demo-service-audit.json` 直接核对默认模式、默认模型来源、视频流与摄像头链路结果

如本地管理员账号未初始化，先执行：

```powershell
.\.venv\Scripts\python.exe scripts\init_local_admin.py --username admin --password "请替换为你自己的密码"
```

推荐直接使用答辩入口启动应用：

```bat
start_demo_session.bat
```

如需查看更短的现场命令版，可直接看 [demo-runbook.md](./demo-runbook.md)。

- `start_demo_session.bat` 会默认从 `models/behavior.pt` 与 `models/head.pt` 启动
- 首屏应默认进入“单图检测”
- 启动后的左侧模型区应显示“启动入口默认”

若需要手动低层启动：

```powershell
.\.venv\Scripts\python.exe app.py
```

- 启动后确认浏览器可访问 `http://127.0.0.1:5000`

推荐固定演示素材：

- 单图：`testfile/0014012.jpg`
- 批量：`testfile/0009008.jpg`、`testfile/0009013.jpg`、`testfile/0009022.jpg`
- 视频：`testfile/QQ202618-01246-HD.mp4`

## 3. 启动后人工检查

登录页：

- 能进入登录页
- 若未初始化，页面能明确提示初始化命令
- 已初始化后，可正常登录

主工作台：

- 四种模式切换正常
- 左侧模型区显示“启动入口默认”
- 单图模式可见上传区和结果预览区
- 批量模式可见历史批量导出入口
- 视频模式可启动任务并看到处理中状态
- 实时摄像头模式下上传按钮隐藏、摄像头操作按钮显示

历史记录：

- 可刷新
- 可筛选
- 可定位最新任务
- 选中任务后“导出选中报告”按钮状态正确

## 4. 现场优先演示顺序

推荐顺序：

1. 登录
2. 单图检测
3. 批量检测
4. 视频检测
5. 历史记录与报告导出
6. 实时摄像头

这样即使现场摄像头设备异常，也不影响前半段主链路演示。

## 5. 常见异常处理

管理员登录被拦：

- 检查是否仍是历史弱口令配置
- 重新执行 `scripts/init_local_admin.py`

页面能开但检测失败：

- 检查 `models/` 中模型文件是否存在
- 检查上传素材格式是否在允许范围内

历史报告导出失败：

- 先确认历史任务确实已完成
- 再确认输出目录可写

摄像头不可用：

- 先关闭占用摄像头的软件
- 在系统相机应用中确认设备是否正常
- 若仍不可用，现场跳过实时摄像头，改讲单图/批量/视频主链路

## 6. 不要在现场做的事

- 不要临时改模型文件名或路径
- 不要直接删正式 `data/` 下的数据文件做“重置”
- 不要临时修改前端入口文件
- 不要把回归脚本跑出的临时目录误当成正式输出目录

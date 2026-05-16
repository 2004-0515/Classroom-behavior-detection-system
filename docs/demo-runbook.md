# 课堂行为检测系统答辩运行清单

## 1. 答辩前 5 分钟

在项目根目录执行：

```bat
verify_classroom_app.bat
```

预期结果：

- `healthcheck` / `startup_smoke` / `interaction_smoke` / `regression_smoke` / `hardening_contracts` / `browser_visual_audit` 全部 `OK`
- 最新汇总产物写入 `docs/_artifacts/verify-all-summary.json`

如需在答辩前一晚把真实答辩入口完整彩排一遍，可执行：

```powershell
.\.venv\Scripts\python scripts\real_demo_service_audit.py
```

或：

```bat
real_demo_service_audit.bat
```

预期结果：

- 生成 `docs/_artifacts/real-demo-service-audit.json`
- 覆盖 `start_demo_session.bat` 下的默认模式、默认模型来源、运行时切模、单图、批量、视频流、历史导出与摄像头链路
- 该脚本会真实写入正式 `data/`、`uploads/`、`outputs/`

## 2. 正式启动演示

在项目根目录执行：

```bat
start_demo_session.bat
```

预期结果：

- 预检通过
- 输出固定演示地址：`http://127.0.0.1:5000`
- 输出默认演示模型：`models/behavior.pt` 与 `models/head.pt`
- 首屏默认进入“单图检测”
- 左侧模型区显示“启动入口默认”
- 控制台出现 `课堂行为检测系统启动中...`
- 保持当前窗口打开，不要关闭

如果端口 `5000` 已经是满足答辩入口契约的本系统实例，脚本会提示：

```text
[INFO] Existing classroom demo app detected on port 5000, and it already matches the demo entry contract. Reusing current service.
```

这时直接打开 `http://127.0.0.1:5000` 即可。

如果 `5000` 上虽然是当前系统实例，但不是以答辩入口契约运行，例如默认模式不是“单图检测”或默认模型不是 `behavior.pt + head.pt`，脚本会拒绝复用，并提示先关闭现有服务后重启。

如果老师追问“你现在跑的是哪套模型”，直接点击左侧“当前模型”：

- 会显示学生模型和教师模型的完整路径
- 可以直接指明当前演示默认从 `models/behavior.pt` 与 `models/head.pt` 启动
- 弹窗会显示“来源：启动入口默认”

## 3. 推荐演示素材

- 单图：`testfile/0014012.jpg`
- 批量：`testfile/0009008.jpg`、`testfile/0009013.jpg`、`testfile/0009022.jpg`
- 视频：`testfile/QQ202618-01246-HD.mp4`

## 4. 现场展示顺序

建议顺序：

1. 登录系统
2. 单图检测
3. 批量检测
4. 视频检测
5. 查看报告导出
6. 视现场条件决定是否展示摄像头

## 5. 现场兜底

- 如果摄像头不可用：直接跳过“实时摄像头”，前面四项已经有完整验收与截图产物支撑
- 如果需要只做启动前确认，不立刻起服务：

```bat
start_demo_session.bat --preflight-only
```

- 如果要核对最近一次验收时间：
  - `docs/_artifacts/verify-all-summary.json`
  - `docs/_artifacts/browser-visual-audit.json`
  - `docs/_artifacts/hardening-contracts.json`
  - `docs/_artifacts/real-demo-service-audit.json`

## 6. 结束后

关闭运行 `start_demo_session.bat` 的窗口即可停止服务。

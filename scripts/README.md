# Scripts

本目录存放项目初始化、健康检查、前端回归与页面/交互/回归烟测脚本。

推荐使用顺序：

1. `verify_all.py` / `verify_all.ps1`
   - 一键总验收入口
   - 串联 `healthcheck`、`startup_smoke`、前端 service 单测、共享报告契约单测、UI 烟测、交互烟测、回归烟测、高标准边界审计、严格系统级浏览器审计、浏览器视觉审计
   - 若想从仓库根目录直接运行，可使用 `verify_classroom_app.bat`

2. `demo_preflight.py`
   - 答辩前快速只读预检
   - 检查 Python 运行时、关键 Python 依赖、管理员配置、默认模型与当前实际模型、固定演示素材、浏览器、根目录入口、完整验收产物与 `127.0.0.1:5000` 端口
   - 要求 `docs/_artifacts/` 下完整验收产物存在且不超过 24 小时；不满足则直接失败
   - 若想从仓库根目录直接运行，可使用 `demo_preflight.bat`

3. `startup_smoke.py`
   - 真实启动烟测
   - 使用临时数据目录与隔离端口拉起 `app.py`
   - 检查首页、会话接口、临时管理员配置生成后自动回收进程
   - 若想从仓库根目录直接运行，可使用 `startup_smoke.bat`

根目录答辩入口：

- `start_demo_session.bat`
  - 先执行 `demo_preflight.bat`
  - 通过后在当前窗口前台启动 `app.py`
  - 若 `127.0.0.1:5000` 已是当前系统实例，且当前服务已满足答辩入口契约，则直接复用
  - 若 `127.0.0.1:5000` 已是当前系统实例，但当前服务不满足答辩入口契约，则会要求先关闭现有服务再重新启动
  - 固定使用答辩端口 `5000`，不会继承外部 `APP_PORT`
  - 默认从已验收的 `models/behavior.pt` 与 `models/head.pt` 启动
  - 首屏固定进入“单图检测”，不继承上次保存的模式
  - 运行后仍保留模型切换和其他界面功能
  - 会打印固定演示素材与访问地址
  - 如只想做现场前提项确认而不真正起服务，可执行 `start_demo_session.bat --preflight-only`

- `start_classroom_app.bat`
  - 通用日志启动入口
  - 自动创建 `outputs/` 并把 stdout/stderr 写入日志
  - 支持通过 `APP_HOST` / `APP_PORT` 覆盖绑定地址

4. `healthcheck.py`
   - 只读健康检查
   - 覆盖 Python 编译、前端语法、目录结构、默认模型与当前实际模型、关键路由、脚本运行时 helper

5. `frontend_service_tests.py` / `frontend_service_tests.ps1`
   - 快速回归前端 JS 单测入口，会递归执行 `static/app/**/*.test.js`
   - 当前覆盖 `static/app/services/task-results.js`
   - 当前覆盖 `static/app/services/task-runtime.js`
   - 当前覆盖 `static/app/services/browser-webcam-session.js`
   - 当前覆盖 `static/app/components/task-summary.js`
   - 当前覆盖 `static/app/components/history.js`
   - 当前覆盖 `static/app/lib/dialogs.js`
   - 当前覆盖 `static/app/lib/summary.js`
   - 当前覆盖 `static/app/lib/history.js`
   - 当前覆盖 `static/app/lib/task-payload.js`

6. `ui_smoke.py`
   - 页面结构与关键 DOM 烟测
   - 只覆盖结构存在性，不代表真实浏览器 UX 已通过

7. `interaction_smoke.py`
   - 登录、模式切换、按钮显隐、导出动作等交互契约烟测
   - 只覆盖交互契约，不替代真实浏览器行为审计

8. `regression_smoke.py`
   - 业务主链路回归烟测
   - 覆盖单图、批量、视频、历史、报告、浏览器摄像头会话等主路径
   - 对 video / browser webcam / live webcam 额外校验 tracking summary 与 detection 明细的一致性，包括 `unique_targets`、`peak_concurrency` 和 source breakdown
   - 当前额外校验单图报告 HTML、批量任务报告 HTML、视频报告 HTML，以及批量导出 ZIP 内对应报告 HTML 与各自任务 summary 的关键 metric cards 一致

9. `hardening_contracts.py`
   - 报告复用、批量导出、浏览器摄像头异常路径与服务层并发安全契约
   - 当前额外校验 tracking 报告在 `display_metrics / derived_metrics` 漂移时必须重新生成，且 HTML 要渲染刷新后的指标值
   - 当前额外校验批量导出 ZIP 中的每份报告 HTML 与各自任务 summary 的关键 metric cards 一致

10. `audit_readiness.py`
   - 高标准边界审计
   - 使用临时数据目录覆盖未初始化登录、管理员弱输入、错误上传、任务缺失、报告批量参数、浏览器摄像头停止参数和样本识别效果
   - 当前额外校验样本图片报告 HTML 与该任务 summary 的关键 metric cards 一致，不再只看报告接口返回 200
   - 运行结束会校验真实 `data`、`uploads`、`outputs` 状态未变化

11. `strict_system_audit.py`
   - 启动两套隔离审计服务，并调用 `static/app/scripts/strict-system-audit.cjs` 做 Playwright 级严格浏览器审计
   - 默认覆盖 1440 / 1366 / 390 三种视口下的登录、工作台、报告、批量导出、视频停止、浏览器摄像头 fallback，以及桌面视口下的视频完成与服务端摄像头启停
   - 对 tracking 型 video / webcam 结果页额外校验 summary API、当前 summary 卡片和历史主指标三者口径一致
   - 对单图 / 批量 / 视频报告页额外校验 HTML metric cards 与 summary API 的 `display_metrics.cards` 前 4 项一致
   - 当前额外校验候选模型库中不应出现“未命名”入口，视频结果预览必须拿到有效时长且无播放错误
   - 当前额外校验历史跨模式批量导出 ZIP：浏览器实际打开的 `zip_url`、`report_count`、ZIP 内报告文件、manifest/readme，以及每份报告 HTML 与各自 summary 的关键 metric cards 一致
   - 视频严格审计默认使用两份样本：`video-stop` 保持长视频以覆盖处理中断，`video-complete` 使用短视频以保证 tracing 和完成态校验稳定
   - 会收集 machine-readable issue 列表、截图、console/network 日志，以及出现问题时的 trace
   - 汇总产物写入 `docs/_artifacts/strict-system-audit.json`

12. `browser_visual_audit.ps1`
   - 启动隔离审计服务并用本机 Edge/Chrome headless 截图
   - 当前会校验单图 / 批量 / 视频报告 HTML 至少包含 summary API 的关键 metric card 标签和值，并复用 `verify_report_archive.py` 作为共享 HTML 契约校验器
   - 当前会校验单图 / 批量 / 视频报告 HTML 与各自 summary API 的关键 metric card 标签和值一致
   - 当前会校验批量 ZIP 内的单图 / 批量 / 视频报告 HTML 与各自 summary API 的关键 metric card 标签和值一致，并复用 `verify_report_archive.py` 作为共享 ZIP 契约校验器
   - 产物写入 `docs/_artifacts/browser-audit-*.png`（含视频报告截图）和 `docs/_artifacts/browser-visual-audit.json`
   - 当前额外写出单报告 HTML 与批量导出校验用的 HTML / summary / expectations / validation 产物，便于回溯逐份报告验证结果
   - 当前已纳入默认总验收；若当前机器缺少 Edge/Chrome，会在该项失败并给出原因

13. `verify_report_archive.py`
   - 报告 ZIP / HTML 契约校验工具
   - 可直接校验单份报告 HTML 是否包含期望 marker 与关键 metric cards，也可校验导出的 ZIP 是否包含 `readme.txt`、`manifest.csv`、期望报告 HTML，以及每份 HTML 的关键 metric cards
   - 当前也作为 `browser_visual_audit.ps1`、`audit_readiness.py`、`regression_smoke.py`、`hardening_contracts.py`、`real_demo_service_audit.py` 的共享校验来源，避免多份脚本各自维护不同口径

14. `real_demo_service_audit.py`
    - 真实答辩入口服务演练
    - 会启动或复用 `start_demo_session.bat` 对应的 `127.0.0.1:5000` 服务
    - 覆盖答辩入口默认模式、默认模型来源、运行时模型切换、单图、批量、视频流、历史导出、服务端摄像头诊断与启停
    - 当前会校验单图 / 视频报告 HTML 与 summary API 的关键 metric card 值一致
    - 当前会校验批量导出 ZIP 内的单图 / 批量 / 视频报告 HTML 与各自任务 summary 的关键 metric card 值一致
    - 若服务端摄像头在诊断后瞬时不可用，会记录 `start_error` 与二次诊断结果，而不是让整份彩排直接失败
    - 产物写入 `docs/_artifacts/real-demo-service-audit.json`
     - 该脚本会真实写入正式 `data/`、`uploads/`、`outputs/`，用于答辩前整链路彩排，不属于隔离烟测
     - 若想从仓库根目录直接运行，可使用 `real_demo_service_audit.bat`

15. `build_acceptance_package.py`
     - 汇总 `docs/` 下的答辩说明和 `docs/_artifacts/` 下的关键验收产物
     - 输出 `docs/_artifacts/acceptance-20260518-r2-package.zip` 与对应 `manifest.json`
     - 会自动纳入严格浏览器审计 run dir、浏览器截图、真实答辩入口彩排摘要和批量 ZIP 等证据

16. `verify_acceptance_package.py`
     - 校验 `acceptance-20260518-r2-package.zip` 与 sidecar manifest 是否一致
     - 默认逐项验证 zip 内文件路径、大小和 `sha256`
     - `--check-live-files` 可额外校验当前工作区中的源文件仍与 manifest 一致
     - 若想从仓库根目录直接运行，可使用 `verify_acceptance_package.bat`

17. `webcam_probe.py`
     - 单独检查本机摄像头是否能被项目打开
     - 默认使用隔离临时目录，不修改正式 `data/`、`uploads/`、`outputs`
     - 默认只诊断，不启动任务：`.\.venv\Scripts\python.exe scripts\webcam_probe.py`
    - 如需真实启动并停止一次：`.\.venv\Scripts\python.exe scripts\webcam_probe.py --live-seconds 2`
    - 如需保留隔离产物便于检查：`.\.venv\Scripts\python.exe scripts\webcam_probe.py --live-seconds 2 --keep-temp`
    - 只有在明确需要写入正式项目状态时，才使用 `--use-real-state`

辅助脚本：

- `init_local_admin.py`
  - 初始化本地管理员账号

- `runtime_paths.py`
  - 统一解析 `python` / `node` 运行时
  - `python` 优先顺序：`CLASSROOM_PYTHON` -> 当前解释器 -> `ROOT/.venv/Scripts/python.exe` -> PATH 中的 `python`
  - `node` 优先使用系统 PATH；若 PATH 中的 `node` 缺失或 `--version` 无法正常执行，则回退到 bundled runtime
  - `resolve_playwright_node_paths()` 会优先使用 `static/app/node_modules`，找不到时回退到 bundled runtime 内的 `playwright` / `playwright-core` pnpm 目录

- `runtime_paths_test.py`
  - 校验 `runtime_paths.resolve_python()` / `resolve_node()` / `resolve_playwright_node_paths()` 的优先级与 fallback 行为

- `verify_report_archive_test.py`
  - 校验共享报告 HTML / ZIP 契约工具的单报告 marker、nested expectations 映射和批量 ZIP 校验行为
  - 已纳入 `verify_all.py` 默认链路，用于尽早拦截共享契约回归

- `tracking_runtime_test.py`
  - 校验 `utils.detector.TrackingRuntime` 在 tracker 漏发 `track_id` 时的补号、过期和 source 隔离行为

- `tracking_fallback_test.py`
  - 直接校验共享 fallback helper 和 `backfill_tracking_metrics.assign_track_ids()` 的分配语义，避免实时链路与历史回填漂移

- `summary_metrics_test.py`
  - 校验 tracking 型 summary 的 `unique_targets`、`peak_concurrency`、source breakdown 和图表统计不会被跨帧复用或同帧重复 `track_id` 误放大

- `backfill_tracking_metrics.py`
  - 为历史 `video` / `webcam` 任务回填 `track_id` 及 tracking 型 `display_metrics` / `derived_metrics`

- `model_checksum_manifest.py`
  - 维护 `models/checksums.json`
  - 默认校验当前 `models/**/*.pt` 与清单是否一致，`--rewrite` 用于明确换模后的重写确认

- `model_integrity_test.py`
  - 校验模型完整性清单的 round-trip、未登记模型、篡改模型和坏清单场景

- `demo_runtime_contract.py`
  - 供 `demo_preflight.py` 与 `real_demo_service_audit.py` 复用的本地答辩入口契约探测辅助模块
  - 会本地签发管理员 session cookie，并读取运行中服务的默认模式与模型来源

- `audit_server.py`
  - 供 `browser_visual_audit.ps1` 与 `strict_system_audit.py` 复用的隔离审计服务
  - 支持带管理员 / 无管理员两种启动形态
  - 通过环境变量把上传、输出、数据库、管理员配置和 YOLO 配置全部指向临时目录

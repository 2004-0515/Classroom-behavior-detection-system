# 2026-05-19 主线收口摘要

## 基线

- 当前人工封版 tag 仍为 `acceptance-20260518-r2`
- `main` 已在该封版之后额外合入两条主线硬化提交：`4330c5c`、`8dc6ccc`
- 当前主线 merge commit 为 `ad9c2e0`

## 本轮收口内容

- `classroom_app/routes/tasks.py` 与 `classroom_app/routes/models.py` 的失败分支改为稳定返回 JSON 错误载荷，避免前端在任务创建失败或模型路由失败时退化成不可解析的 HTML 错误页。
- `static/app/scripts/strict-system-audit.cjs` 新增一次性重试逻辑：当 GitHub Windows runner 在同源 `/static/` 资源加载阶段出现瞬时传输失败时，审计脚本会先清理该类瞬时诊断并 reload 一次页面，再决定是否把 `webcam-browser-failure` 计为 hard issue。
- 上述变更不会放宽真实产品错误的判定标准；重试只覆盖瞬时、同源、静态资源加载失败这一类 runner 噪声。

## 验证结果

- 本地 `.\.venv\Scripts\python.exe scripts\strict_system_audit.py` 已通过。
- 本地 `.\.venv\Scripts\python.exe scripts\verify_all.py` 已通过。
- PR #4 已于 `2026-05-19T08:07:49Z` 合入。
- 合入后的 `main` 对应 GitHub Actions `Windows Acceptance` run `26084645310` 已完成，结论为 `success`。
- `acceptance-20260519-package.zip` 与 sidecar manifest 已生成，并通过 `--check-live-files` 验包。

## 建议复核命令

```powershell
.\.venv\Scripts\python.exe scripts\build_acceptance_package.py --label acceptance-20260519 --acceptance-tag acceptance-20260518-r2 --baseline-commit ad9c2e0
```

```powershell
.\.venv\Scripts\python.exe scripts\verify_acceptance_package.py --label acceptance-20260519 --check-live-files
```

## 关键证据

- [acceptance-20260519-package.zip](./_artifacts/acceptance-20260519-package.zip)
- [acceptance-20260519-package.manifest.json](./_artifacts/acceptance-20260519-package.manifest.json)
- [strict-system-audit.json](./_artifacts/strict-system-audit.json)
- [verify-all-summary.json](./_artifacts/verify-all-summary.json)
- [high-standard-audit-report.md](./high-standard-audit-report.md)

## 对外表述

可直接引用：

> 当前人工封版仍是 `acceptance-20260518-r2`，但 `main` 已额外合入任务/模型路由错误 JSON 化和严格浏览器审计瞬时静态资源失败重试两项硬化；对应主线提交 `ad9c2e0` 的 `Windows Acceptance` 已通过。

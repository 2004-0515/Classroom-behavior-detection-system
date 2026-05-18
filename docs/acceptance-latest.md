# 最新验收状态

更新时间：2026-05-18

## 当前仓库级验收入口

- GitHub Actions workflow：`Windows Acceptance`
- 当前 CI 基线：`windows-2025-vs2026`、Python `3.11`、Node `24`
- 当前状态读取方式：查看仓库 Actions 页中 `Windows Acceptance` 在 `main` 分支上的最新记录
- 说明：此文档不再固定 run id；任何新的 push 都会生成新的验收记录，硬编码 run id 会让文档立即过期

## 本轮收口内容

- 将 `windows-acceptance.yml` 的 Node 运行时提升到 `24`
- 在 `static/app/package.json` / `package-lock.json` 写入前端 `engines.node >=18`
- 补齐 README 中的 Python / Node 当前验收基线说明
- 修复 `strict-system-audit.cjs`：无稳定摄像头环境下，`/api/streams/webcam/feed`、`/api/streams/webcam/diagnostics` 与视频流 feed 的瞬时失败不再被误判为 hard issue

## 相关说明

- 当前人工封版 tag 使用 `acceptance-20260518-r2`
- 当前交付摘要见 [acceptance-handoff-20260518-r2.md](./acceptance-handoff-20260518-r2.md)
- 历史交付摘要保留在 [acceptance-handoff-20260518.md](./acceptance-handoff-20260518.md)
- 通用审计结论与复核命令见 [high-standard-audit-report.md](./high-standard-audit-report.md)

## 对外最短表述

> 仓库级总验收入口是 GitHub Actions 的 `Windows Acceptance`。当前 CI 基线固定在 Python `3.11` 和 Node `24`，默认总验收已包含严格浏览器审计、摄像头硬化契约和真实浏览器截图审计；如需精确到某一次运行，以 `main` 分支上的最新 workflow 记录为准。

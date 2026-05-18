# 最新验收状态

更新时间：2026-05-18

## 当前仓库级通过记录

- GitHub Actions workflow：`Windows Acceptance`
- 最新通过 run：`26011829474`
- 对应提交：`5642715` `Ignore transient stream probe failures in strict audit`
- 结果：`success`
- 当前 CI 基线：`windows-2025-vs2026`、Python `3.11`、Node `24`

## 本轮收口内容

- 将 `windows-acceptance.yml` 的 Node 运行时提升到 `24`
- 在 `static/app/package.json` / `package-lock.json` 写入前端 `engines.node >=18`
- 补齐 README 中的 Python / Node 当前验收基线说明
- 修复 `strict-system-audit.cjs`：无稳定摄像头环境下，`/api/streams/webcam/feed`、`/api/streams/webcam/diagnostics` 与视频流 feed 的瞬时失败不再被误判为 hard issue

## 相关说明

- 最近一个人工封版 tag 仍为 `acceptance-20260518`，对应提交 `7e2fdb3`
- 历史交付摘要保留在 [acceptance-handoff-20260518.md](./acceptance-handoff-20260518.md)
- 通用审计结论与复核命令见 [high-standard-audit-report.md](./high-standard-audit-report.md)

## 对外最短表述

> 最近一次仓库级 `Windows Acceptance` 通过记录是 2026-05-18 的 run `26011829474`，对应提交 `5642715`。当前 CI 基线固定在 Python `3.11` 和 Node `24`，默认总验收已包含严格浏览器审计、摄像头硬化契约和真实浏览器截图审计。

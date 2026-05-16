# 遗留资产说明

以下文件仍保留在仓库中，但**已经迁移到原型归档目录，不是当前正式运行入口**：

- `legacy/prototype/index.html`
- `legacy/prototype/main.js`
- `legacy/prototype/style.css`

它们来自旧版原型或早期界面实验，和当前 Flask shell 工作台并不一致。当前正式入口为：

- `templates/app_shell.html`
- `static/app/main.js`
- `static/css/app.css`

处理原则：

- 不再把遗留文件作为 README、验收或答辩说明依据
- 若后续确认完全不再需要，可在单独清理提交中删除整个 `legacy/prototype/`
- 若仅做对照保留，必须继续维持“遗留/非现役”标识，避免误导维护者

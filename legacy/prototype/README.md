该目录仅保存迁移前的原型前端资产，供历史对照，不参与当前正式运行。

当前正式入口：

- `app.py`
- `classroom_app/`
- `templates/app_shell.html`
- `static/app/main.js`
- `static/css/app.css`

归档文件：

- `index.html`
- `main.js`
- `style.css`

处理原则：

- 不在 README、验收脚本、答辩说明中把这些文件当成正式入口
- 不为这些文件补业务修复，除非明确要回溯旧原型
- 正式功能问题只在当前正式实现中修复

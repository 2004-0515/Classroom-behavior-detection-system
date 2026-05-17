from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Dict, List
import json


class ReportGenerator:
    """检测报告生成器"""
    TEMPLATE_VERSION = "2026-05-16-zero-failure-v1"

    @staticmethod
    def generate_html_report(task_info: Dict[str, Any], output_path: str):
        """生成HTML格式的详细报告"""
        student_stats = ReportGenerator._coerce_stats(task_info.get("student_behavior_stats", {}))
        teacher_stats = ReportGenerator._coerce_stats(task_info.get("teacher_behavior_stats", {}))
        combined_behaviors = ReportGenerator._get_top_behaviors(student_stats, teacher_stats, 4)
        student_total = sum(student_stats.values())
        teacher_total = sum(teacher_stats.values())
        total = int(task_info.get("total_detections", 0) or 0)
        avg_conf = float(task_info.get("average_confidence", 0) or 0) * 100
        duration = float(task_info.get("duration", 0) or 0)
        mode = task_info.get("task_type", "unknown")
        preview_html = ReportGenerator._build_preview(task_info)
        narrative = ReportGenerator._build_narrative(mode, total, avg_conf, duration, combined_behaviors)
        speeches = ReportGenerator._build_speeches(mode, total, avg_conf, duration, combined_behaviors)

        html_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>课堂行为检测报告</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        :root {{
            --bg: #eef4fb;
            --panel: rgba(255, 255, 255, 0.96);
            --line: rgba(171, 193, 218, 0.34);
            --text: #2d3748;
            --soft: #5f6f86;
            --muted: #8a96aa;
            --primary: #29415c;
            --primary-soft: #4f759b;
            --success: #5b977f;
            --tone1-bg: rgba(233, 241, 251, 0.96);
            --tone1-bd: rgba(121, 151, 186, 0.35);
            --tone1-fg: #29415c;
            --tone2-bg: rgba(238, 245, 252, 0.96);
            --tone2-bd: rgba(146, 171, 201, 0.35);
            --tone2-fg: #4f759b;
            --tone3-bg: rgba(243, 248, 254, 0.96);
            --tone3-bd: rgba(167, 190, 216, 0.35);
            --tone3-fg: #6d8eb3;
            --tone4-bg: rgba(247, 250, 255, 0.96);
            --tone4-bd: rgba(186, 204, 225, 0.35);
            --tone4-fg: #87a4c6;
        }}
        body {{
            font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
            background: linear-gradient(180deg, #f4f8fd 0%, #ebf2fa 100%);
            color: var(--text);
            line-height: 1.7;
            padding: 24px;
            overflow-wrap: anywhere;
            word-break: break-word;
        }}
        h1, h2, h3, p, span, strong, small, li, td, th, a {{
            overflow-wrap: anywhere;
            word-break: break-word;
        }}
        .page {{
            max-width: 1280px;
            margin: 0 auto;
            display: grid;
            gap: 22px;
        }}
        .report-toolbar {{
            position: sticky;
            top: 0;
            z-index: 20;
            display: flex;
            justify-content: flex-end;
            gap: 10px;
            padding-bottom: 2px;
        }}
        .report-action {{
            appearance: none;
            border: 1px solid var(--line);
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.96);
            color: var(--primary);
            padding: 10px 16px;
            font: inherit;
            font-size: 14px;
            cursor: pointer;
            box-shadow: 0 10px 24px rgba(163, 181, 204, 0.12);
        }}
        .report-action.primary {{
            background: linear-gradient(180deg, rgba(255,255,255,0.99) 0%, rgba(241,247,255,0.95) 100%);
            border-color: rgba(152, 181, 215, 0.34);
        }}
        .panel {{
            background: var(--panel);
            border: 1px solid var(--line);
            border-radius: 12px;
            padding: 22px;
            box-shadow: 0 18px 40px rgba(163, 181, 204, 0.12);
        }}
        .hero {{
            display: grid;
            grid-template-columns: minmax(0, 1.1fr) minmax(320px, 0.9fr);
            gap: 18px;
            align-items: stretch;
        }}
        .eyebrow {{
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0;
            font-size: 12px;
            margin-bottom: 10px;
        }}
        h1, h2, h3 {{
            letter-spacing: 0;
        }}
        h1 {{
            font-size: 40px;
            line-height: 1.16;
            margin-bottom: 12px;
            padding-bottom: 4px;
            color: var(--primary);
        }}
        .hero-copy p,
        .meta-list,
        .speech-card p,
        .narrative-card small,
        .recommend-list li {{
            color: var(--soft);
        }}
        .meta-list {{
            display: grid;
            gap: 6px;
            margin-top: 14px;
            font-size: 14px;
        }}
        .preview-box {{
            min-height: 280px;
            border-radius: 12px;
            border: 1px solid var(--line);
            background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(244,249,255,0.95) 100%);
            display: grid;
            place-items: center;
            overflow: hidden;
        }}
        .preview-box img,
        .preview-box video {{
            width: 100%;
            height: 100%;
            object-fit: contain;
            display: block;
            background: #f8fbff;
        }}
        .preview-summary {{
            width: 100%;
            height: 100%;
            padding: 24px;
            display: grid;
            gap: 16px;
            align-content: center;
        }}
        .preview-summary strong {{
            font-size: 28px;
            line-height: 1.18;
            padding-bottom: 4px;
            color: var(--primary);
        }}
        .preview-summary p {{
            color: var(--soft);
        }}
        .preview-actions {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .preview-link {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 132px;
            padding: 10px 14px;
            border-radius: 999px;
            border: 1px solid var(--line);
            color: var(--primary);
            background: rgba(255, 255, 255, 0.98);
            text-decoration: none;
            font-size: 14px;
        }}
        .preview-empty {{
            padding: 24px;
            text-align: center;
            color: var(--muted);
        }}
        .grid-4,
        .speech-grid,
        .behavior-grid,
        .analysis-grid {{
            display: grid;
            gap: 16px;
        }}
        .grid-4 {{
            grid-template-columns: repeat(4, minmax(0, 1fr));
        }}
        .speech-grid,
        .analysis-grid {{
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
        .behavior-grid {{
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
        .metric-card,
        .speech-card,
        .narrative-card,
        .behavior-card {{
            border: 1px solid var(--line);
            border-radius: 10px;
            padding: 16px 18px;
            background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(244,249,255,0.95) 100%);
        }}
        .metric-card.accent,
        .narrative-card.accent {{
            border-color: rgba(152, 181, 215, 0.34);
            background: linear-gradient(180deg, rgba(255,255,255,0.99) 0%, rgba(241,247,255,0.95) 100%);
        }}
        .metric-card span,
        .speech-card span,
        .narrative-card span,
        .behavior-card span {{
            display: block;
            color: var(--muted);
            font-size: 12px;
            margin-bottom: 8px;
        }}
        .metric-card strong,
        .narrative-card strong {{
            display: block;
            font-size: 34px;
            line-height: 1.14;
            padding-bottom: 4px;
            color: var(--primary);
        }}
        .tag-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 12px;
        }}
        .tag {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 7px 12px;
            border-radius: 999px;
            font-size: 13px;
            border: 1px solid var(--tone1-bd);
            background: var(--tone1-bg);
            color: var(--tone1-fg);
        }}
        .tag.tone-2 {{ background: var(--tone2-bg); border-color: var(--tone2-bd); color: var(--tone2-fg); }}
        .tag.tone-3 {{ background: var(--tone3-bg); border-color: var(--tone3-bd); color: var(--tone3-fg); }}
        .tag.tone-4 {{ background: var(--tone4-bg); border-color: var(--tone4-bd); color: var(--tone4-fg); }}
        .pill {{
            display: inline-flex;
            padding: 6px 10px;
            border-radius: 999px;
            border: 1px solid rgba(170, 190, 214, 0.34);
            background: rgba(243, 247, 252, 0.96);
            color: var(--primary-soft);
            font-size: 12px;
        }}
        .section-title {{
            margin-bottom: 14px;
        }}
        .section-title h2 {{
            font-size: 26px;
            color: var(--primary);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
        }}
        th, td {{
            text-align: left;
            padding: 12px 10px;
            border-bottom: 1px solid rgba(226, 233, 243, 0.9);
            font-size: 14px;
        }}
        th {{
            color: var(--primary);
            background: rgba(244, 248, 255, 0.96);
        }}
        .progress-bar {{
            width: 100%;
            height: 10px;
            background: rgba(230, 236, 244, 0.9);
            border-radius: 999px;
            overflow: hidden;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #4f759b 0%, #87a4c6 100%);
            border-radius: 999px;
        }}
        .recommend-list {{
            padding-left: 18px;
        }}
        .footer {{
            text-align: center;
            color: var(--muted);
            font-size: 13px;
            padding: 10px 0 20px;
        }}
        @media (max-width: 980px) {{
            .hero,
            .grid-4,
            .speech-grid,
            .behavior-grid,
            .analysis-grid {{
                grid-template-columns: 1fr;
            }}
            .report-toolbar {{
                position: static;
                justify-content: stretch;
                display: grid;
                grid-template-columns: 1fr 1fr;
            }}
            .report-action {{
                width: 100%;
            }}
            h1 {{
                font-size: 32px;
                line-height: 1.18;
            }}
            .metric-card strong,
            .narrative-card strong {{
                font-size: 30px;
            }}
        }}
        @media print {{
            @page {{
                size: A4 portrait;
                margin: 12mm;
            }}
            body {{
                background: white;
                padding: 0;
            }}
            .report-toolbar {{
                display: none;
            }}
            .preview-link {{
                color: var(--primary);
                text-decoration: none;
            }}
            .panel {{
                box-shadow: none;
                break-inside: avoid;
            }}
        }}
    </style>
</head>
<body>
    <div class="page">
        <div class="report-toolbar">
            <button class="report-action" type="button" onclick="backToConsole()">返回系统</button>
            <button class="report-action primary" type="button" onclick="printReport()">打印 / 导出 PDF</button>
        </div>
        <section class="panel hero">
            <div class="hero-copy">
                <div class="eyebrow">Classroom Vision Report</div>
                <h1>课堂行为检测报告</h1>
                <p>{mode_intro}</p>
                <div class="tag-row">
                    <span class="pill">{status_text}</span>
                    <span class="pill">文件：{file_name}</span>
                    <span class="pill">任务：{task_type}</span>
                </div>
                <div class="meta-list">
                    <div>生成时间：{generation_time}</div>
                    <div>任务 ID：{task_id}</div>
                    <div>处理帧数：{processed_frames}</div>
                </div>
            </div>
            <div class="preview-box">{preview_html}</div>
        </section>

        <section class="grid-4">
            <article class="metric-card accent"><span>总检测数</span><strong>{total_detections}</strong></article>
            <article class="metric-card"><span>平均置信度</span><strong>{avg_confidence}%</strong></article>
            <article class="metric-card"><span>处理时长</span><strong>{duration} 秒</strong></article>
            <article class="metric-card"><span>任务类型</span><strong>{task_type}</strong></article>
        </section>

        <section class="analysis-grid">
            <article class="narrative-card accent">
                <span>结论摘要</span>
                <strong>{narrative_title}</strong>
                <small>{narrative_text}</small>
                <div class="tag-row">{top_behavior_tags}</div>
            </article>
            <article class="narrative-card">
                <span>展示建议</span>
                <strong>{recommend_title}</strong>
                <small>{recommend_text}</small>
            </article>
        </section>

        <section class="speech-grid">
            <article class="speech-card">
                <span>30 秒版</span>
                <p>{speech_short}</p>
            </article>
            <article class="speech-card">
                <span>90 秒版</span>
                <p>{speech_long}</p>
            </article>
        </section>

        <section class="behavior-grid">
            <article class="panel">
                <div class="section-title">
                    <div class="eyebrow">Student Behaviors</div>
                    <h2>学生行为分析</h2>
                </div>
                <div class="tag-row">{student_tags}</div>
                {student_behavior_content}
            </article>
            <article class="panel">
                <div class="section-title">
                    <div class="eyebrow">Teacher Or Heads</div>
                    <h2>教师/人头行为分析</h2>
                </div>
                <div class="tag-row">{teacher_tags}</div>
                {teacher_behavior_content}
            </article>
        </section>

        <section class="panel">
            <div class="section-title">
                <div class="eyebrow">Suggestions</div>
                <h2>建议与分析</h2>
            </div>
            {recommendations}
        </section>

        <div class="footer">
            <p>课堂行为检测系统 | Powered by YOLOv8</p>
        </div>
    </div>
    <script>
        function printReport() {{
            window.print();
        }}
        function backToConsole() {{
            if (window.opener && !window.opener.closed) {{
                window.close();
                return;
            }}
            if (window.history.length > 1) {{
                window.history.back();
            }}
        }}
    </script>
</body>
</html>
"""

        html_content = html_template.format(
            generation_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            task_id=escape(str(task_info.get("task_id", "N/A"))),
            task_type=escape(ReportGenerator._get_task_type_name(mode)),
            file_name=escape(str(task_info.get("file_name", "N/A"))),
            processed_frames=escape(str(task_info.get("processed_frames", 0))),
            total_detections=total,
            avg_confidence=f"{avg_conf:.1f}",
            duration=f"{duration:.1f}",
            mode_intro=escape(narrative["mode_intro"]),
            status_text=escape(ReportGenerator._get_status_text(task_info.get("status", "completed"))),
            preview_html=preview_html,
            narrative_title=escape(narrative["title"]),
            narrative_text=escape(narrative["text"]),
            recommend_title=escape(narrative["recommend_title"]),
            recommend_text=escape(narrative["recommend_text"]),
            top_behavior_tags=ReportGenerator._render_tags(combined_behaviors),
            speech_short=escape(speeches["short"]),
            speech_long=escape(speeches["long"]),
            student_tags=ReportGenerator._render_tags(ReportGenerator._rank_single_group(student_stats, 3)),
            teacher_tags=ReportGenerator._render_tags(ReportGenerator._rank_single_group(teacher_stats, 3)),
            student_behavior_content=ReportGenerator._generate_behavior_table(student_stats, student_total),
            teacher_behavior_content=ReportGenerator._generate_behavior_table(teacher_stats, teacher_total),
            recommendations=ReportGenerator._generate_recommendations(student_stats, teacher_stats),
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        return output_path

    @staticmethod
    def _coerce_stats(raw: Any) -> Dict[str, int]:
        if isinstance(raw, str):
            raw = json.loads(raw)
        return {str(key): int(value or 0) for key, value in (raw or {}).items()}

    @staticmethod
    def _format_behavior_label(label: str) -> str:
        mapping = {
            "head": "人头",
            "heads": "人头",
            "raise_hand": "举手",
            "hand-raising": "举手",
            "hand_raise": "举手",
            "read": "阅读",
            "reading": "阅读",
            "write": "写字",
            "writing": "写字",
            "listen": "听讲",
            "listening": "听讲",
            "phone": "玩手机",
            "using_phone": "玩手机",
        }
        if label in mapping:
            return mapping[label]
        return label.replace("_", " ").replace("-", " ")

    @staticmethod
    def _get_top_behaviors(student_stats: Dict[str, int], teacher_stats: Dict[str, int], limit: int) -> List[Dict[str, Any]]:
        merged: Dict[str, int] = {}
        for key, value in list(student_stats.items()) + list(teacher_stats.items()):
            label = ReportGenerator._format_behavior_label(key)
            merged[label] = merged.get(label, 0) + int(value or 0)
        combined = [
            {"label": label, "value": value}
            for label, value in merged.items()
            if value > 0
        ]
        combined.sort(key=lambda item: item["value"], reverse=True)
        return combined[:limit]

    @staticmethod
    def _rank_single_group(stats: Dict[str, int], limit: int) -> List[Dict[str, Any]]:
        items = [
            {"label": ReportGenerator._format_behavior_label(key), "value": int(value)}
            for key, value in stats.items()
            if int(value or 0) > 0
        ]
        items.sort(key=lambda item: item["value"], reverse=True)
        return items[:limit]

    @staticmethod
    def _render_tags(items: List[Dict[str, Any]]) -> str:
        if not items:
            return '<span class="tag">暂无行为标签</span>'
        rendered = []
        for index, item in enumerate(items):
            tone = (index % 4) + 1
            rendered.append(
                f'<span class="tag tone-{tone}"><strong>{escape(str(item["label"]))}</strong><small>{item["value"]}</small></span>'
            )
        return "".join(rendered)

    @staticmethod
    def _generate_behavior_table(behavior_stats: Dict[str, int], total: int) -> str:
        if not behavior_stats or total == 0:
            return "<p class='preview-empty'>暂无检测数据</p>"
        rows = []
        for behavior, count in sorted(behavior_stats.items(), key=lambda item: item[1], reverse=True):
            percentage = (count / total) * 100 if total else 0
            rows.append(
                f"""
                <tr>
                    <td><strong>{escape(ReportGenerator._format_behavior_label(behavior))}</strong></td>
                    <td>{count}</td>
                    <td>{percentage:.1f}%</td>
                    <td>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: {percentage:.1f}%"></div>
                        </div>
                    </td>
                </tr>
                """
            )
        return (
            "<table><thead><tr><th>行为类别</th><th>检测次数</th><th>占比</th><th>分布</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )

    @staticmethod
    def _generate_recommendations(student_stats: Dict[str, int], teacher_stats: Dict[str, int]) -> str:
        recommendations: List[str] = []
        if student_stats:
            total_student = sum(student_stats.values())
            positive_behaviors = ["举手", "听讲", "看书", "写字", "阅读"]
            positive_count = sum(student_stats.get(name, 0) for name in positive_behaviors)
            positive_ratio = (positive_count / total_student * 100) if total_student else 0
            if positive_ratio > 70:
                recommendations.append("学生整体学习状态较好，适合作为课堂参与度较高的样例展示。")
            elif positive_ratio > 50:
                recommendations.append("学生学习状态较稳定，可以结合互动场景说明识别结果的代表性。")
            else:
                recommendations.append("建议结合课堂管理场景讲解识别结果，突出系统对异常状态的发现能力。")

        if teacher_stats:
            total_teacher = sum(teacher_stats.values())
            head_count = teacher_stats.get("人头", 0) + teacher_stats.get("head", 0)
            head_ratio = (head_count / total_teacher * 100) if total_teacher else 0
            if head_ratio > 60:
                recommendations.append("人头目标占比较高，适合强调系统在密集课堂画面中的稳定检测能力。")

        if not recommendations:
            recommendations.append("检测结果可以直接用于演示，建议结合原图或视频片段说明识别框与行为标签的对应关系。")

        return "<ul class='recommend-list'>" + "".join(f"<li>{escape(item)}</li>" for item in recommendations) + "</ul>"

    @staticmethod
    def _build_narrative(mode: str, total: int, avg_conf: float, duration: float, behaviors: List[Dict[str, Any]]) -> Dict[str, str]:
        top_line = "、".join(f'{item["label"]}{item["value"]}次' for item in behaviors[:3]) if behaviors else "当前行为分布还不够集中"
        if total >= 100:
            title = "检测覆盖较高"
        elif total > 0:
            title = "结果可用于展示"
        else:
            title = "等待有效结果"
        mode_intro = {
            "image": "这份报告聚焦单图检测结果，适合对照原图讲解识别框和行为标签。",
            "batch": "这份报告聚焦批量检测汇总，适合展示多张素材在统一参数下的识别一致性。",
            "video": "这份报告聚焦视频检测汇总，适合讲解连续画面中的跟踪稳定性和行为变化。",
            "webcam": "这份报告聚焦实时巡检汇总，适合讲解现场反馈速度和课堂监测节奏。",
        }.get(mode, "这份报告聚焦当前任务检测结果。")
        return {
            "title": title,
            "text": f"本次任务共识别 {total} 个目标，平均置信度 {avg_conf:.1f}%，处理时长 {duration:.1f} 秒。主要行为为 {top_line}。",
            "recommend_title": "结果适合答辩讲解" if total > 0 else "建议先生成结果",
            "recommend_text": {
                "image": "建议结合原图和结果图对照，强调单帧场景下的识别清晰度。",
                "batch": "建议切换几张代表性样本，说明模型在不同课堂图片上的输出一致性。",
                "video": "建议配合连续画面说明系统对课堂动态过程的持续跟踪能力。",
                "webcam": "建议结合实时状态区说明处理节奏、机位选择和现场反馈能力。",
            }.get(mode, "建议结合检测资源和统计结果进行讲解。"),
            "mode_intro": mode_intro,
        }

    @staticmethod
    def _build_speeches(mode: str, total: int, avg_conf: float, duration: float, behaviors: List[Dict[str, Any]]) -> Dict[str, str]:
        opener = {
            "image": "这里展示的是单图检测结果，系统会在单帧画面里定位课堂目标并输出行为标签。",
            "batch": "这里展示的是一组批量检测结果，系统会对多张课堂图片做统一识别和汇总。",
            "video": "这里展示的是视频检测结果，系统会在连续画面里持续跟踪课堂行为变化。",
            "webcam": "这里展示的是实时巡检结果，系统会边采集边输出课堂行为识别反馈。",
        }.get(mode, "这里展示的是当前检测结果。")
        value_line = "、".join(f'{item["label"]}{item["value"]}次' for item in behaviors[:3]) if behaviors else "当前行为分布还不够集中"
        mode_value = {
            "image": "它适合重点说明单帧画面里的识别框精度和行为标签对应关系。",
            "batch": "它适合重点说明多张课堂素材在同一套参数下的输出一致性。",
            "video": "它适合重点说明连续画面下的跟踪稳定性和行为变化捕捉能力。",
            "webcam": "它适合重点说明实时监测节奏、处理反馈速度和现场可视化能力。",
        }.get(mode, "它适合说明当前模式下的检测结果。")
        return {
            "short": f"{opener} 本次任务共识别 {total} 个目标，平均置信度 {avg_conf:.1f}%。其中最主要的是 {value_line}。",
            "long": f"{opener} 本次任务共识别 {total} 个目标，平均置信度 {avg_conf:.1f}%，处理时长 {duration:.1f} 秒。其中最主要的是 {value_line}。{mode_value}",
        }

    @staticmethod
    def _build_preview(task_info: Dict[str, Any]) -> str:
        assets = task_info.get("assets", {}) or {}
        if not assets:
            return '<div class="preview-empty">当前没有可嵌入的结果资源</div>'
        results = assets.get("results") or []
        asset = results[0] if results else assets
        result_path = asset.get("result")
        original = asset.get("original")
        target = result_path or original
        if not target:
            return '<div class="preview-empty">当前没有可嵌入的结果资源</div>'
        suffix = Path(str(target)).suffix.lower()
        safe = escape(str(target), quote=True)
        if suffix in {".mp4", ".webm", ".ogg"}:
            return ReportGenerator._build_video_preview_card(task_info, asset)
        return f'<img src="{safe}" alt="检测结果预览">'

    @staticmethod
    def _build_video_preview_card(task_info: Dict[str, Any], asset: Dict[str, Any]) -> str:
        links = []
        if asset.get("result"):
            links.append(f'<a class="preview-link" href="{escape(str(asset["result"]), quote=True)}" target="_blank" rel="noopener">打开结果视频</a>')
        if asset.get("original"):
            links.append(f'<a class="preview-link" href="{escape(str(asset["original"]), quote=True)}" target="_blank" rel="noopener">打开原始视频</a>')
        processed_frames = task_info.get("processed_frames", 0)
        total_detections = task_info.get("total_detections", 0)
        duration = float(task_info.get("duration", 0) or 0)
        return (
            "<div class='preview-summary'>"
            "<span class='pill'>视频报告概览</span>"
            f"<strong>{escape(ReportGenerator._get_task_type_name(task_info.get('task_type', 'video')))}</strong>"
            f"<p>文件：{escape(str(task_info.get('file_name', '未命名素材')))}</p>"
            f"<p>本次任务处理帧数 {escape(str(processed_frames))}，共识别 {escape(str(total_detections))} 个目标，处理时长 {duration:.1f} 秒。</p>"
            f"<div class='preview-actions'>{''.join(links) or '<span class=\"preview-empty\">当前没有可用视频资源链接</span>'}</div>"
            "</div>"
        )

    @staticmethod
    def _get_status_text(status: str) -> str:
        mapping = {
            "completed": "已完成",
            "processing": "处理中",
            "failed": "失败",
            "pending": "待启动",
        }
        return mapping.get(status, status)

    @staticmethod
    def _get_task_type_name(task_type: str) -> str:
        type_names = {
            "image": "单张图片检测",
            "batch": "批量图片检测",
            "video": "视频检测",
            "webcam": "实时摄像头检测",
        }
        return type_names.get(task_type, task_type)

    @staticmethod
    def generate_json_report(task_info: Dict[str, Any], output_path: str):
        """生成JSON格式报告"""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(task_info, f, ensure_ascii=False, indent=2)
        return output_path

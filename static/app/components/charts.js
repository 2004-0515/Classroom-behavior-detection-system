import { formatBehaviorStats } from "../lib/format.js";

let studentChart;
let teacherChart;

function hasChartRuntime() {
    return typeof window !== "undefined" && typeof window.Chart !== "undefined";
}

function buildDataset(stats, palette) {
    const formatted = formatBehaviorStats(stats);
    const labels = Object.keys(formatted || {});
    const values = Object.values(formatted || {});
    const hasData = values.length > 0;
    return {
        labels: hasData ? labels : ["暂无数据"],
        datasets: [
            {
                data: hasData ? values : [1],
                backgroundColor: hasData ? palette : ["rgba(214, 224, 236, 0.9)"],
                borderColor: "#ffffff",
                borderWidth: 2,
                hoverOffset: 8,
            },
        ],
    };
}

function ensureChart(chart, canvas, title, stats, palette) {
    if (!hasChartRuntime() || !canvas) {
        return null;
    }
    const dataset = buildDataset(stats, palette);
    if (!chart) {
        return new window.Chart(canvas, {
            type: "doughnut",
            data: dataset,
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "62%",
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            color: "#5b5376",
                            boxWidth: 12,
                            boxHeight: 12,
                            padding: 18,
                            font: {
                                family: '"Segoe UI", "Microsoft YaHei", sans-serif',
                                size: 12,
                            },
                        },
                    },
                    title: {
                        display: false,
                        text: title,
                    },
                },
            },
        });
    }
    chart.data = dataset;
    chart.update();
    return chart;
}

export function renderCharts(summary) {
    const studentCanvas = document.getElementById("studentChart");
    const teacherCanvas = document.getElementById("teacherChart");
    const studentFocus = document.getElementById("studentChartFocus");
    const teacherFocus = document.getElementById("teacherChartFocus");
    const studentSource = summary?.display_metrics?.behavior_charts?.student || summary?.student_behavior_stats || {};
    const teacherSource = summary?.display_metrics?.behavior_charts?.teacher || summary?.teacher_behavior_stats || {};
    const studentStats = formatBehaviorStats(studentSource);
    const teacherStats = formatBehaviorStats(teacherSource);
    if (!hasChartRuntime()) {
        if (studentCanvas) {
            studentCanvas.style.visibility = "hidden";
        }
        if (teacherCanvas) {
            teacherCanvas.style.visibility = "hidden";
        }
        renderFocus(studentFocus, studentStats);
        renderFocus(teacherFocus, teacherStats);
        return;
    }
    if (studentCanvas) {
        studentCanvas.style.visibility = "visible";
    }
    if (teacherCanvas) {
        teacherCanvas.style.visibility = "visible";
    }
    studentChart = ensureChart(studentChart, studentCanvas, "学生行为", studentSource, [
        "#29415c",
        "#4f759b",
        "#8badcf",
        "#c2d7eb",
        "#8ea7bf",
        "#d5e4f2",
    ]);
    teacherChart = ensureChart(teacherChart, teacherCanvas, "教师行为", teacherSource, [
        "#243349",
        "#5d7694",
        "#91aac7",
        "#d5e1ee",
        "#a7bbd2",
        "#e2ebf5",
    ]);
    renderFocus(studentFocus, studentStats);
    renderFocus(teacherFocus, teacherStats);
}

function renderFocus(node, stats) {
    if (!node) {
        return;
    }
    const entries = Object.entries(stats || {}).sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0)).slice(0, 2);
    node.innerHTML = entries.length
        ? entries.map(([label, value], index) => `<span class="chart-focus-tag tone-${(index % 4) + 1}">${label} ${value}</span>`).join("")
        : `<span class="chart-focus-tag muted">暂无数据</span>`;
}

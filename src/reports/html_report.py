"""中文 HTML 候选票报告。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
import os
from pathlib import Path
from typing import Any

import pandas as pd

from src.features.required_columns import 基准代码
from src.reports.chart import 图表失败清单字段, 批量生成走势图, 配置图表字体
from src.reports.csv_report import 等级顺序
from src.utils.chinese import get_chinese_display_name


报告标题 = "美股主升浪突破候选票报告"
免责声明 = "本报告仅用于候选筛选和复盘，不构成买卖建议，不自动交易。"
缓存结果说明 = "当前结果只基于已缓存标的，不代表全市场。"
HTML失败清单字段 = 图表失败清单字段

HTML主表字段 = [
    "排名",
    "代码",
    "中文名称",
    "名称",
    "市场",
    "是否ETF",
    "是否杠杆ETF",
    "最新交易日",
    "最新收盘价",
    "当日涨幅",
    "5日涨幅",
    "20日涨幅",
    "60日涨幅",
    "成交额",
    "20日量比",
    "MACD状态",
    "突破状态",
    "相对强度状态",
    "综合评分",
    "等级",
    "等级说明",
    "入选理由",
    "风险标签",
    "观察价",
    "失效位",
]

HTML必要字段 = HTML主表字段 + [
    "趋势结构分",
    "突破强度分",
    "量能强度分",
    "相对强度分",
    "主升浪形态分",
    "风险扣分",
    "评分解释",
]


@dataclass(frozen=True)
class HtmlReportResult:
    """HTML 报告生成结果。"""

    html_path: Path
    report_path: Path
    failure_path: Path
    charts_dir: Path
    input_count: int
    display_count: int
    chart_count: int
    chart_failure_count: int
    contains_title: bool
    contains_disclaimer: bool
    contains_table: bool
    contains_cards: bool
    contains_risk_tags: bool
    contains_score_explanation: bool
    offline_ready: bool
    benchmark_excluded: bool
    recommendation: str


def 读取候选票(input_path: Path | str) -> pd.DataFrame:
    """读取候选票 CSV，并校验 HTML 必要字段。"""
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"候选票 CSV 不存在：{path}")
    df = pd.read_csv(path, encoding="utf-8-sig")
    if "中文名称" not in df.columns and {"代码", "名称", "是否ETF"}.issubset(df.columns):
        df["中文名称"] = df.apply(
            lambda row: get_chinese_display_name(row.get("代码", ""), row.get("名称", ""), row.get("是否ETF", "")),
            axis=1,
        )
    missing = [field for field in HTML必要字段 if field not in df.columns]
    if missing:
        raise ValueError(f"HTML报告生成失败：候选票缺少必要字段：{'、'.join(missing)}")
    return df


def 筛选HTML候选(df: pd.DataFrame, top: int = 100, min_score: float = 0, min_grade: str = "D") -> pd.DataFrame:
    """按 HTML 参数筛选候选票，不修改输入 DataFrame。"""
    output = df.copy(deep=True)
    output["综合评分"] = pd.to_numeric(output["综合评分"], errors="coerce")
    output = output[output["综合评分"] >= min_score].copy()
    min_grade_rank = 等级顺序[min_grade]
    output = output[output["等级"].map(等级顺序).fillna(-1) >= min_grade_rank].copy()
    output = output.sort_values(["综合评分", "代码"], ascending=[False, True]).reset_index(drop=True)
    if top > 0:
        output = output.head(top).copy()
    output["排名"] = range(1, len(output) + 1)
    return output


def 保存HTML失败清单(failures: pd.DataFrame, path: Path | str) -> Path:
    """保存 HTML 报告失败清单。"""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if failures.empty:
        failures = pd.DataFrame(columns=HTML失败清单字段)
    failures.to_csv(output_path, index=False, encoding="utf-8-sig")
    return output_path


def 生成HTML报告(
    input_path: Path | str,
    cache_dir: Path | str,
    output_path: Path | str,
    charts_dir: Path | str,
    report_path: Path | str,
    failure_path: Path | str,
    top: int = 100,
    min_score: float = 0,
    min_grade: str = "D",
    no_charts: bool = False,
) -> HtmlReportResult:
    """生成离线中文 HTML 报告、图表和验收报告。"""
    input_path = Path(input_path)
    output_path = Path(output_path)
    charts_dir = Path(charts_dir)
    report_path = Path(report_path)
    failure_path = Path(failure_path)
    generate_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    candidates = 读取候选票(input_path)
    display = 筛选HTML候选(candidates, top=top, min_score=min_score, min_grade=min_grade)
    font_warning = 配置图表字体()
    if no_charts:
        charts_dir.mkdir(parents=True, exist_ok=True)
        chart_paths: dict[str, Path] = {}
        failures = pd.DataFrame(columns=HTML失败清单字段)
    else:
        chart_paths, failures = 批量生成走势图(display, cache_dir=cache_dir, charts_dir=charts_dir)
    保存HTML失败清单(failures, failure_path)

    html = 渲染HTML(
        candidates=display,
        chart_paths=chart_paths,
        output_path=output_path,
        generate_time=generate_time,
        chart_failure_count=len(failures),
        no_charts=no_charts,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")

    validation = 验收HTML内容(html=html, input_count=len(candidates), display_count=len(display))
    severe_issues = 获取严重问题(validation, display)
    recommendation = "可以进入第 11 步扩大数据下载与真实候选池验证" if not severe_issues else "不建议进入第 11 步扩大数据下载与真实候选池验证"
    report = 生成HTML验收报告(
        input_path=input_path,
        output_path=output_path,
        charts_dir=charts_dir,
        report_path=report_path,
        failure_path=failure_path,
        input_count=len(candidates),
        display_count=len(display),
        chart_count=len(chart_paths),
        chart_failure_count=len(failures),
        validation=validation,
        severe_issues=severe_issues,
        recommendation=recommendation,
        generate_time=generate_time,
        font_warning=font_warning,
        no_charts=no_charts,
        benchmark_excluded=not set(display["代码"].astype(str).str.upper()).intersection(set(基准代码)) if not display.empty else True,
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    return HtmlReportResult(
        html_path=output_path,
        report_path=report_path,
        failure_path=failure_path,
        charts_dir=charts_dir,
        input_count=len(candidates),
        display_count=len(display),
        chart_count=len(chart_paths),
        chart_failure_count=len(failures),
        contains_title=validation["包含标题"],
        contains_disclaimer=validation["包含免责声明"],
        contains_table=validation["包含主表格"],
        contains_cards=validation["包含候选卡片"],
        contains_risk_tags=validation["包含风险标签"],
        contains_score_explanation=validation["包含评分解释"],
        offline_ready=validation["可以离线打开"],
        benchmark_excluded=not set(display["代码"].astype(str).str.upper()).intersection(set(基准代码)) if not display.empty else True,
        recommendation=recommendation,
    )


def 渲染HTML(
    candidates: pd.DataFrame,
    chart_paths: dict[str, Path],
    output_path: Path,
    generate_time: str,
    chart_failure_count: int,
    no_charts: bool,
) -> str:
    """渲染完整离线 HTML。"""
    grade_counts = {grade: int((candidates["等级"] == grade).sum()) if not candidates.empty else 0 for grade in ["A+", "A", "B", "C", "D"]}
    max_score = _format_score(candidates["综合评分"].max()) if not candidates.empty else "无"
    benchmark_excluded = not set(candidates["代码"].astype(str).str.upper()).intersection(set(基准代码)) if not candidates.empty else True
    rows_html = "\n".join(_render_table_row(row) for _, row in candidates.iterrows())
    cards_html = "\n".join(_render_candidate_card(row, chart_paths, output_path, no_charts) for _, row in candidates.iterrows())
    if not rows_html:
        rows_html = f"<tr><td colspan=\"{len(HTML主表字段)}\">暂无符合条件的候选票</td></tr>"
    if not cards_html:
        cards_html = "<p class=\"empty-state\">暂无符合条件的候选票</p>"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{报告标题}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1f2937;
      --muted: #64748b;
      --line: #d8dee8;
      --risk: #b42318;
      --accent: #0f766e;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", Arial, sans-serif;
      line-height: 1.55;
    }}
    .page {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 30px;
      letter-spacing: 0;
    }}
    h2 {{
      margin: 28px 0 12px;
      font-size: 20px;
      letter-spacing: 0;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
      margin: 18px 0;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
    }}
    .metric strong {{
      display: block;
      margin-top: 4px;
      font-size: 18px;
    }}
    .notice {{
      background: #fff7ed;
      border: 1px solid #fed7aa;
      border-radius: 8px;
      padding: 12px 14px;
      margin: 12px 0;
    }}
    .controls {{
      display: grid;
      grid-template-columns: 2fr 1fr 1fr auto;
      gap: 8px;
      align-items: end;
      margin: 18px 0;
    }}
    .controls label {{
      display: grid;
      gap: 4px;
      font-size: 13px;
      color: var(--muted);
    }}
    input, select {{
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
      background: #fff;
      color: var(--text);
      font: inherit;
    }}
    .checkbox-line {{
      display: flex;
      align-items: center;
      gap: 6px;
      height: 36px;
      color: var(--text);
    }}
    .table-wrap {{
      overflow-x: auto;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    table {{
      width: 100%;
      min-width: 1280px;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #eef2f7;
      white-space: nowrap;
    }}
    .candidate-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
      gap: 14px;
    }}
    .candidate-card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-left-width: 6px;
      border-radius: 8px;
      padding: 14px;
    }}
    .card-head {{
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: flex-start;
      margin-bottom: 10px;
    }}
    .code {{
      font-size: 20px;
      font-weight: 700;
    }}
    .name {{
      color: var(--muted);
      font-size: 13px;
      word-break: break-word;
    }}
    .grade {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 46px;
      border-radius: 999px;
      padding: 4px 9px;
      color: #fff;
      font-weight: 700;
      font-size: 13px;
    }}
    .grade-a-plus {{ background: #7c2d12; }}
    .grade-a {{ background: #b45309; }}
    .grade-b {{ background: #0f766e; }}
    .grade-c {{ background: #475569; }}
    .grade-d {{ background: #6b7280; }}
    .card-grade-a-plus {{ border-left-color: #7c2d12; }}
    .card-grade-a {{ border-left-color: #b45309; }}
    .card-grade-b {{ border-left-color: #0f766e; }}
    .card-grade-c {{ border-left-color: #475569; }}
    .card-grade-d {{ border-left-color: #6b7280; }}
    .risk-tag {{
      display: inline-block;
      margin: 3px 4px 3px 0;
      border: 1px solid #fecaca;
      background: #fff1f2;
      color: var(--risk);
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 700;
    }}
    .leveraged-warning {{
      display: inline-block;
      margin-left: 6px;
      border: 1px solid #f97316;
      background: #ffedd5;
      color: #9a3412;
      border-radius: 999px;
      padding: 3px 8px;
      font-size: 12px;
      font-weight: 700;
    }}
    .chart {{
      width: 100%;
      aspect-ratio: 2 / 1;
      object-fit: contain;
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 6px;
    }}
    .chart-missing {{
      display: grid;
      place-items: center;
      min-height: 160px;
      background: #f8fafc;
      border: 1px dashed var(--line);
      border-radius: 6px;
      color: var(--muted);
    }}
    .score-grid {{
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin: 10px 0;
      font-size: 13px;
    }}
    .score-grid div {{
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 8px;
    }}
    .score-grid span {{
      color: var(--muted);
      display: block;
    }}
    .reason, .explain {{
      margin: 8px 0;
      font-size: 13px;
    }}
    .footer {{
      margin-top: 28px;
      color: var(--muted);
      border-top: 1px solid var(--line);
      padding-top: 14px;
    }}
    .hidden {{ display: none; }}
    @media (max-width: 760px) {{
      .page {{ padding: 14px; }}
      .controls {{ grid-template-columns: 1fr; }}
      .candidate-grid {{ grid-template-columns: 1fr; }}
      .score-grid {{ grid-template-columns: 1fr 1fr; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <h1>{报告标题}</h1>
    <p class="notice">免责声明：{免责声明}</p>
    <section class="summary" aria-label="报告摘要">
      <div class="metric"><span>生成时间</span><strong>{escape(generate_time)}</strong></div>
      <div class="metric"><span>候选票数量</span><strong>{len(candidates)}</strong></div>
      <div class="metric"><span>数据来源</span><strong>本地缓存</strong></div>
      <div class="metric"><span>是否排除 QQQ/SPY</span><strong>{'是' if benchmark_excluded else '否'}</strong></div>
      <div class="metric"><span>最高评分</span><strong>{max_score}</strong></div>
      <div class="metric"><span>A+ 数量</span><strong>{grade_counts['A+']}</strong></div>
      <div class="metric"><span>A 数量</span><strong>{grade_counts['A']}</strong></div>
      <div class="metric"><span>B 数量</span><strong>{grade_counts['B']}</strong></div>
      <div class="metric"><span>C 数量</span><strong>{grade_counts['C']}</strong></div>
      <div class="metric"><span>D 数量</span><strong>{grade_counts['D']}</strong></div>
      <div class="metric"><span>失败图表数量</span><strong>{chart_failure_count}</strong></div>
    </section>
    <p class="notice">当前结果说明：{缓存结果说明}</p>
    <section class="controls" aria-label="筛选工具">
      <label>搜索代码或名称<input id="searchInput" type="search" placeholder="输入代码或名称"></label>
      <label>等级筛选<select id="gradeFilter"><option value="">全部等级</option><option>A+</option><option>A</option><option>B</option><option>C</option><option>D</option></select></label>
      <label>最低评分<input id="scoreFilter" type="number" min="0" max="100" step="1" value="0"></label>
      <label class="checkbox-line"><input id="riskOnly" type="checkbox">只看有风险标签</label>
    </section>
    <h2>候选票主表格</h2>
    <section class="table-wrap">
      <table id="candidateTable">
        <thead><tr>{''.join(f'<th>{escape(field)}</th>' for field in HTML主表字段)}</tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </section>
    <h2>候选卡片</h2>
    <section class="candidate-grid" id="candidateCards">
      {cards_html}
    </section>
    <p class="footer">免责声明：{免责声明}</p>
  </main>
  <script>
    const controls = {{
      search: document.getElementById('searchInput'),
      grade: document.getElementById('gradeFilter'),
      score: document.getElementById('scoreFilter'),
      riskOnly: document.getElementById('riskOnly')
    }};
    function filterItems() {{
      const keyword = controls.search.value.trim().toUpperCase();
      const grade = controls.grade.value;
      const minScore = Number(controls.score.value || 0);
      const riskOnly = controls.riskOnly.checked;
      document.querySelectorAll('[data-candidate]').forEach((item) => {{
        const text = item.dataset.search || '';
        const itemGrade = item.dataset.grade || '';
        const score = Number(item.dataset.score || 0);
        const hasRisk = item.dataset.hasRisk === '是';
        const visible = (!keyword || text.includes(keyword)) && (!grade || itemGrade === grade) && score >= minScore && (!riskOnly || hasRisk);
        item.classList.toggle('hidden', !visible);
      }});
    }}
    Object.values(controls).forEach((control) => control.addEventListener('input', filterItems));
  </script>
</body>
</html>
"""


def _render_table_row(row: pd.Series) -> str:
    score = _to_float(row.get("综合评分"))
    grade = str(row.get("等级", "D"))
    risk_text = str(row.get("风险标签", "无明显风险"))
    has_risk = "否" if risk_text == "无明显风险" else "是"
    search_text = f"{row.get('代码', '')} {row.get('中文名称', '')} {row.get('名称', '')}".upper()
    cells = "".join(f"<td>{_format_field(field, row.get(field))}</td>" for field in HTML主表字段)
    return f'<tr data-candidate data-search="{escape(search_text)}" data-grade="{escape(grade)}" data-score="{score:.2f}" data-has-risk="{has_risk}">{cells}</tr>'


def _render_candidate_card(row: pd.Series, chart_paths: dict[str, Path], output_path: Path, no_charts: bool) -> str:
    ticker = str(row.get("代码", "")).upper()
    grade = str(row.get("等级", "D"))
    grade_class = _grade_class(grade)
    score = _to_float(row.get("综合评分"))
    risk_text = str(row.get("风险标签", "无明显风险"))
    has_risk = "否" if risk_text == "无明显风险" else "是"
    chinese_name = str(row.get("中文名称", "") or get_chinese_display_name(ticker, row.get("名称", ""), row.get("是否ETF", "")))
    search_text = f"{ticker} {chinese_name} {row.get('名称', '')}".upper()
    chart_html = '<div class="chart-missing">图表暂不可用</div>'
    if not no_charts and ticker in chart_paths:
        rel_path = Path(os.path.relpath(chart_paths[ticker], start=output_path.parent)).as_posix()
        chart_html = f'<img class="chart" src="{escape(rel_path)}" alt="{escape(ticker)} 走势缩略图">'
    leveraged = '<span class="leveraged-warning">杠杆ETF高风险</span>' if str(row.get("是否杠杆ETF", "")) == "是" else ""
    risk_tags = "".join(f'<span class="risk-tag">{escape(tag.strip())}</span>' for tag in risk_text.split("；") if tag.strip())

    return f"""
      <article class="candidate-card card-{grade_class}" data-candidate data-search="{escape(search_text)}" data-grade="{escape(grade)}" data-score="{score:.2f}" data-has-risk="{has_risk}">
        <div class="card-head">
          <div>
            <div class="code">第{_format_plain(row.get('排名'))}名 {escape(chinese_name)}（{escape(ticker)}） {leveraged}</div>
            <div class="name">原始名称：{escape(str(row.get('名称', '')))}</div>
          </div>
          <div><span class="grade {grade_class}">{escape(grade)}</span><div>综合评分 {_format_score(score)}</div></div>
        </div>
        {chart_html}
        <div class="score-grid">
          <div><span>趋势结构分</span>{_format_score(row.get('趋势结构分'))}</div>
          <div><span>突破强度分</span>{_format_score(row.get('突破强度分'))}</div>
          <div><span>量能强度分</span>{_format_score(row.get('量能强度分'))}</div>
          <div><span>相对强度分</span>{_format_score(row.get('相对强度分'))}</div>
          <div><span>主升浪形态分</span>{_format_score(row.get('主升浪形态分'))}</div>
          <div><span>风险扣分</span>{_format_score(row.get('风险扣分'))}</div>
        </div>
        <p class="reason"><strong>入选理由：</strong>{escape(str(row.get('入选理由', '')))}</p>
        <p class="reason"><strong>风险标签：</strong>{risk_tags}</p>
        <p class="explain"><strong>评分解释：</strong>{escape(str(row.get('评分解释', '')))}</p>
        <p><strong>观察价：</strong>{_format_price(row.get('观察价'))}　<strong>失效位：</strong>{_format_price(row.get('失效位'))}</p>
      </article>
    """


def _format_field(field: str, value: Any) -> str:
    if field in {"当日涨幅", "5日涨幅", "20日涨幅", "60日涨幅"}:
        return escape(_format_percent(value))
    if field in {"最新收盘价", "观察价", "失效位"}:
        return escape(_format_price(value))
    if field in {"综合评分"}:
        return escape(_format_score(value))
    if field in {"成交额"}:
        return escape(_format_amount(value))
    if field in {"20日量比"}:
        return escape(_format_ratio(value))
    return escape(_format_plain(value))


def _format_plain(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def _format_price(value: Any) -> str:
    number = _to_float(value)
    if pd.isna(number):
        return ""
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _format_score(value: Any) -> str:
    number = _to_float(value)
    if pd.isna(number):
        return "无"
    return f"{number:.1f}"


def _format_percent(value: Any) -> str:
    number = _to_float(value)
    if pd.isna(number):
        return ""
    return f"{number * 100:.2f}%"


def _format_ratio(value: Any) -> str:
    number = _to_float(value)
    if pd.isna(number):
        return ""
    return f"{number:.2f}"


def _format_amount(value: Any) -> str:
    number = _to_float(value)
    if pd.isna(number):
        return ""
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:.2f}亿"
    if abs(number) >= 10_000:
        return f"{number / 10_000:.2f}万"
    return f"{number:.0f}"


def _to_float(value: Any) -> float:
    return float(pd.to_numeric(value, errors="coerce"))


def _grade_class(grade: str) -> str:
    mapping = {"A+": "grade-a-plus", "A": "grade-a", "B": "grade-b", "C": "grade-c", "D": "grade-d"}
    return mapping.get(grade, "grade-d")


def 验收HTML内容(html: str, input_count: int, display_count: int) -> dict[str, bool]:
    """检查 HTML 关键内容。"""
    return {
        "包含标题": 报告标题 in html,
        "包含免责声明": 免责声明 in html,
        "包含主表格": 'id="candidateTable"' in html,
        "包含候选卡片": 'class="candidate-card' in html,
        "包含风险标签": "风险标签" in html and "risk-tag" in html,
        "包含评分解释": "评分解释" in html,
        "可以离线打开": "http://" not in html and "https://" not in html,
        "输入非空时有展示": not (input_count > 0 and display_count == 0),
    }


def 获取严重问题(validation: dict[str, bool], candidates: pd.DataFrame) -> list[str]:
    """根据验收结果返回严重问题。"""
    issues: list[str] = []
    if not validation["包含主表格"]:
        issues.append("主表格缺失")
    if not validation["包含候选卡片"]:
        issues.append("候选卡片缺失")
    if not validation["包含风险标签"]:
        issues.append("风险标签为空或缺失")
    if not validation["包含评分解释"]:
        issues.append("评分解释为空或缺失")
    if not validation["输入非空时有展示"]:
        issues.append("输入候选数量大于0但HTML展示数量为0")
    if not candidates.empty and candidates["风险标签"].astype(str).str.strip().eq("").any():
        issues.append("存在风险标签为空的候选")
    if not candidates.empty and candidates["评分解释"].astype(str).str.strip().eq("").any():
        issues.append("存在评分解释为空的候选")
    return issues


def 生成HTML验收报告(
    input_path: Path,
    output_path: Path,
    charts_dir: Path,
    report_path: Path,
    failure_path: Path,
    input_count: int,
    display_count: int,
    chart_count: int,
    chart_failure_count: int,
    validation: dict[str, bool],
    severe_issues: list[str],
    recommendation: str,
    generate_time: str,
    font_warning: str | None,
    no_charts: bool,
    benchmark_excluded: bool,
) -> str:
    """生成 HTML 报告验收 Markdown。"""
    lines = [
        "# HTML报告验收报告",
        "",
        f"1. 生成时间：{generate_time}",
        f"2. 输入 CSV 路径：`{input_path}`",
        f"3. 输出 HTML 路径：`{output_path}`",
        f"4. 图表目录：`{charts_dir}`",
        f"5. 输入候选数量：{input_count}",
        f"6. HTML 展示候选数量：{display_count}",
        f"7. 生成图表数量：{chart_count}",
        f"8. 图表失败数量：{chart_failure_count}",
        f"9. 是否默认排除 QQQ/SPY：{'是' if benchmark_excluded else '否'}",
        f"10. HTML 是否包含标题：{'是' if validation['包含标题'] else '否'}",
        f"11. HTML 是否包含免责声明：{'是' if validation['包含免责声明'] else '否'}",
        f"12. HTML 是否包含主表格：{'是' if validation['包含主表格'] else '否'}",
        f"13. HTML 是否包含候选卡片：{'是' if validation['包含候选卡片'] else '否'}",
        f"14. HTML 是否包含风险标签：{'是' if validation['包含风险标签'] else '否'}",
        f"15. HTML 是否包含评分解释：{'是' if validation['包含评分解释'] else '否'}",
        f"16. HTML 是否可以离线打开：{'是' if validation['可以离线打开'] else '否'}",
        f"17. 失败清单路径：`{failure_path}`",
        "18. 当前结果是否只基于已缓存标的：是，当前结果只基于已缓存标的，不代表全市场。",
        "19. 是否建议进入第 11 步“扩大数据下载与真实候选池验证”：",
        f"    - {recommendation}",
        "",
        "## 补充说明",
        "",
        f"- 图表模式：{'未生成图表，仅生成文字和表格' if no_charts else '已尝试生成本地图表'}",
        f"- 字体提示：{font_warning or '无'}",
        "- 本系统只做候选票筛选和复盘辅助，不自动交易，不给确定性买卖建议。",
        "",
        "## 严重问题",
        "",
    ]
    if severe_issues:
        lines.extend(f"- {issue}" for issue in severe_issues)
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"

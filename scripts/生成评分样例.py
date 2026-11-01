"""生成主升浪相似度评分样例。

只读取本地技术特征样例，不联网、不下载行情、不生成最终候选票。
"""

from __future__ import annotations

import argparse
from datetime import datetime
import sys
from pathlib import Path

import pandas as pd


项目根目录 = Path(__file__).resolve().parents[1]
if str(项目根目录) not in sys.path:
    sys.path.insert(0, str(项目根目录))

from src.scoring.scoring_pipeline import 评分输出字段, score_feature_dataframe_with_failures  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402


默认输入路径 = 项目根目录 / "data" / "output" / "技术特征样例.csv"
默认输出路径 = 项目根目录 / "data" / "output" / "评分样例.csv"
默认报告路径 = 项目根目录 / "data" / "output" / "评分验收报告.md"
默认失败路径 = 项目根目录 / "data" / "output" / "评分失败清单.csv"


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="生成主升浪相似度评分样例。")
    parser.add_argument("--input", type=str, default=str(默认输入路径), help="技术特征样例输入路径。")
    parser.add_argument("--output", type=str, default=str(默认输出路径), help="评分样例输出路径。")
    parser.add_argument("--top", type=int, default=20, help="最多输出前 N 只，0 表示不限制。")
    parser.add_argument("--min-score", type=float, default=0.0, help="最低综合评分过滤。")
    return parser.parse_args()


def main() -> int:
    """生成评分样例。"""
    args = parse_args()
    logger = get_logger("Mstock评分样例")
    input_path = Path(args.input)
    output_path = Path(args.output)

    if args.top < 0:
        logger.error("参数错误：--top 不能小于0。")
        return 1
    if args.min_score < 0 or args.min_score > 100:
        logger.error("参数错误：--min-score 必须在0到100之间。")
        return 1
    if not input_path.exists():
        logger.error(f"评分样例生成失败：输入文件不存在：{input_path}")
        return 1

    feature_df = pd.read_csv(input_path, encoding="utf-8-sig")
    try:
        result = score_feature_dataframe_with_failures(feature_df)
    except Exception as exc:
        logger.error(f"评分样例生成失败：{exc}")
        return 1

    scored = result.scored.copy()
    before_filter_count = len(scored)
    if not scored.empty:
        scored = scored[scored["综合评分"] >= args.min_score].copy()
        if args.top > 0:
            scored = scored.head(args.top).copy()
        scored = scored.reset_index(drop=True)
        scored["排名"] = range(1, len(scored) + 1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(output_path, index=False, encoding="utf-8-sig")
    result.failures.to_csv(默认失败路径, index=False, encoding="utf-8-sig")

    report = 生成评分验收报告(
        input_path=input_path,
        output_path=output_path,
        input_count=len(feature_df),
        success_count=before_filter_count,
        failure_count=len(result.failures),
        scored=scored,
    )
    默认报告路径.write_text(report, encoding="utf-8")

    logger.info(f"评分样例已生成：{output_path}")
    logger.info(f"评分样例行数：{len(scored)}")
    logger.info(f"评分失败数量：{len(result.failures)}")
    logger.info(f"评分验收报告已生成：{默认报告路径}")
    return 0


def 生成评分验收报告(
    input_path: Path,
    output_path: Path,
    input_count: int,
    success_count: int,
    failure_count: int,
    scored: pd.DataFrame,
) -> str:
    """生成中文评分验收报告。"""
    severe_issues: list[str] = []
    missing_output_fields = [field for field in 评分输出字段 if field not in scored.columns]
    if missing_output_fields:
        severe_issues.append(f"缺失评分字段：{'、'.join(missing_output_fields)}")
    if success_count == 0 and input_count > 0:
        severe_issues.append("全部评分失败")

    score_range_ok = True
    sub_score_ok = True
    empty_reason = False
    empty_risk = False
    empty_explanation = False
    if not scored.empty:
        score_range_ok = scored["综合评分"].between(0, 100).all()
        sub_score_ok = (
            (scored["趋势结构分"].between(0, 25).all())
            and (scored["突破强度分"].between(0, 25).all())
            and (scored["量能强度分"].between(0, 15).all())
            and (scored["相对强度分"].between(0, 15).all())
            and (scored["主升浪形态分"].between(0, 10).all())
            and (scored["风险扣分"].between(0, 20).all())
        )
        empty_reason = scored["入选理由"].astype(str).str.strip().eq("").any()
        empty_risk = scored["风险标签"].astype(str).str.strip().eq("").any()
        empty_explanation = scored["评分解释"].astype(str).str.strip().eq("").any()

    if not score_range_ok:
        severe_issues.append("综合评分超出0到100")
    if not sub_score_ok:
        severe_issues.append("分项分数超出上限")
    if empty_reason:
        severe_issues.append("入选理由为空")
    if empty_risk:
        severe_issues.append("风险标签为空")
    if empty_explanation:
        severe_issues.append("评分解释为空")

    recommend = not severe_issues
    grade_distribution = scored["等级"].value_counts().to_dict() if not scored.empty else {}
    top10 = scored.head(10) if not scored.empty else pd.DataFrame(columns=评分输出字段)

    lines = [
        "# 评分验收报告",
        "",
        f"1. 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"2. 输入文件路径：`{input_path}`",
        f"3. 输出文件路径：`{output_path}`",
        f"4. 输入股票数量：{input_count}",
        f"5. 成功评分数量：{success_count}",
        f"6. 失败评分数量：{failure_count}",
        f"7. 评分字段是否完整：{'是' if not missing_output_fields else '否'}",
        f"8. 综合评分是否全部在 0-100：{'是' if score_range_ok else '否'}",
        f"9. 分项分数是否超过上限：{'否' if sub_score_ok else '是'}",
        f"10. 是否存在空的入选理由：{'是' if empty_reason else '否'}",
        f"11. 是否存在空的风险标签：{'是' if empty_risk else '否'}",
        f"12. 是否存在空的评分解释：{'是' if empty_explanation else '否'}",
        "13. 等级分布：",
    ]
    if grade_distribution:
        for grade, count in grade_distribution.items():
            lines.append(f"    - {grade}：{count}")
    else:
        lines.append("    - 无")
    lines.extend(["14. Top 10 摘要："])
    if top10.empty:
        lines.append("    - 无")
    else:
        for _, row in top10.iterrows():
            lines.append(
                f"    - 第{int(row['排名'])}名 {row['代码']}：综合评分{row['综合评分']}，等级{row['等级']}，理由：{row['入选理由']}"
            )
    lines.extend(
        [
            "15. 是否建议进入第 9 步“中文候选票输出”：",
            f"    - {'可以进入第 9 步中文候选票输出' if recommend else '不建议进入第 9 步中文候选票输出'}",
            "",
            "## 严重问题",
            "",
        ]
    )
    if severe_issues:
        for issue in severe_issues:
            lines.append(f"- {issue}")
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())

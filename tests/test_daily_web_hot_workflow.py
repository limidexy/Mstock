import argparse
from types import SimpleNamespace

import pandas as pd

from scripts import 每日网上热度选票流程 as workflow


def test_daily_workflow_supports_skip_network_and_skip_download(tmp_path, monkeypatch):
    """每日流程支持 skip-network 和 skip-download，并生成 Top 20 摘要报告。"""
    for name, path in {
        "默认热度池路径": tmp_path / "网上热度池.csv",
        "默认热度池报告路径": tmp_path / "网上热度池生成报告.md",
        "默认热度来源失败路径": tmp_path / "网上热度来源失败清单.csv",
        "默认热度下载失败路径": tmp_path / "网上热度池下载失败清单.csv",
        "默认流程报告路径": tmp_path / "每日网上热度流程报告.md",
        "默认股票池路径": tmp_path / "美股股票池.csv",
        "默认缓存目录": tmp_path / "daily",
        "默认候选输出路径": tmp_path / "今日候选票.csv",
        "默认候选报告路径": tmp_path / "候选票生成报告.md",
        "默认候选失败路径": tmp_path / "候选票失败清单.csv",
        "默认HTML路径": tmp_path / "今日候选票.html",
        "默认HTML报告路径": tmp_path / "HTML报告验收报告.md",
        "默认HTML失败路径": tmp_path / "HTML报告失败清单.csv",
        "默认图表目录": tmp_path / "charts",
    }.items():
        monkeypatch.setattr(workflow, name, path)
    monkeypatch.setattr(workflow, "项目根目录", tmp_path)

    hot_df = pd.DataFrame(
        {
            "代码": ["NBIS"],
            "来源分类": ["涨幅榜；阶段新高"],
            "是否涨幅榜": ["是"],
            "是否成交量榜": ["否"],
            "是否热门趋势": ["否"],
            "是否阶段新高": ["是"],
        }
    )
    candidate_df = pd.DataFrame(
        {
            "排名": [1],
            "代码": ["NBIS"],
            "中文名称": ["待补充中文名"],
            "名称": ["Nebius"],
            "是否ETF": ["否"],
            "综合评分": [55.0],
            "等级": ["C"],
            "当日涨幅": [0.1],
            "5日涨幅": [0.2],
            "入选理由": ["突破20日新高"],
        }
    )

    def fake_hot(args):
        assert args.no_network is True
        return SimpleNamespace(
            数据=hot_df,
            来源统计=[object()],
            来源成功数量=1,
            来源失败数量=0,
        )

    def fake_download(args):
        raise AssertionError("skip-download 时不应下载行情")

    monkeypatch.setattr(workflow, "运行生成网上热度池", fake_hot)
    monkeypatch.setattr(workflow, "运行更新网上热度池行情", fake_download)
    monkeypatch.setattr(workflow, "生成候选票", lambda **kwargs: SimpleNamespace(candidates=candidate_df, failures=pd.DataFrame()))
    monkeypatch.setattr(workflow, "生成候选票报告", lambda **kwargs: "候选票生成报告\n")
    monkeypatch.setattr(workflow, "生成HTML报告", lambda **kwargs: kwargs["output_path"].write_text("HTML", encoding="utf-8"))

    context = workflow.运行每日网上热度流程(
        argparse.Namespace(
            limit=500,
            top=100,
            skip_download=True,
            skip_network=True,
            missing_only=True,
            provider="auto",
            sleep_min=0.0,
            sleep_max=0.0,
            max_retries=0,
            days=300,
            sources=workflow.默认来源,
        )
    )

    assert context.本轮尝试下载数量 == 0
    assert context.今日候选票数量 == 1
    report = (tmp_path / "每日网上热度流程报告.md").read_text(encoding="utf-8")
    assert "Top 20 摘要" in report
    assert "热度来源不是买入理由" in report

import io
import re
from pathlib import Path

import pytest

from src.utils.chinese import (
    get_candidate_fields,
    get_reason_codes,
    get_risk_tags,
    require_known_field,
    to_chinese_bool,
)
from src.utils.logger import get_logger


项目根目录 = Path(__file__).resolve().parents[1]
中文字符模式 = re.compile(r"[\u4e00-\u9fff]")


候选字段 = [
    "排名",
    "代码",
    "中文名称",
    "名称",
    "市场",
    "是否ETF",
    "是否杠杆ETF",
    "最新收盘价",
    "当日涨幅",
    "5日涨幅",
    "10日涨幅",
    "20日涨幅",
    "60日涨幅",
    "成交量",
    "成交额",
    "20日量比",
    "MA5乖离",
    "MA10乖离",
    "MA20乖离",
    "距离20日新高",
    "距离60日新高",
    "距离120日新高",
    "MACD状态",
    "相对QQQ强度",
    "相对SPY强度",
    "趋势结构分",
    "突破强度分",
    "量能强度分",
    "相对强度分",
    "主升浪形态分",
    "风险扣分",
    "综合评分",
    "等级",
    "入选理由",
    "风险标签",
    "观察价",
    "失效位",
    "我的校对",
    "我的备注",
    "是否加入观察池",
    "是否实际交易",
    "交易结果",
]

入选理由 = [
    "均线多头排列",
    "突破20日新高",
    "突破60日新高",
    "接近120日新高",
    "放量突破",
    "成交额放大",
    "MACD红柱扩大",
    "强于QQQ",
    "强于SPY",
    "收盘接近日高",
    "主升浪加速",
    "平台突破",
    "回踩MA10后转强",
]

风险标签 = [
    "距离MA5过远",
    "距离MA10过远",
    "连续加速过热",
    "长上影线",
    "缩量冲高",
    "盘后走弱",
    "杠杆ETF风险",
    "流动性不足",
    "买卖价差可能偏大",
    "高波动风险",
]


def test_core_user_visible_files_are_chinese():
    """检查关键用户可见文件包含中文内容。"""
    files = [
        "AGENTS.md",
        "README.md",
        "docs/策略说明.md",
        "docs/截图风格总结.md",
        "docs/中文字段说明.md",
        "docs/风险标签说明.md",
        "docs/数据源说明.md",
        "config/系统配置.yml",
        "config/评分权重.yml",
        "config/数据源配置.example.yml",
    ]

    for file_path in files:
        text = (项目根目录 / file_path).read_text(encoding="utf-8")
        assert 中文字符模式.search(text), f"{file_path} 缺少中文内容"


def test_project_declares_no_auto_trading():
    """检查项目明确声明不自动交易。"""
    agents_text = (项目根目录 / "AGENTS.md").read_text(encoding="utf-8")
    readme_text = (项目根目录 / "README.md").read_text(encoding="utf-8")
    config_text = (项目根目录 / "config/系统配置.yml").read_text(encoding="utf-8")

    combined_text = "\n".join([agents_text, readme_text, config_text])

    assert "不自动" in combined_text
    assert "允许自动交易: false" in config_text
    assert "允许连接券商账户: false" in config_text


def test_candidate_fields_are_centralized_and_chinese():
    """检查候选报表字段集中维护且全部为中文字段。"""
    fields = get_candidate_fields()

    assert fields == 候选字段
    for field in fields:
        assert 中文字符模式.search(field), f"字段缺少中文：{field}"


def test_reason_codes_are_centralized_and_chinese():
    """检查入选理由集中维护且全部为中文原因。"""
    reasons = get_reason_codes()

    assert reasons == 入选理由
    for reason in reasons:
        assert 中文字符模式.search(reason), f"入选理由缺少中文：{reason}"


def test_risk_tags_are_centralized_and_chinese():
    """检查风险标签集中维护且全部为中文标签。"""
    tags = get_risk_tags()

    assert tags == 风险标签
    for tag in tags:
        assert 中文字符模式.search(tag), f"风险标签缺少中文：{tag}"


def test_chinese_bool_and_error_message_are_chinese():
    """检查工具函数返回中文，并且错误提示为中文。"""
    assert to_chinese_bool(True) == "是"
    assert to_chinese_bool(False) == "否"
    require_known_field("综合评分")

    with pytest.raises(ValueError, match="未知中文字段"):
        require_known_field("unknown")

    with pytest.raises(TypeError, match="布尔值转换失败"):
        to_chinese_bool("是")


def test_logger_outputs_chinese_level_name_and_message():
    """检查日志工具输出中文级别和中文消息。"""
    stream = io.StringIO()
    logger = get_logger("Mstock测试中文日志", stream=stream)

    logger.info("候选筛选开始")

    output = stream.getvalue()
    assert "信息" in output
    assert "候选筛选开始" in output

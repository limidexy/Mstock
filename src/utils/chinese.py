"""中文字段、中文原因码和中文风险标签。

本模块集中维护用户可见的中文文本，便于报表、日志和测试统一校验。
"""

from __future__ import annotations


候选报表字段 = [
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

中文原因码 = [
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

中文风险标签 = [
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

等级说明 = {
    "A+": "核心主升浪候选",
    "A": "强趋势候选",
    "B": "观察候选",
    "C": "形态不完整",
    "D": "不符合风格",
}

布尔中文 = {
    True: "是",
    False: "否",
}

常用中文简称 = {
    "A": "安捷伦科技",
    "AA": "美国铝业",
    "AAAA": "激进资产配置ETF",
    "AAAC": "AAA级CLO ETF",
    "AACB": "Artius II并购公司",
    "AAL": "美国航空",
    "AAON": "AAON暖通设备",
    "AAPL": "苹果",
    "ABNB": "爱彼迎",
    "AMD": "超威半导体",
    "AMAT": "应用材料",
    "AMZN": "亚马逊",
    "APP": "AppLovin移动广告平台",
    "ARKK": "方舟创新ETF",
    "ARM": "安谋",
    "ASML": "阿斯麦",
    "AVGO": "博通",
    "BABA": "阿里巴巴",
    "COIN": "Coinbase",
    "CRWD": "CrowdStrike网络安全",
    "DDOG": "Datadog云监控",
    "DKNG": "DraftKings",
    "FNGD": "FANG+三倍做空ETN",
    "FNGU": "FANG+三倍做多ETN",
    "GOOGL": "谷歌A",
    "HACK": "网络安全ETF",
    "HAKY": "网络安全备兑ETF",
    "HOOD": "Robinhood",
    "IAE": "亚太高股息基金",
    "IALT": "系统另类策略ETF",
    "IGV": "软件行业ETF",
    "INTC": "英特尔",
    "KLAC": "科磊",
    "LABD": "生物科技三倍做空ETF",
    "LABU": "生物科技三倍做多ETF",
    "LI": "理想汽车",
    "LRCX": "泛林集团",
    "MDB": "MongoDB",
    "MELI": "美客多",
    "META": "Meta",
    "MSFT": "微软",
    "MSTR": "MicroStrategy比特币概念",
    "MU": "美光科技",
    "NET": "Cloudflare云网络",
    "NFLX": "奈飞",
    "NIO": "蔚来",
    "NVDA": "英伟达",
    "PANW": "帕洛阿尔托网络",
    "PDD": "拼多多",
    "PLTR": "Palantir数据分析",
    "PYPL": "PayPal支付",
    "QAI": "多策略对冲ETF",
    "QCOM": "高通",
    "QQQ": "纳指100ETF",
    "RBLX": "Roblox游戏平台",
    "ROKU": "Roku流媒体",
    "SE": "Sea东南亚互联网",
    "SHOP": "Shopify电商",
    "SMCI": "超微电脑",
    "SMH": "半导体ETF",
    "SNOW": "Snowflake",
    "SOFI": "SoFi",
    "SOXX": "半导体ETF",
    "SOXL": "半导体三倍做多ETF",
    "SOXS": "半导体三倍做空ETF",
    "SPY": "标普500ETF",
    "SQ": "Block",
    "TAC": "TransAlta电力",
    "TECL": "科技三倍做多ETF",
    "TECS": "科技三倍做空ETF",
    "TSLA": "特斯拉",
    "TSM": "台积电",
    "TTD": "Trade Desk广告科技",
    "U": "Unity软件",
    "UBER": "优步",
    "WAGN": "帕伯莱Wagons ETF",
    "XLC": "通信服务ETF",
    "XLE": "能源ETF",
    "XLF": "金融ETF",
    "XLI": "工业ETF",
    "XLK": "科技行业ETF",
    "XLY": "可选消费ETF",
    "XPEV": "小鹏汽车",
}


def get_candidate_fields() -> list[str]:
    """返回候选报表中文字段。"""
    return 候选报表字段.copy()


def get_reason_codes() -> list[str]:
    """返回中文入选理由。"""
    return 中文原因码.copy()


def get_risk_tags() -> list[str]:
    """返回中文风险标签。"""
    return 中文风险标签.copy()


def get_chinese_display_name(code: str, original_name: str = "", is_etf: str = "") -> str:
    """返回适合中文报告展示的简称。"""
    normalized = str(code).strip().upper()
    if normalized in 常用中文简称:
        return 常用中文简称[normalized]
    if str(is_etf).strip() == "是":
        return "待补充中文ETF"
    if not str(original_name).strip() or str(original_name).strip() == "不足数据":
        return "待补充中文名"
    return "待补充中文名"


def get_display_label(code: str, chinese_name: str = "", original_name: str = "", is_etf: str = "") -> str:
    """返回中文名称加代码的展示标签。"""
    display_name = str(chinese_name).strip() or get_chinese_display_name(code, original_name, is_etf)
    return f"{display_name}（{str(code).strip().upper()}）"


def to_chinese_bool(value: bool) -> str:
    """把布尔值转换为中文。"""
    if not isinstance(value, bool):
        raise TypeError("布尔值转换失败：输入必须是布尔类型。")
    return 布尔中文[value]


def require_known_field(field_name: str) -> None:
    """校验字段是否属于候选报表中文字段。"""
    if field_name not in 候选报表字段:
        raise ValueError(f"未知中文字段：{field_name}")

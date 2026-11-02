# Mstock

Mstock 是一个全中文的美股 / ETF 主升浪突破相似票筛选与复盘系统。

系统目标是帮助用户在冷启动阶段，从公开股票池和日线行情中筛选可能符合“主升浪突破”风格的候选票，并通过中文报告辅助人工复盘。

## 当前状态

已实现股票池、行情缓存与备用数据源、技术特征、规则评分、中文候选 CSV、待校对 CSV、离线 HTML 与走势缩略图，以及国内外公开热度来源的覆盖扩展。

当前是市场研究与候选筛选系统，不是交易执行或收益回测系统。人工校对偏好分析仍为占位模块。历史输出不代表最新市场状态。

迁移请先读 [迁移交接资料](docs/MIGRATION_HANDOFF.md) 和 [开发接续说明](docs/PROJECT_CONTINUATION.md)。GitHub 只保存安全源码与模板，行情、人工校对及历史输出须另行恢复。

公开源码仓库：[limidexy/Mstock](https://github.com/limidexy/Mstock)。真实行情缓存、私人校对、迁移备份和真实环境变量不随仓库发布；首次克隆后没有历史数据属于预期状态，测试使用独立模拟样本。

## 系统边界

- 只做候选票筛选和复盘辅助。
- 不自动下单。
- 不连接券商账户。
- 不输出确定性的买卖建议。
- 第一版以规则评分为主，不使用机器学习作为核心逻辑。

## 目录说明

```text
docs/      中文说明文档
config/    系统配置、评分权重和数据源配置模板
data/      原始数据、处理数据、缓存、校对和输出目录
src/       Python 源码模块
scripts/   中文命令脚本入口
tests/     基础测试
```

## 云端运行

旧电脑不在身边时，打开 [云端小批量选票](https://github.com/limidexy/Mstock/actions/workflows/cloud-run.yml)，点击“运行工作流”（Run workflow），勾选允许本轮获取公开日线行情。完成后下载该次运行的 `Mstock-report`，解压并打开 `index.html`。默认8只指定股票加QQQ/SPY基准，只用于小批量运行，报告标明实际数据日期和覆盖范围。

仅检查代码时使用 [云端源码验收](https://github.com/limidexy/Mstock/actions/workflows/cloud-check.yml)，该入口不下载真实行情。两个入口均不会恢复旧电脑私人历史数据。具体操作和范围见 [云端使用说明](docs/CLOUD_USAGE.md)。

## Windows 环境与测试

使用64位 Python 3.12，不使用系统默认 Python 3.14。依赖锁定文件是本次迁移验证环境快照，不是无法考证的原始环境快照。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-windows-lock.txt
.\.venv\Scripts\python.exe -m pytest
```

测试使用临时模拟数据，不需要真实缓存或联网。已有数据恢复后，可运行 `scripts/迁移离线验收.py` 检查实际缓存与固定样本计算一致性。

## 风险提示

本项目输出仅用于候选筛选和复盘研究，不构成投资建议。任何交易决策都需要用户自行判断并承担风险。

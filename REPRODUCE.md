# 复现说明（REPRODUCE）

**项目**：持续同调量化研究项目（tda_project）
**目标**：让第三方在一台干净机器上复现论文第五章的主结果、留出验证报告的全部表格，以及两轮数据修正（基准日历重建、候选重算）。
**前提**：数据不在包内。先读 `DATA_MANIFEST.md`，按第 6 节重建或直接使用随包的衍生表。

---

## 1. 环境

| 项 | 值 |
|---|---|
| 操作系统 | Windows 10/11（亦可在 Linux 下运行，路径改为正斜杠） |
| Python | 3.12（开发环境为独立虚拟环境，不污染系统 3.13） |
| 依赖 | `pip install -r requirements.lock.txt` |
| 关键依赖 | giotto-tda 0.6.2、gudhi 3.13.0、giotto-ph 0.2.4、multipers、persim、pandas、numpy |
| 排版（仅重建 PDF 时） | TeX Live 2026 + XeLaTeX，中文字体 SimSun/SimHei |

`install.log`（随包）记录了实际安装过程与失败项。离线 wheel 归档（仅 multipers 一个，8.7 MB）在开发机的 `tda_project/vendor/wheels/`，未随包交付；无外网时按 `install.log` 记录的版本另行下载即可。

**本包目录与开发目录的对应关系**（重要）：开发工程的布局是 `工作根/paper_drafts/` 与 `工作根/tda_project/{config,src,outputs}` 并列，另有 `工作根/a_share_pit/` 数据目录。本交付包把 `tda_project/` 的内容与 `paper_drafts/` 平铺进了 `03_可复现代码/`。因此：

| 本包路径 | 开发工程路径 |
|---|---|
| `03_可复现代码/config/` | `tda_project/config/` |
| `03_可复现代码/src/` | `tda_project/src/` |
| `03_可复现代码/outputs/` | `tda_project/outputs/`（仅关键校验产物） |
| `03_可复现代码/paper_drafts/` | `工作根/paper_drafts/` |

要真正重跑脚本，须先按 DATA_MANIFEST 第 6 节重建数据，然后**恢复开发目录布局**：把 `config/`、`src/`、`outputs/` 三个目录放回 `tda_project/` 下，使 `paper_drafts/` 与 `tda_project/` 并列。原因：`src/regime_check/` 的脚本按 `parents[2]/outputs` 定位（在本包布局下可直接运行），而 `paper_drafts/` 的脚本按 `parents[1]/tda_project/outputs` 定位（要求开发布局）。两处路径写法不一致是历史遗留，此处如实说明，不改动脚本。

---

## 2. 目录约定

```
tda_project/
├── config/             39 个预登记 TOML（每个版本的判定规则与门槛）
├── src/
│   ├── data/           PIT 面板构造
│   ├── topology/       持续同调特征（点云、切片、A/D 特征）
│   ├── labels.py       冻结危机标签
│   ├── evaluation.py   因果评估
│   ├── regime_check/   v0.03 至 v0.26 全链路脚本
│   ├── phti_replication/
│   └── xy_replication/ 兴业相关网络复现与审计
├── outputs/            全部产物（CSV / JSON / HTML）
└── requirements.lock.txt
paper_drafts/           后期分析与实验脚本（v0.21 至 v0.34）
```

所有脚本默认从项目根目录运行，读写 `tda_project/outputs/` 下的固定文件名。

---

## 3. 最小复现路径（只复现论文主结果，约 3 步）

| 步骤 | 命令 | 产出 | 校验点 |
|---|---|---|---|
| 1 | `python paper_drafts/run_v033_rebuild_bench.py` | `regime_v033_benchmark_daily.csv` | 6,502 行；与 `trade_calendar` 双向差集为空 |
| 2 | `python paper_drafts/run_v033_ledger.py` | `regime_v033_arms_newcal.csv` 等 | 六臂净损益差：79.011 / 65.082 / 94.760 / 83.147 / 73.490 / 104.859 |
| 3 | `python paper_drafts/run_v034_candidates.py` | `regime_v034_paper_table.csv` | 十候选净损益差与论文表一致 |

第 2 步含旧日历保真门：同一套代码在旧基准上必须跑出 78.958744 / 147.5561 / −68.597（与冻结值误差 ≤1e-6）。若这一门不过，说明数据或代码版本不对，后面的结果不必看。

---

## 4. 全量复现路径

按版本顺序，每一步都对应一个预登记 TOML 与一个产物文件。**先读 TOML，再跑脚本**——判定门槛、分位数、票数都在 TOML 里，脚本只执行。

### 4.1 数据层

| 版本 | 脚本 | 预登记 | 产物 |
|---|---|---|---|
| v0.04 | `src/regime_check/build_v04_labels.py` | `config/regime_*` | `regime_daily_labels_v04.csv`（3,339 行） |
| v0.05 | `build_v05_benchmark_realwind.py` | — | `regime_v05_benchmark_daily.csv`（**旧版 6,483 行，仅作保真对照**） |
| v0.33 | `paper_drafts/run_v033_rebuild_bench.py` | `regime_bench_rebuild_v0.33.toml` | `regime_v033_benchmark_daily.csv`（6,502 行） |

### 4.2 触发与告警层

| 版本 | 脚本 | 内容 |
|---|---|---|
| v0.12 | `build_v012_trigger_policy.py` | 触发规则候选网格 |
| v0.13 | `build_v013_trigger_recall.py` | 召回与提前量 |
| v0.15 | `build_v015_light_patch.py` | 规则微调（选定 S3） |
| v0.16 | `build_v016_governed_pnl.py` | 告警状态机（选定 B10）与治理损益 |

### 4.3 判定与账本

| 版本 | 脚本 | 内容 |
|---|---|---|
| v0.17 | `build_v017_topology_increment.py` | 拓扑特征的条件判别增量 |
| v0.18 | `build_v018_sealed_validation.py` | **封存验证开箱**（留出验证报告的全部表格） |
| v0.19 | `build_v019_c1_product_completion.py` | 六格析因网格 |
| v0.21 | `build_v021_rolling_clock.py` | 滚动判定钟 R |

### 4.4 数据修正与候选重算

| 版本 | 脚本 | 内容 |
|---|---|---|
| v0.30 | `paper_drafts/run_v030_ingest.py` / `run_v030_a31_features.py` | a 腿换库 |
| v0.31 | `paper_drafts/run_v031_a31_tuned.py` | a31 调参网格 |
| v0.32 | `paper_drafts/run_v032_ingest.py` / `run_v032_a31_single.py` / `run_v032_judge.py` / `run_v032_audit.py` | a 腿单一源与六项审计 |
| v0.33 | `paper_drafts/run_v033_*.py`（5 支） | 基准重建、S3 对比、账本、自查、逐事件对账 |
| v0.34 | `paper_drafts/run_v034_candidates.py` | 十候选重算与四道门 |

### 4.5 拓扑专项（未进论文主结果）

`run_crowding_topo_v025.py`、`run_v026_dispersion_confirm.py` 等，对应 v0.25 / v0.26 四条否定结论。**未随日历修正重算**，其绝对值仍是旧日历口径，不能与新数字混用。

---

## 5. 校验点（复现是否成功）

**完整校验表见 `EXPECTED_OUTPUTS.csv`（64 项）**：每一行给出指标、论文展示值、精确期望值、口径、生成脚本、产物文件、产物字段与容差。下表只是其中最常用的十四项。

随包 `outputs/` 已附校验与最小复现所需的全部关键产物（约 7 MB，19 个文件）：**校验类**——`regime_v034_paper_table.csv`（十候选主表）、`regime_v033_arms_newcal.csv`／`_oldcal.csv`（新旧日历六臂）、`regime_v033_benchmark_daily.csv`（6,502 日基准）、`regime_v033_benchmark_audit.json`、`regime_v05_crisis_events.csv`、`regime_v018_summary.json`；**中间输入类**——`regime_v05_benchmark_daily.csv`（旧基准，保真门用）、`regime_v07_split_wide.csv`、`regime_v012_trigger_event_timing.csv`、`regime_v016_governed_pnl_summary.csv`、`regime_v017_account_event_matrix.csv`、`regime_v017_manifest.json`、`regime_v021_baseline_summary.csv`、`regime_v015_lightpatch_false_alarm.csv`、`regime_v016_governed_pnl_false_alarm.csv`、`regime_daily_labels_v04.csv`。**不重跑任何脚本，也可以用校验类产物逐格核对 `EXPECTED_OUTPUTS.csv`；要重跑第 3 节的三步，用中间输入类作输入。** 其中 `_oldcal` 与 `regime_v05_benchmark_daily.csv`（旧基准）仅用于保真门，不得用于正式结论。

| 指标 | 期望值 | 出处 |
|---|---|---|
| 基准行数 | 6,502 | `regime_v033_benchmark_daily.csv` |
| 事件数 | 45 | `regime_v05_crisis_events.csv` |
| 识别、分档 | 45/45；24／7／14 | 论文表 5-1 |
| 告警日占比 | 23.5% | 同上 |
| 方案一净损益差 | +79.0（精确 79.011） | `regime_v034_paper_table.csv` |
| 方案二净损益差 | +104.9（精确 104.859） | 同上 |
| 方案一＋R | +114.8（精确 114.823） | 同上 |
| 方案二＋R | +140.7（精确 140.672） | 同上 |
| 消融 S3 无状态管理 | −5.3（精确 −5.269） | 同上 |
| R 独立增量 | +35.8（精确 35.812） | 同上 |
| C1 增量 | +25.8（精确 25.848） | 同上 |
| 旧日历保真（方案一） | 78.958744 | `regime_v033_arms_oldcal.csv` |
| 封存验证归因校验 | 61799f5cbf82a828 | `regime_v018_summary.json` |
| 封存验证误报校验 | fc0f817e5b39f053 | 同上 |

**四舍五入约定**：论文与报告中的数字均为精确值四舍五入到一位小数（个别分解项保留两位以闭合恒等式）。因此“事件侧＋误报段”与“净损益差合计”相加时可能出现 0.1 的尾差，这是展示精度而非计算错误。

---

## 6. 常见问题

**问：为什么 `regime_v05_benchmark_daily.csv` 有二份，行数还不一样？**
答：v0.05 那份是旧版（6,483 行，漏 19 个交易日），保留只为跑保真门。一切正式计算都用 v0.33 那份（6,502 行）。判别方法见 `DATA_MANIFEST.md` 5.2。

**问：为什么有的脚本读 `xy_replication_data.db::benchmark_daily`？**
答：那是 v0.17 之前的旧口径，该表也是 6,483 行的旧版。新脚本一律读 v0.33 的 CSV。若复现旧版本，需注意这一差异。

**问：19 个漏取日会改变结论吗？**
答：不改变。S3 告警段 118 段、撤销 117 次、切换 19 起、判型 10 起逐项不变；唯一需要改的数字是告警日占比 23.4% → 23.5% 与账本的两个分项。详见 `v033_bench_rebuild_report.md`。

**问：为什么 31 码面板只有 6,500 个可用收盘日，而基准有 6,502？**
答：两个原因。其一，Wind 行业面板自 2000-01-04 起，比基准晚 1 个交易日（1999-12-30），得 6,501 日；其二，2014 版新设的 7 个行业在 Wind 回溯序列中缺 2014-02-20，该日横截面不完整，可用完整日再减 1，得 6,500 日。见 `DATA_MANIFEST.md` 7.2。

**问：能只跑封存验证吗？**
答：可以。`build_v018_sealed_validation.py` 只依赖四份输入（触发层误报明细 `regime_v015_lightpatch_false_alarm.csv`、治理层误报明细 `regime_v016_governed_pnl_false_alarm.csv`、基准日线 `regime_v05_benchmark_daily.csv`、危机事件表 `regime_v05_crisis_events.csv`），不重算拓扑。四份输入均已随包放在 `03_可复现代码/outputs/`；跑出的结果应与 `02_留出验证报告/data/` 的四份冻结产物（归因表、误报表、事实表、汇总 JSON）逐字一致。

---

## 7. 产物命名规则

`regime_v<版本号>_<内容>.csv|json`，版本号与 `config/regime_*_v<版本号>.toml` 一一对应。报告类产物为 `v<版本号>_*_report.md|html`。**同名文件不得跨版本混用**——本项目曾因把旧日历产物当新产物引用而误报过数字，故所有修正版一律新起文件名，不覆盖旧文件。

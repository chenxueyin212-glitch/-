# 代码文件索引（CODE_INDEX）

**用途**：逐个说明 `03_可复现代码/` 下全部 **210 个 Python 脚本**各自是干什么的；**39 个预登记 TOML** 的逐项清单见 `04_支撑材料/预登记索引.md`（本文件第 6 节只讲使用要点）。先看这张表，再决定跑哪个；不需要通读代码。
**配套**：想看「这些代码是按什么研究顺序长出来的」读 `04_支撑材料/研究思路与代码脉络.md`；运行方法见 `REPRODUCE.md`；数据口径见 `DATA_MANIFEST.md`；数字校验见 `EXPECTED_OUTPUTS.csv`。

---

## 0. 怎么用这份索引

- 每个脚本一行：**文件名 | 作用 | 性质**。性质分四类：
  - **主链**——论文主结果的生成环节，复现必需；
  - **实验**——预登记实验（含否定结果），对应某个 `config/*.toml`；
  - **诊断**——只读分析、事后核查、审计，不影响任何冻结产物；
  - **报告/可视化**——把已有产物渲染成 HTML/PDF，不重新计算。
- 大部分脚本首行 docstring 写明预登记文件与红线；**先读 TOML 再跑脚本**。
- ⚠️ 有 **22 个脚本写死了开发机绝对路径**（`D:/WorkBuddy/2026-10-28-22-54-51/...`，多见于 `paper_drafts/` 的一次性诊断），换机器复现时需先改路径。主链脚本（`src/regime_check/` 与 `run_v033_*`、`run_v034_*`）均用相对路径，不受影响。
- 命名规律：`build_vNN_*` 生成第 vNN 版产物；`*_report.py` 只渲染报告；`verify_*`／`validate_*`／`audit_*` 为独立复核；`explore_*` 为探索性分析（非预登记主线）。

---

## 1. 核心库（src/ 根目录，10 个）

| 文件 | 作用 | 性质 |
|---|---|---|
| `src/__init__.py` | 工程包说明（A 股系统性风险预警：双参数持续同调研究工程） | — |
| `src/config.py` | 路径与研究参数加载（零第三方依赖，内置 tomllib） | 主链 |
| `src/labels.py` | 市场级危机标签与事件清单（冻结标签的实现） | 主链 |
| `src/evaluation.py` | 严格因果的检测器与评估器（交易日口径） | 主链 |
| `src/baselines.py` | Gate 1 普通风险基线（仅用当前右对齐窗口） | 实验 |
| `src/gate0_acceptance.py` | Gate 0 工程验收：固定面板、合成标签、日期 purge 与逐折切分 | 实验 |
| `src/run_gate1_development.py` | 运行 Gate 1 开发期 OOF 实验（2025 起测试集封存） | 实验 |
| `src/validate_gate1.py` | 独立复核 Gate 1 输出，不重训不改参 | 诊断 |
| `src/run_sliced_pilot.py` | 真实行业面板上的密度切片工程试点 | 实验 |
| `src/smoke_test.py` | 端到端最小验证：数据层＋因果自检＋评估层＋拓扑后端 | 主链 |

## 2. 数据与拓扑层（src/data、src/topology，3 个）

| 文件 | 作用 | 性质 |
|---|---|---|
| `src/data/pit_panel.py` | 从 tdx_central.db 构造严格 point-in-time 的行业面板与点云 | 主链 |
| `src/topology/features.py` | 持续同调特征计算内核的薄封装（拟合口径由本项目控制） | 主链 |
| `src/topology/__init__.py` | 拓扑特征层说明 | — |

---

## 3. 危机主链（src/regime_check/，66 个）——v0.03 至 v0.26 全链路

### 3.1 数据导入与基准（7 个）

| 文件 | 作用 | 性质 |
|---|---|---|
| `collect_wind_front.py` | 把单份 Wind 原始行情响应复制进 third_party/wind/ | 主链 |
| `import_wind_front.py` | 合并 Wind 881001.WI 前段响应为逐日 CSV | 主链 |
| `import_wind_extension.py` | 导入 Wind 881001.WI 2025-05-30 之后的延伸段 | 主链 |
| `build_v05_benchmark.py` | 构造 v0.05 分段基准与延伸标签日历 | 主链 |
| `build_v05_benchmark_realwind.py` | 用真实 881001.WI 重建 v0.05 基准（**旧版 6,483 行，仅保真对照**） | 主链 |
| `audit_benchmark_extension.py` | 只读审计：2025-05-30 牛熊分界是否为数据边界 | 诊断 |
| `build_v05_judgement_inputs.py` | 构造 v0.05 判定层输入（只出数据，不下结论） | 主链 |
| `verify_v05_judgement.py` | v0.05 判定层：在延伸样本上重判 14 条推测 | 实验 |
| `build_v05_report.py` | v0.05 判定报告与清单 | 报告 |
| `diagnose_v05_composition.py` | 事后诊断 v0.05 显著性激增的成因（描述性） | 诊断 |

### 3.2 标签、猜想与窗口敏感性（v0.02—v0.05，11 个）

| 文件 | 作用 | 性质 |
|---|---|---|
| `build_v03_summaries.py` | v0.03 阶段 1：分线短窗摘要 | 主链 |
| `verify_v03_split.py` | v0.03 阶段 2：w=10 分线 14 条推测重判 | 实验 |
| `build_v03_report.py` | v0.03 分线重判报告＋结论台账 | 报告 |
| `build_v04_labels.py` | v0.04：用真实 Wind 延伸牛熊标签（OPTION A） | 主链 |
| `verify_v04_extension.py` | v0.04：用延伸标签重跑 v0.03 判定网格 | 实验 |
| `build_v04_report.py` | v0.04 延伸报告＋结论台账 | 报告 |
| `build_window_grid_summaries.py` | v0.02 窗口尺度敏感性：窗口网格上重算逐日摘要 | 实验 |
| `verify_window_grid.py` | v0.02：裁决四个预登记窗口问题 J1—J4 | 实验 |
| `build_window_sensitivity_report.py` | v0.02 窗口敏感性报告渲染 | 报告 |
| `build_breadth_daily.py` | Stage B-0：逐日横截面宽度/成交额/涨跌停代理 | 诊断 |
| `build_regime_labels.py` | Stage B-2：猜想检验用逐日状态标签 | 实验 |

### 3.3 猜想核验与上下文导出（12 个）

| 文件 | 作用 | 性质 |
|---|---|---|
| `build_daily_ph_summaries.py` | Stage B-1：市场状态点云全日期逐日形状摘要 | 主链 |
| `verify_conjectures.py` | Stage B-3：14 条市场状态猜想对照逐日标签核验 | 实验 |
| `build_conjecture_check_report.py` | Stage B-4：猜想核验离线 HTML 报告 | 报告 |
| `export_crisis_context.py` | 只读导出危机样本 ±20 交易日上下文 | 诊断 |
| `export_crisis_context_all17.py` | 同上（全 17 事件版） | 诊断 |
| `export_crisis_context_all19.py` | 同上（全 19 事件版） | 诊断 |
| `export_crisis_context_v05.py` | v0.05 判定样本的 ±20 日上下文导出 | 诊断 |
| `export_crisis_context_v06_early.py` | v0.06 早期事件窗导出（只导出，不统计） | 诊断 |
| `export_crisis_context_v07.py` | v0.07 上下文导出（整合 v0.05 与 v0.06） | 诊断 |
| `build_crisis_context_report.py` | 危机上下文离线 HTML 报告 | 报告 |
| `build_crisis_context_report_all17.py` | 全 17 事件版上下文报告 | 报告 |
| `build_crisis_context_report_all19.py` | 全 19 事件版上下文报告 | 报告 |
| `build_crisis_context_report_v05.py` | v0.05 上下文中文报告 | 报告 |
| `build_crisis_context_report_v06_early.py` | v0.06 早期事件窗报告 | 报告 |
| `build_crisis_context_report_v07.py` | v0.07 整合版上下文报告 | 报告 |
| `export_state_breakdown.py` | 只读导出 v0.03 逐日状态标签 | 诊断 |

### 3.4 v0.06—v0.10：早期延伸、整合与分型（11 个）

| 文件 | 作用 | 性质 |
|---|---|---|
| `build_v06_early_summaries.py` | v0.06 早期历史描述性 TDA 延伸 | 实验 |
| `build_v07_integrated_wide.py` | 整合 v0.05 日历与 v0.06 早期描述为 v0.07 宽表 | 主链 |
| `validate_v07_integration.py` | 校验 v0.07 整合数据与报告载荷 | 诊断 |
| `build_v08_event_typology.py` | v0.08 危机事件拓扑画像分型（纯描述对账） | 实验 |
| `build_v08_typology_report.py` | v0.08 拓扑分型报告 | 报告 |
| `explore_v08_patterns.py` | v0.08 分型数据的探索性模式搜索 | 诊断 |
| `explore_v08_patterns_followup.py` | 后续：置换检验、非线性依赖、子聚类 | 诊断 |
| `explore_v08_fast_final.py` | 优化版 44 对置换＋快速 bootstrap | 诊断 |
| `explore_v08_correction_bootstrap.py` | 全 44 对置换＋多重校正、聚类稳定性 | 诊断 |
| `explore_v08_cross_and_nonlinear.py` | 金融特征交叉核对＋非线性拟合 | 诊断 |
| `explore_v08_fpca_leadlag_correction.py` | FPCA、领先滞后、全置换＋校正 | 诊断 |

### 3.5 v0.09—v0.11：日级检测、交互与反事实（6 个）

| 文件 | 作用 | 性质 |
|---|---|---|
| `build_v09_daylevel_detection.py` | v0.09 危机拓扑状态日级检测与实时分类（只读） | 实验 |
| `build_v09_daylevel_report.py` | v0.09 报告生成器 | 报告 |
| `build_v010_interaction_test.py` | v0.10 金融危机类型 × 拓扑响应交互检验 | 实验 |
| `build_v010_interaction_report.py` | v0.10 交互检验中文报告 | 报告 |
| `build_v011_counterfactual.py` | v0.11 四路径反事实损益（认沽权利金＋到期收益现金流化） | 实验 |
| `build_v011_counterfactual_report.py` | v0.11 反事实损益报告 | 报告 |

### 3.6 v0.12—v0.17：触发器、告警治理与产品链（12 个）

| 文件 | 作用 | 性质 |
|---|---|---|
| `build_v012_trigger_policy.py` | v0.12 触发层政策对比网格＋逐日判定与切换 | 实验 |
| `build_v012_trigger_report.py` | v0.12 触发政策对比报告 | 报告 |
| `build_v013_trigger_recall.py` | v0.13 召回优先高敏触发器研究（**选定 S3 的来源**） | 实验 |
| `build_v013_trigger_recall_report.py` | v0.13 离线中文报告 | 报告 |
| `build_v014_trigger_governance.py` | v0.14 误报治理：撤销（收复＋静默/纯静默）× 冷却（0/5/10/20）9 变体（**选定 B10 的来源**） | 实验 |
| `build_v014_governance_report.py` | v0.14 治理报告 | 报告 |
| `build_v015_light_patch.py` | v0.15 弱三中二最小补丁研究 | 实验 |
| `build_v015_lightpatch_report.py` | v0.15 补丁报告 | 报告 |
| `build_v016_governed_pnl.py` | v0.16 消音治理后触发器接回端到端损益账本（**B10 治理损益**） | 主链 |
| `build_v016_governed_pnl_report.py` | v0.16 账本报告 | 报告 |
| `build_v017_topology_increment.py` | v0.17 产品栈条件下的拓扑条件判别增量检验 | 实验 |
| `build_v017_topology_increment_report.py` | v0.17 增量报告 | 报告 |

### 3.7 v0.18—v0.24：封存验证、产品补全与候选（10 个）

| 文件 | 作用 | 性质 |
|---|---|---|
| `build_v018_sealed_validation.py` | v0.18 封存验证期开箱检验（**留出验证报告全部表格的来源**） | 主链 |
| `build_v019_c1_product_completion.py` | v0.19 C1 产品化补全：7/10 项确认 × 4/5/6 票析因网格（**主结果表来源**） | 主链 |
| `build_v020_asym_confirm.py` | v0.20 非对称类型确认（浅快单日/深慢两日）——否定封存 | 实验 |
| `build_v021_rolling_clock.py` | v0.21 滚动判定钟 R：每段告警各开 20 日观察期（baseline/rolling 双模式） | 实验 |
| `build_v022_netvalue.py` | v0.22 净值口径完整核算（回补 B、认沽、止损、类型修正） | 实验 |
| `build_v023_miss_ledger.py` | v0.23 45 事件漏保账（纯描述性重分类） | 诊断 |
| `build_v023_parallel_channel.py` | v0.23 分散式解体并行通道（PR30/corr30 分散态＋深回撤激活） | 实验 |
| `build_v024_topo_probe.py` | v0.24 拓扑分散签名探测臂 | 实验 |
| `build_v024b_topo_window.py` | v0.24b 拓扑探测臂 2 年滚动分位变体 | 实验 |
| `build_v022_netvalue.py` 的可视化见 paper_drafts/build_v022_visual.py | | |

---

## 4. 券商规则复现（src/phti_replication/，6 个）与兴业复现（src/xy_replication/，30 个）

### 4.1 PHTI 复现线（Baitinger & Flegel 2021 拓扑湍流指数）

| 文件 | 作用 | 性质 |
|---|---|---|
| `phti_pipeline.py` | A 股行业面板的因果 PHTI 指标流水线 | 实验 |
| `run_engineering_acceptance.py` | PHTI 复现工程验收（v0.2, p=2） | 诊断 |
| `build_phti_close_reading.py` | Baitinger & Flegel (2021) 精读报告 | 报告 |
| `build_phti_replication_status.py` | A 股 PHTI 复现设计＋工程验收报告 | 报告 |
| `section33_ashare_check.py` | 该文 3.3 节在 A 股数据上的探索性核验 | 诊断 |
| `wasserstein_worked_example.py` | 两张相邻日持久图之间 W_p 距离的具体算例 | 诊断 |

### 4.2 兴业《捕捉市场的形状》复现线

| 文件 | 作用 | 性质 |
|---|---|---|
| `__init__.py` | 兴业复现管线说明 | — |
| `topology.py` | 相关网络 VR 持续同调（与兴业原报告图 12 核对公式） | 主链 |
| `compute_features.py` | 逐日申万二级相关网络 H2 特征（支持断点续跑） | 主链 |
| `compute_corrected_features.py` | 用修正版 SW2014＋SW2021 重算相关网络特征 | 主链 |
| `validate_corrected_features.py` | 独立核验修正版行业输入与图 13/14 量级差异 | 诊断 |
| `backtest.py` | 低 H2 择时回测、普通变量对照、信号明细与发布后表现 | 实验 |
| `validate_replication.py` | 独立复核兴业复现（日期、信号、收益、仓位、汇总） | 诊断 |
| `self_test.py` | 数学内核合成样例与跨库核验 | 主链 |
| `fetch_sw2_data.py` | 下载申万二级行业与申万 A 指代理基准（只读快照） | 主链 |
| `fetch_sw2_legacy.py` | 补采 2014 版停用二级序列（只追加） | 主链 |
| `fetch_sw2014_corrected.py` | 独立采集修正版 SW2014 二级指数 | 主链 |
| `import_wind_all_a_daily.py` | 导入 Wind 881001.WI 日线快照 | 主链 |
| `import_ifind_table_supplement.py` | 导入 iFind 原始表格的逐日补充行情 | 主链 |
| `import_westock_supplement.py` | 导入 WeStock 原始返回补充库 | 主链 |
| `ic_diagnostics.py` | 稀疏低频择时信号的 IC 诊断 | 诊断 |
| `signal_trigger_ic_matrix.py` | 信号何时触发的补充只读诊断 | 诊断 |
| `cluster_last_day_ic.py` | 每个 k=1 事件簇最后一日的评分诊断 | 诊断 |
| `crisis_onset_tda_study.py` | 高 H2 孔洞数是否领先危机（只读研究） | 诊断 |
| `event_and_adaptive_threshold_study.py` | 事件阈值与自适应阈值两项后续只读诊断 | 诊断 |
| `qualitative_parameter_study.py` | 定性关系研究＋预登记探索性参数网格 | 实验 |
| `pit_sensitivity.py` | ⚠️ 有代码映射缺陷的历史实验，仅留作审计，**不是有效复现** | 诊断 |
| `compare_landscape_figures.py` | 对照兴业图 12/13 与本地持久景观形态（不重算） | 诊断 |
| `export_example.py` | 导出 2024-12-31 相关网络持久图与兴业原图视觉核对 | 诊断 |
| `build_report.py` | 由已审计 CSV/JSON 生成兴业复现 HTML | 报告 |
| `build_standalone_report.py` | 把复现报告打包为单文件 HTML | 报告 |
| `build_cluster_last_day_report.py` | 簇末日 IC 研究报告 | 报告 |
| `build_crisis_onset_tda_report.py` | 高 N／危机起点研究报告 | 报告 |
| `build_event_adaptive_report.py` | 两项后续问题的报告 | 报告 |
| `build_ic_method_report.py` | IC 诊断方法说明报告 | 报告 |

---

## 5. 后期实验与诊断（paper_drafts/，86 个）

### 5.1 v0.25—v0.26：抱团拓扑与分户型通道（20 个）

| 文件 | 作用 | 性质 |
|---|---|---|
| `run_crowding_topo_v025.py` | v0.25 抱团拓扑四法主实验（M1—M4） | 实验 |
| `run_v025_cases.py` | v0.25 案例投影（2026 三段、2021 抱团瓦解、2024 微盘危机） | 诊断 |
| `run_v025_placebo.py` | v0.25 时间安慰剂（同年度非危机日重跑） | 实验 |
| `build_v025_report.py` | v0.25 实验报告 HTML | 报告 |
| `crowding_topo_lib.py` | v0.25 公共库：G 主导连通分支寿命等工具 | 主链 |
| `crowding_breadth_test.py` | 拥挤度 vs 宽度差（结构性下跌的操作化定义） | 诊断 |
| `crowding_full_history.py` | 全史成交额集中度（拥挤度） | 诊断 |
| `crowding_rolling_pct.py` | 拥挤度滚动分位口径＋领先性检验 | 诊断 |
| `topo_crowding_unwind.py` | 拓扑量能否刻画抱团瓦解（三层检验） | 实验 |
| `topo_crowding_control.py` | 控制检验：H0 死亡尺度是否只是前期涨幅的代理 | 诊断 |
| `disperse_vs_v025.py` | v0.25 与分散签名的对照工具（含窗口与行业收益加载） | 诊断 |
| `pr_mst_robustness.py` | PR 与 MST 总权重的稳健性对照（W=20/40/60） | 诊断 |
| `global_mst_dispersion.py` | 19 行业相关距离点云的 MST 总权重与平均边长 | 诊断 |
| `v025_2026_reach.py` | v0.25 四法在 2026 L2/L3 上能做到什么地步 | 诊断 |
| `v025_2026_timecost.py` | m2 单侧 p 值是否分布退化＋20 日观察点代价 | 诊断 |
| `v025_horizon_power.py` | 训练期 31 段 m1 在第 5/10/20 日的判别力（AUC） | 诊断 |
| `run_v026_dispersion_confirm.py` | v0.26 分户型下跌非拓扑确认通道（预登记，含两处修正说明） | 实验 |
| `v026_gate_feasibility.py` | 状态门可行性体检（只用已冻结的 corr20） | 诊断 |
| `v026_state_frequency.py` | 低相关状态出现频率（非预登记补充） | 诊断 |
| `effective_dimension.py` | 有效维度 PR/ER、平均两两相关、第一主成分占比 | 诊断 |

### 5.2 v0.28—v0.34：数据修正与候选重算（21 个）

| 文件 | 作用 | 性质 |
|---|---|---|
| `run_v028_ab_compare.py` | v0.28 B/A 对照（756 日滚动分位真实口径） | 实验 |
| `run_v028_quantile_map.py` | v0.28 方案 B 可行性：a27→a16 经验分位映射外推 | 实验 |
| `run_v029_b_unified.py` | v0.29 b 腿统一代码体系重算（2021 版二级、W=10） | 实验 |
| `run_v029_votes.py` | v0.29 判定对账：新 b 腿特征＋参数网格 | 实验 |
| `run_v030_ingest.py` | v0.30 阶段 1：Wind 一级行业回溯落地＋准入 | 主链 |
| `run_v030_a31_features.py` | v0.30 阶段 2：a 腿 31 行业统一坐标特征重算 | 主链 |
| `run_v030_compare.py` | v0.30 阶段 3：a16 与 a31 判定对账 | 实验 |
| `run_v031_a31_tuned.py` | v0.31 a31 调参网格与完整判定对账 | 实验 |
| `run_v032_ingest.py` | v0.32 阶段 1：16 个老代码 Wind 取数＋准入（单一源第一步） | 主链 |
| `run_v032_a31_single.py` | v0.32 阶段 2：p31 单一源特征重算＋p16 对账 | 主链 |
| `run_v032_audit.py` | v0.32 阶段 3：采样审计（六项） | 诊断 |
| `run_v032_judge.py` | v0.32 单一源后的判定机对账与分层参数搜索 | 实验 |
| `run_v033_rebuild_bench.py` | v0.33 基准日历重建（6,502 日，**主结果数据基础**） | 主链 |
| `run_v033_ledger.py` | v0.33 账本与七票重算（只换日历，其余逐字复用 v0.19） | 主链 |
| `run_v033_s3_compare.py` | v0.33 S3/B10 新旧日历逐日并排对照 | 诊断 |
| `run_v033_selfaudit.py` | v0.33 自查：独立第二实现重算 S3/B10 并逐日比对 | 诊断 |
| `run_v033_event_recon.py` | v0.33 自查：账本逐事件全字段对账 | 诊断 |
| `run_v033_handcheck.py` | v0.33 自查：独立重写仓位模拟手算 p1/p3/p4 | 诊断 |
| `run_v034_candidates.py` | v0.34 十候选在新日历上的重算（**论文主表候选数字来源**） | 主链 |
| `verify_event_pnl.py` | 终审复算：v0.19 引擎语义复算事件 1/119 的 P4 与 CSV 对账 | 诊断 |
| `latest_check_20261120.py` | 截至 2026-11-20 的成色检验（价格层） | 诊断 |

### 5.3 危机轮次、形态与结构性下跌（24 个）

| 文件 | 作用 | 性质 |
|---|---|---|
| `crisis_rounds_manual.py` | 45 标签段按「一轮下跌＋收复」合并为叙事层危机轮次 | 诊断 |
| `crisis_rounds_final.py` | 叙事层危机轮次定稿：深度、时长、并入段数 | 诊断 |
| `crisis_episode_merge.py` | 从高点回撤超阈值起一轮、收复前高结束的合并工具 | 诊断 |
| `crisis_episode_rebound.py` | 45 标签段合并为「真正的一次危机」 | 诊断 |
| `crisis_episode_zigzag.py` | ZigZag 分解：下行摆动吃进几个标签段（几段合一段） | 诊断 |
| `crisis_stress_episodes.py` | 「真正危机」=指数连续处于 250 日高点回撤超阈值的时段 | 诊断 |
| `event_definition_audit.py` | 核查 45 事件是否同一规则产生（2000/2013 年的反例检查） | 诊断 |
| `event_window_shape_check.py` | 45 事件窗是否等价于「峰→谷」（2026 窗口对比依据） | 诊断 |
| `round_shape_summary.py` | 轮级聚合＋形态占比（2015 后是否更结构性） | 诊断 |
| `round_style_divergence.py` | 11 轮危机的宽基 vs 小盘/成长背离 | 诊断 |
| `structural_channel_local.py` | 结构性下跌第二通道（仅本地数据可算部分） | 诊断 |
| `structural_channel_segments.py` | 结构性通道段内统计（绝对水平口径） | 诊断 |
| `structural_decline_check.py` | 2025—2026 前 5% 成交额集中度等结构性下跌迹象 | 诊断 |
| `structural_vs_broad_2015.py` | 2015 前后危机是全面熊还是结构性/抱团瓦解 | 诊断 |
| `three_unwind_types.py` | 19 行业事前 250 日收益、危机 20 日收益与窗内相关 | 诊断 |
| `three_unwind_2026_exclusive.py` | 2026 两段三型签名＋三族互斥性检验 | 诊断 |
| `shallow_fast_rotation_topo.py` | 浅快型/轮动型的拓扑画像（描述性） | 诊断 |
| `rotation_by_industry.py` | 危机窗内 28 行业收益分化（轮动判据） | 诊断 |
| `rotation_persistence.py` | 危机中新领涨在危机后是否仍领涨 | 诊断 |
| `pre_crisis_leadership.py` | 三次危机积累段的领涨板块结构对照 | 诊断 |
| `quintile_reversal.py` | 危机前 250 日涨幅五分组的危机中跌幅 | 诊断 |
| `margin_deleverage_rank.py` | 两融去杠杆历史排名（描述性，不接产品） | 诊断 |
| `s3_yearly_census.py` | S3 裸触发与 S3+B10 告警状态逐年普查 | 诊断 |
| `false_activation_census.py` | 误动手普查：误报段上确认过门槛、实际切换的日子 | 诊断 |

### 5.4 2026 年诊断与全球对照（12 个）

| 文件 | 作用 | 性质 |
|---|---|---|
| `label_runs_2026.py` | 用 v0.05 原构造复算 2026 的标签连续段 | 诊断 |
| `pre_alert_2026.py` | 2026-05-11 宽基见顶前触发器响过没有、确认门差几票 | 诊断 |
| `why_2026_no_cut.py` | 2026 未切换的七票指标中位数区间对照（卡死诊断） | 诊断 |
| `topo_projection_2026.py` | 2026 危机段向 v0.08 拓扑两簇的样本外投影（描述性） | 诊断 |
| `topo_window_sensitivity_2026.py` | 2026 各段投影到「状态扩张/相关重构」轴的窗口敏感性 | 诊断 |
| `two_axis_projection_2026.py` | 两轴同时投影 2026（深慢/浅快轴＋拓扑两簇轴） | 诊断 |
| `ai_chain_proxy.py` | 2026 AI 硬件链事件的本地代理（科创50/创业板指 vs 万得全A） | 诊断 |
| `latest_check_20261120.py` | （同 5.2）成色检验 | 诊断 |
| `post2020_alarm_coverage.py` | 2020 后告警但不动窗口 × 危机覆盖双向对账 | 诊断 |
| `post2020_topology_commonality.py` | 2020 后危机前后拓扑特征共性普查（描述性） | 诊断 |
| `global_linkage.py` | 2025 以来 A 股与海外相关性是否显著抬升 | 诊断 |
| `us2000_path.py` | ZigZag 转折点提取工具（美国 2000 年路径用） | 诊断 |
| `us_episodes_989900.py` | 美股 1998—2000 危机段提取（峰谷规则） | 诊断 |

### 5.5 可视化与工具（9 个）

| 文件 | 作用 | 性质 |
|---|---|---|
| `build_action_overview.py` | 动作总览图：价格＋45 危机带＋两方案动手节点（单 HTML） | 报告 |
| `build_ch5_visual.py` | 第五章可视化：11 项拓扑特征＋S3+B10 告警＋预案应对点 | 报告 |
| `build_v022_visual.py` | v0.22 净值九臂可视化（echarts 内联单 HTML） | 报告 |
| `topo_param_scan.py` | 拓扑参数空间全扫描（v0.07 宽表全部拓扑量） | 诊断 |
| `topo_param_year_control.py` | 对年度控制变量回归取残差后的 Pearson（参数稳健性） | 诊断 |
| `intra_inter_correlation.py` | 行业内 vs 行业间相关（结构性下跌第三块拼图） | 诊断 |
| `intra_inter_samelevel.py` | 同上（同层级口径） | 诊断 |
| `intra_inter_2021_test.py` | 2021 后子样本内/间相关区分度的决定性检验 | 诊断 |
| `_extract_eq.py` | 一次性提取事件窗口个股收盘存 pickle（工具） | 主链 |

---

## 6. 预登记 TOML（config/，39 个）

全部清单、版本、标题与登记时间见 `04_支撑材料/预登记索引.md`。要点：
- 文件名与产物名一一对应（`regime_*_vNN.toml` ↔ `regime_vNN_*.csv`）；
- 判定门槛、分位数、票数、红线都写在 TOML 里，**脚本只执行**；
- 少数 TOML 无标题字段（如 `gate1.toml`、`study.toml`、`regime_window_sensitivity_v0.2.toml` 等），以文件头注释为准。

---

## 7. 校验与中间产物（outputs/，19 个）

**校验类**（核对 `EXPECTED_OUTPUTS.csv` 用）：

| 文件 | 作用 |
|---|---|
| `regime_v033_benchmark_daily.csv` | 6,502 日基准（主结果数据基础） |
| `regime_v033_benchmark_audit.json` | 基准重建七道门审计记录 |
| `regime_v033_arms_newcal.csv` | 新日历六臂完整指标 |
| `regime_v033_arms_oldcal.csv` | 旧日历六臂（**仅保真门用，不得用于正式结论**） |
| `regime_v033_ledger_summary.csv` | v0.33 账本汇总 |
| `regime_v034_paper_table.csv` | 十候选主表（论文 5.4 各表数字来源） |
| `regime_v034_cand_compare.csv` | 十候选增量与排序对照 |
| `regime_v05_crisis_events.csv` | 45 个冻结危机事件表 |
| `regime_v018_summary.json` | 封存验证汇总（含归因/误报校验哈希） |

**中间输入类**（重跑 REPRODUCE 第 3 节三步与封存验证的直接输入）：

| 文件 | 作用 |
|---|---|
| `regime_v05_benchmark_daily.csv` | 旧版基准 6,483 行（**仅保真门用**） |
| `regime_daily_labels_v04.csv` | 逐日后段标签 3,339 行 |
| `regime_v07_split_wide.csv` | 两套点云逐日宽表（判定层输入） |
| `regime_v012_trigger_event_timing.csv` | 45 事件触发时点表 |
| `regime_v015_lightpatch_false_alarm.csv` | 触发层误报明细（封存验证输入） |
| `regime_v016_governed_pnl_false_alarm.csv` | 治理层误报明细（封存验证输入） |
| `regime_v016_governed_pnl_summary.csv` | 治理损益汇总 |
| `regime_v017_account_event_matrix.csv` ／ `regime_v017_manifest.json` | 事件矩阵与清单（账本重算输入） |
| `regime_v021_baseline_summary.csv` | v0.21 基线臂汇总（候选重算对照） |

**不重跑任何脚本即可用校验类产物逐格核对 `EXPECTED_OUTPUTS.csv`（64 项）；中间输入类凑齐后可直接跑最小复现三步。**

---

*本索引只描述文件用途，不含新实验结论。若某脚本 docstring 与本索引表述有出入，以脚本首部 docstring 与对应预登记 TOML 为准。*

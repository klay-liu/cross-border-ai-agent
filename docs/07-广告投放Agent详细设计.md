# 广告投放 Agent 详细设计

**版本**: v1.0
**日期**: 2026-02-26
**优先级**: P2 — Phase 2

---

## 一、Agent 定位

### 1.1 核心使命

将 Amazon PPC 广告从「人工调价凭感觉」转变为「数据驱动自动优化」：

```
传统广告管理:
手动创建广告 → 凭经验出价 → 每周看一次报表 → 手动调价 → 预算浪费

Agent 广告管理:
自动架构广告 → 公式化出价 → 每日自动分析 → 智能调价 → 负词管理 → 预算最优配置
```

### 1.2 核心能力矩阵

| 能力 | 说明 | 数据源 |
|------|------|--------|
| **广告架构设计** | 自动创建 Exact/Phrase/Broad 三组广告结构 | Amazon Advertising API |
| **智能出价** | 基于 ACOS/CVR 公式化计算最优出价 | 广告报表数据 |
| **搜索词分析** | 挖掘高转化搜索词、识别无效流量 | Search Term Report |
| **负关键词管理** | 自动添加负关键词，杜绝预算浪费 | 搜索词报表 + 规则引擎 |
| **预算分配** | 80/20 法则分配预算到成熟词和探索词 | 历史表现数据 |
| **竞价情报** | 监控关键词竞价变化趋势 | Bid Landscape 数据 |

---

## 二、广告架构设计

### 2.1 三层广告组架构

```
┌─────────────────────────────────────────────────────────┐
│                    Campaign (品类级别)                     │
│              例: "Spring Replacement - US"                │
│                                                         │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐  │
│  │  Ad Group 1   │ │  Ad Group 2   │ │  Ad Group 3   │  │
│  │  Exact Match  │ │ Phrase Match  │ │  Broad Match  │  │
│  │               │ │               │ │               │  │
│  │ 精准关键词     │ │ 词组关键词     │ │ 广泛关键词     │  │
│  │ 高转化+控成本  │ │ 流量拓展      │ │ 新词发现       │  │
│  │               │ │               │ │               │  │
│  │ 预算占比: 50%  │ │ 预算占比: 30% │ │ 预算占比: 20% │  │
│  │ 目标ACOS: 20% │ │ 目标ACOS: 25%│ │ 目标ACOS: 35%│  │
│  └───────────────┘ └───────────────┘ └───────────────┘  │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │              Auto Campaign (自动投放)               │  │
│  │    用于发现新关键词，预算占比: 10% (从Broad中分出)   │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 2.2 关键词流转机制

```
Auto/Broad 发现新词
    │
    ▼
┌─────────────────────────┐
│ 搜索词报表分析            │
│ 每日自动提取新搜索词      │
└───────────┬─────────────┘
            │
    ┌───────┴───────┐
    │               │
    ▼               ▼
 转化 ≥ 2次     转化 = 0 且
 ACOS < 30%     点击 ≥ 15次
    │               │
    ▼               ▼
┌─────────┐   ┌─────────┐
│ 提升为   │   │ 添加为   │
│ Exact   │   │ 负关键词  │
│ 关键词   │   │ (Broad组)│
└─────────┘   └─────────┘
```

---

## 三、智能出价系统

### 3.1 核心出价公式

```
┌─────────────────────────────────────────────────┐
│                                                 │
│   max_cpc = selling_price × target_acos × cvr   │
│                                                 │
│   示例:                                          │
│   售价 $8.99 × 目标ACOS 25% × 转化率 12%        │
│   = $8.99 × 0.25 × 0.12                        │
│   = $0.27 (最高每次点击出价)                     │
│                                                 │
└─────────────────────────────────────────────────┘
```

### 3.2 出价调整规则

```python
BID_ADJUSTMENT_RULES = {
    "increase_bid": {
        # 加价条件: 表现好但曝光不足
        "conditions": {
            "acos": "< target_acos * 0.8",     # ACOS 远低于目标
            "impressions_7d": "< 100",          # 但曝光不足
            "ctr": "> 0.3%",                    # 点击率正常
        },
        "action": "bid * 1.15",                 # 加价 15%
        "max_increase_per_day": 0.20,           # 单日最多加 $0.20
    },
    "decrease_bid": {
        # 降价条件: ACOS 超标
        "conditions": {
            "acos": "> target_acos * 1.3",      # ACOS 超标 30%+
            "clicks_7d": ">= 10",               # 有足够数据
        },
        "action": "bid * 0.85",                 # 降价 15%
        "min_bid": 0.10,                        # 最低出价 $0.10
    },
    "pause_keyword": {
        # 暂停条件: 持续亏损
        "conditions": {
            "acos": "> target_acos * 2.0",      # ACOS 超标 2倍
            "clicks_14d": ">= 20",              # 14天点击 ≥ 20
            "conversions_14d": "<= 1",           # 几乎无转化
        },
        "action": "pause",
    },
    "reactivate_keyword": {
        # 重新激活: 暂停超过30天的词，重新测试
        "conditions": {
            "paused_days": "> 30",
            "keyword_relevance": "high",
        },
        "action": "reactivate_with_min_bid",
    }
}
```

### 3.3 时段竞价策略

```python
DAYPARTING_STRATEGY = {
    # 美国站时段调整 (EST)
    "peak_hours": {
        "time_range": "18:00-23:00",    # 晚间购物高峰
        "bid_multiplier": 1.20,          # 加价 20%
    },
    "normal_hours": {
        "time_range": "08:00-18:00",    # 工作时间
        "bid_multiplier": 1.00,          # 标准出价
    },
    "off_peak": {
        "time_range": "23:00-08:00",    # 深夜
        "bid_multiplier": 0.70,          # 降价 30%
    },
    # 周末调整
    "weekend_multiplier": 1.10,          # 周末整体加 10%
}
```

---

## 四、搜索词分析引擎

### 4.1 搜索词分类与处理

```python
SEARCH_TERM_RULES = {
    "promote_to_exact": {
        # 晋升为精准关键词
        "min_conversions": 2,
        "max_acos": 0.30,
        "min_clicks": 5,
        "action": "添加到 Exact Ad Group，初始出价 = 历史CPC * 1.1"
    },
    "add_negative_exact": {
        # 添加精准否定
        "min_clicks": 15,
        "conversions": 0,
        "action": "添加到触发广告组的精准否定词"
    },
    "add_negative_phrase": {
        # 添加词组否定（识别无关词根）
        "pattern": "检测到与产品完全无关的词根",
        "examples": ["recipe", "how to", "DIY", "free"],
        "action": "添加到 Campaign 级别的词组否定"
    },
    "monitor": {
        # 继续观察
        "clicks_range": "5-14",
        "conversions": 0,
        "action": "标记观察，下周复查"
    }
}
```

### 4.2 搜索词分析 Prompt

```
分析以下 Amazon PPC 搜索词报告，给出优化建议。

产品: {product_name}
目标 ACOS: {target_acos}%
当前周期: 过去 7 天

搜索词数据:
{search_term_data}

请完成以下分析:

1. **高价值词**: 转化 ≥2 且 ACOS < 目标 → 建议提升为 Exact 关键词
2. **无效词**: 点击 ≥15 且转化 = 0 → 建议添加为负关键词
3. **潜力词**: 点击 5-14 且有转化迹象 → 建议观察或小幅加价
4. **异常词**: 与产品无关的搜索词 → 分析流量来源，建议否定
5. **趋势词**: 近期搜索量明显上升的词 → 评估是否值得加大投放

输出 JSON 格式，包含每个词的具体操作建议和预期影响。
```

---

## 五、关键规则与约束

### 5.1 核心 KPI 红线

```python
KPI_THRESHOLDS = {
    "target_acos": 0.25,             # 目标 ACOS ≤ 25%
    "max_acos_hard_limit": 0.40,     # 硬性上限 40%（超过立即暂停）
    "min_ctr": 0.003,                # 最低点击率 0.3%
    "min_cvr": 0.08,                 # 最低转化率 8%
    "budget_split": {
        "proven_keywords": 0.80,     # 80% 预算给已验证关键词
        "discovery": 0.20,           # 20% 预算给探索性投放
    },
    "daily_budget_cap": 50.00,       # 单日预算上限 $50
    "monthly_budget_cap": 1000.00,   # 月度预算上限 $1000
}
```

### 5.2 安全护栏

```python
SAFETY_GUARDRAILS = {
    "max_bid_change_per_day": 0.30,      # 单日最大出价变动 $0.30
    "max_bid_change_pct": 0.25,          # 单日最大出价变动 25%
    "min_data_threshold": {
        "clicks": 10,                     # 至少10次点击才做调整
        "days": 7,                        # 至少7天数据才做判断
    },
    "new_campaign_warmup_days": 14,       # 新广告14天预热期不做大调整
    "max_keywords_per_ad_group": 50,      # 每个广告组最多50个词
    "daily_negative_keyword_limit": 20,   # 每日最多添加20个负词
}
```

---

## 六、工作流程（每日自动优化）

```
每日 06:00 AM (EST) 自动触发
    │
    ▼
┌─────────────────────────────────────┐
│ Step 1: 数据采集                     │
│ 拉取昨日广告报表                     │
│ (Impressions/Clicks/Spend/Sales)    │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Step 2: KPI 计算                    │
│ 计算每个关键词的 ACOS/CTR/CVR       │
│ 与目标值对比，标记异常               │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Step 3: 搜索词分析                   │
│ 识别高价值词 → 晋升 Exact           │
│ 识别无效词 → 添加否定               │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Step 4: 出价调整                    │
│ 应用出价公式，生成调整建议           │
│ 遵守安全护栏限制                     │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Step 5: 预算再分配                   │
│ 80% → 高 ROI 关键词                │
│ 20% → 探索性投放                    │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Step 6: 执行 + 报告                 │
│ 自动执行调整（低风险）              │
│ 生成日报推送飞书                     │
│ 高风险操作 → 人工审核               │
└─────────────────────────────────────┘
```

---

## 七、数据模型

### 7.1 广告关键词记录

```python
class AdKeyword:
    keyword_id: str               # 关键词ID
    campaign_id: str              # 广告活动ID
    ad_group_id: str              # 广告组ID
    keyword_text: str             # 关键词文本
    match_type: str               # 匹配类型(exact/phrase/broad)
    status: str                   # 状态(active/paused/archived)
    current_bid: float            # 当前出价
    impressions_7d: int           # 7天曝光
    clicks_7d: int                # 7天点击
    spend_7d: float               # 7天花费
    sales_7d: float               # 7天销售额
    orders_7d: int                # 7天订单数
    acos_7d: float                # 7天ACOS
    ctr_7d: float                 # 7天CTR
    cvr_7d: float                 # 7天CVR
    bid_history: list             # 出价调整历史
    promoted_from: str            # 晋升来源(auto/broad/phrase)
    created_at: datetime          # 创建时间
    last_adjusted_at: datetime    # 最后调整时间
```

### 7.2 广告日报

```python
class AdDailyReport:
    report_date: date             # 报告日期
    campaign_id: str              # 广告活动ID
    total_spend: float            # 总花费
    total_sales: float            # 总销售额
    total_orders: int             # 总订单数
    overall_acos: float           # 整体ACOS
    overall_ctr: float            # 整体CTR
    overall_cvr: float            # 整体CVR
    keywords_adjusted: int        # 调整的关键词数
    negatives_added: int          # 新增负关键词数
    keywords_promoted: int        # 晋升的关键词数
    keywords_paused: int          # 暂停的关键词数
    budget_utilization: float     # 预算使用率
    top_performers: list          # Top 5 高效关键词
    worst_performers: list        # Top 5 低效关键词
    recommendations: list         # AI 建议列表
```

---

## 八、成本控制

| 环节 | LLM 调用 | 预估 Token | 月度成本 |
|------|---------|-----------|---------|
| 搜索词分析 (每日) | Haiku ×1/天 | ~5K/天 | ~$0.45 |
| 出价建议生成 (每日) | Haiku ×1/天 | ~3K/天 | ~$0.27 |
| 周度深度分析 | Sonnet ×1/周 | ~8K/周 | ~$0.96 |
| 新广告架构设计 (按需) | Sonnet ×2/月 | ~10K/次 | ~$0.60 |
| **月度合计** | | | **~$2.28** |

---

## 九、迭代路线

| 版本 | 能力 | 阶段 |
|------|------|------|
| v0.1 | 广告数据采集 + 基础 ACOS 监控 + 日报 | Phase 2 M1 |
| v0.2 | + 出价公式自动调整 + 搜索词分析 | Phase 2 M2 |
| v0.3 | + 负关键词管理 + 关键词晋升机制 | Phase 2 M3 |
| v1.0 | + 预算自动分配 + 时段竞价 + 完整报表 | Phase 2 M4 |
| v2.0 | + 竞价情报 + 广告与库存联动 + 多站点 | Phase 3 |

---

*本文档定义了广告投放 Agent 的完整设计，代码实现见 `ai-agent-prototype/src/agents/ad_optimizer.py`*

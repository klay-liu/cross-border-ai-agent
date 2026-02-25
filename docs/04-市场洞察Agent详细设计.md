# 市场洞察 Agent 详细设计

**版本**: v1.0
**日期**: 2026-02-25
**优先级**: P0 — Phase 1 核心模块

---

## 一、Agent 定位

### 1.1 核心使命

实时感知市场脉搏，将碎片化的市场信号转化为可执行的决策建议：

```
传统市场调研:
偶尔看看竞品 → 感觉市场变了 → 已经晚了

Agent 市场洞察:
持续监控 → 实时感知变化 → 自动研判 → 即时告警 → 提前行动
```

### 1.2 核心能力矩阵

| 能力 | 说明 | 数据源 |
|------|------|--------|
| **竞品追踪** | 实时追踪目标竞品的价格、库存、评论、BSR 变化 | Keepa + Amazon |
| **趋势发现** | 发现品类搜索量上升/下降趋势 | Google Trends + Amazon |
| **差评情报** | 持续挖掘竞品新增差评中的产品机会 | Amazon Reviews |
| **新品预警** | 发现品类中的新入场竞品 | Amazon Search |
| **价格情报** | 监控价格战信号、促销活动 | Keepa + Amazon |
| **市场报告** | 自动生成日报/周报，推送关键洞察 | 综合 |

---

## 二、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    市场洞察 Agent                             │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                  调度层 (Scheduler)                   │    │
│  │  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐     │    │
│  │  │每6h  │ │每日  │ │每周  │ │事件  │ │手动  │     │    │
│  │  │价格  │ │评论  │ │趋势  │ │触发  │ │触发  │     │    │
│  │  └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘     │    │
│  └─────┼────────┼────────┼────────┼────────┼──────────┘    │
│        │        │        │        │        │               │
│  ┌─────▼────────▼────────▼────────▼────────▼──────────┐    │
│  │                  采集层 (Collectors)                  │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐            │    │
│  │  │ Keepa    │ │ Amazon   │ │ Google   │            │    │
│  │  │ Collector│ │ Collector│ │ Trends   │            │    │
│  │  └──────────┘ └──────────┘ └──────────┘            │    │
│  └────────────────────┬───────────────────────────────┘    │
│                       │                                     │
│  ┌────────────────────▼───────────────────────────────┐    │
│  │                  分析层 (Analyzers)                   │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐            │    │
│  │  │ 变动检测  │ │ 趋势研判  │ │ LLM 洞察  │            │    │
│  │  │ Detector │ │ Analyzer │ │ Engine   │            │    │
│  │  └──────────┘ └──────────┘ └──────────┘            │    │
│  └────────────────────┬───────────────────────────────┘    │
│                       │                                     │
│  ┌────────────────────▼───────────────────────────────┐    │
│  │                  输出层 (Outputs)                     │    │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐            │    │
│  │  │ 实时告警  │ │ 日报/周报 │ │ 事件推送  │            │    │
│  │  │ Alert   │ │ Report   │ │ Event    │            │    │
│  │  └──────────┘ └──────────┘ └──────────┘            │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、五大核心功能设计

### 3.1 竞品追踪系统

#### 监控对象管理

```python
# 竞品监控配置
WATCHLIST = {
    "弹簧替换件": {
        "keywords": ["trash can spring replacement", "torsion spring kit"],
        "tracked_asins": [
            "B0BVTDP29W",  # Dianrui 300PCS
            "B0FG2DQYY7",  # Fgruh 640PCS
            "B0FGV5FCBN",  # Fgruh M3 750PCS
        ],
        "track_top_n": 10,  # 追踪每个关键词 Top 10
    },
    "U型螺栓": {
        "keywords": ["stainless steel U bolts", "marine U bolts boat trailer"],
        "tracked_asins": ["B0CF8LB4PF"],  # Foliv
        "track_top_n": 10,
    },
    "S挂钩": {
        "keywords": ["heavy duty S hooks", "hammock S hook stainless"],
        "tracked_asins": [],
        "track_top_n": 5,
    }
}
```

#### 变动检测规则

```python
ALERT_RULES = {
    "price_change": {
        "threshold_pct": 10,       # 价格变动 >10% 触发
        "severity": "high",
        "message_template": "⚠️ {asin} 价格从 ${old} → ${new} ({change}%)"
    },
    "stock_out": {
        "condition": "availability == 'Out of Stock'",
        "severity": "critical",
        "message_template": "🔴 {asin} ({brand}) 断货！可能是补货机会"
    },
    "bsr_surge": {
        "threshold_pct": -30,      # BSR 排名上升 >30% (数值下降)
        "severity": "medium",
        "message_template": "📈 {asin} BSR从 #{old} → #{new}，销量可能激增"
    },
    "new_competitor": {
        "condition": "listing_age < 30 days AND bsr_rank < 10000",
        "severity": "high",
        "message_template": "🆕 新竞品入场: {asin} ({brand}) - {title}"
    },
    "review_surge": {
        "threshold": 10,           # 新增评论 >10 条/周
        "severity": "medium",
        "message_template": "💬 {asin} 评论激增: 本周新增 {count} 条"
    },
    "rating_drop": {
        "threshold": -0.2,         # 评分下降 >0.2
        "severity": "medium",
        "message_template": "📉 {asin} 评分从 {old}→{new}，可能有质量问题"
    }
}
```

### 3.2 趋势发现引擎

#### 趋势信号源

| 信号源 | 指标 | 采集频率 | 判断逻辑 |
|--------|------|---------|---------|
| Amazon 搜索量 | 关键词搜索量估算 | 周频 | 连续 3 周上升 → rising |
| Google Trends | 相对搜索热度 | 周频 | 近 4 周 vs 前 12 周均值 |
| BSR 趋势 | 品类 Top 20 BSR 变化 | 日频 | 整体 BSR 下降 → 品类热度上升 |
| 新品密度 | 近 90 天新上架产品数 | 月频 | 新品增多 → 品类受关注 |
| 评论增速 | 头部产品评论增长率 | 周频 | 加速增长 → 需求上升 |

#### 趋势研判模型

```python
def assess_trend(category: str, signals: dict) -> TrendAssessment:
    """
    综合多信号判断趋势方向
    """
    score = 0

    # 搜索量趋势 (权重 30%)
    if signals["search_volume_trend"] == "rising":
        score += 30
    elif signals["search_volume_trend"] == "stable":
        score += 15

    # Google Trends (权重 20%)
    gt_change = signals["google_trends_4w_vs_12w"]
    score += max(min(gt_change * 20, 20), -10)

    # BSR 趋势 (权重 25%)
    if signals["avg_bsr_change"] < -10:  # BSR下降=销量上升
        score += 25
    elif signals["avg_bsr_change"] < 0:
        score += 15

    # 新品密度 (权重 15%)
    if signals["new_listings_90d"] > signals["new_listings_90d_prev"] * 1.5:
        score += 15
    elif signals["new_listings_90d"] > signals["new_listings_90d_prev"]:
        score += 8

    # 评论增速 (权重 10%)
    if signals["review_growth_rate"] > 0.2:
        score += 10
    elif signals["review_growth_rate"] > 0.1:
        score += 5

    # 分级
    if score >= 70:
        direction = "strong_rising"
    elif score >= 50:
        direction = "rising"
    elif score >= 30:
        direction = "stable"
    elif score >= 15:
        direction = "declining"
    else:
        direction = "strong_declining"

    return TrendAssessment(
        category=category,
        direction=direction,
        confidence_score=score,
        signals=signals,
        recommendation=generate_recommendation(direction, signals)
    )
```

### 3.3 差评情报系统

**持续监控竞品新增差评，挖掘产品改进机会**:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ 每日采集      │     │ LLM 分析     │     │ 机会识别     │
│ 竞品新增      │────▶│ 痛点提取     │────▶│ 改进建议     │
│ 1-3星评论    │     │ 分类归档     │     │ 推送通知     │
└─────────────┘     └─────────────┘     └─────────────┘
```

**LLM 分析 Prompt**:

```
你正在分析 Amazon 产品 "{product_title}" 的最新差评。

新增差评内容:
{reviews}

请完成以下分析:

1. **痛点提取**: 每条差评的核心不满是什么？
2. **痛点分类**: 归入以下类别之一: 质量/规格/包装/功能/物流/期望偏差
3. **频率评估**: 这个痛点是个别现象还是系统性问题？
4. **改进可行性**: 作为竞品，我们能否通过产品改进解决此问题？
5. **机会评分** (1-10): 如果解决此痛点，对销量提升的预期影响

输出 JSON 格式。
```

### 3.4 竞争格局分析

**定期（每月）生成品类竞争格局全景报告**:

```python
class CompetitiveLandscape:
    """竞争格局分析"""

    def analyze(self, category: str) -> LandscapeReport:
        # 1. 采集品类 Top 50 产品数据
        products = self.collect_top_products(category, n=50)

        # 2. 计算市场集中度
        concentration = self.calc_concentration(products)
        # CR3: Top 3 占比
        # CR5: Top 5 占比
        # HHI: 赫芬达尔指数

        # 3. 价格带分析
        price_distribution = self.analyze_price_bands(products)
        # 低价带 / 中价带 / 高价带 占比和竞争情况

        # 4. 卖家来源分析
        seller_analysis = self.analyze_sellers(products)
        # 中国卖家占比 / 美国本土卖家占比 / 品牌卖家占比

        # 5. 产品生命周期分析
        lifecycle = self.analyze_lifecycle(products)
        # 新品(< 6个月) / 成长期 / 成熟期 / 衰退期 占比

        # 6. LLM 综合研判
        insight = self.llm_synthesize(
            concentration, price_distribution,
            seller_analysis, lifecycle
        )

        return LandscapeReport(
            category=category,
            concentration=concentration,
            price_distribution=price_distribution,
            seller_analysis=seller_analysis,
            lifecycle=lifecycle,
            insight=insight,
            entry_recommendation=insight.recommendation
        )
```

**输出示例**:

```
## 弹簧替换件 - 竞争格局月报 (2026-02)

### 市场集中度
- CR3 = 35% (分散市场)
- CR5 = 48%
- HHI = 850 (低集中度，竞争充分)

### 价格带分布
┌─────────┬──────┬──────────┬──────────────┐
│ 价格带   │ 占比 │ 竞争程度  │ 建议          │
├─────────┼──────┼──────────┼──────────────┤
│ <$5     │ 15%  │ 低       │ 利润太薄，避开 │
│ $5-$10  │ 55%  │ 中       │ ✅ 主战场     │
│ $10-$20 │ 25%  │ 低       │ ✅ 套装溢价   │
│ >$20    │ 5%   │ 极低     │ 需求不足      │
└─────────┴──────┴──────────┴──────────────┘

### 卖家构成
- 中国卖家: 78%
- 美国本土: 12%
- 其他: 10%

### 关键洞察
1. 本月有 3 个新品进入 Top 20，均为中国卖家
2. Dianrui BSR 上升 15%，正在抢占市场份额
3. $10-$15 价格带竞争最少，套装策略可行
4. 差评改进方向集中在"规格匹配"，这是最大差异化切入点
```

### 3.5 自动报告系统

#### 日报 (Haiku 生成，成本极低)

```
📊 市场日报 - 2026-02-25

🔔 告警事件:
• [高] B0BVTDP29W (Dianrui弹簧) 价格 $6.99→$7.49 (+7.2%)
• [中] B0FG2DQYY7 (Fgruh螺丝) 新增5条评论

📈 BSR 变动 Top 3:
• trash can spring: 平均BSR ↑12%
• U bolt SS: 平均BSR ↓3%（下降=变差）
• S hook: 稳定

💡 AI 建议:
• Dianrui 提价信号明显，我方定价可适当提高
• 弹簧品类持续升温，建议加速选品进度
```

#### 周报 (Sonnet 生成，深度分析)

```markdown
# 市场周报 - 2026-02 W4

## 一、核心指标变化

| 品类 | 搜索量变化 | 头部BSR变化 | 新品数 | 关注度 |
|------|-----------|------------|--------|--------|
| 弹簧替换件 | +8% | ↑15% | 2 | 🟢 上升 |
| U型螺栓 | -2% | 稳定 | 0 | 🟡 稳定 |
| S挂钩 | +1% | 稳定 | 1 | 🟡 稳定 |

## 二、重点事件

### Dianrui 提价策略分析
Dianrui (B0BVTDP29W) 本周将弹簧套装从 $6.99 提价至 $7.49...
[LLM 深度分析: 提价原因、对市场的影响、我方应对建议]

### 新竞品入场警报
ASIN: B0XXXXX, 品牌: NewBrand, 上架30天, BSR已冲到 #8000...
[LLM 分析: 该竞品的策略、威胁等级、差异化优势]

## 三、机会与建议

1. **弹簧品类**: 搜索量持续上升，竞争度未明显增加，窗口期仍在
2. **定价建议**: Dianrui提价后，$7.99-$8.99 定价空间打开
3. **选品建议**: 建议本周启动 "recliner spring replacement" 深度分析

## 四、下周关注重点
- 监控 Dianrui 提价后的销量变化（验证价格弹性）
- 跟踪新竞品 B0XXXXX 的评论积累速度
- Google Trends "spring replacement" 趋势走势
```

---

## 四、数据流设计

### 4.1 采集 → 存储 → 分析 流程

```
定时触发 (每6小时/每日/每周)
    │
    ▼
┌─────────────────────────┐
│     数据采集              │
│  Keepa: 价格/BSR/销量    │
│  Amazon: 评论/新品       │
│  Google: 搜索趋势        │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│     数据存储              │
│  price_history 表        │
│  review_analysis 表      │
│  market_trends 表        │
│  competitor_events 表    │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│     变动检测              │
│  对比上次快照             │
│  触发告警规则             │
└───────────┬─────────────┘
            │
     ┌──────┴──────┐
     │             │
     ▼             ▼
┌─────────┐  ┌─────────┐
│ 即时告警 │  │ 累积分析 │
│ (飞书)  │  │ (日报)  │
└─────────┘  └─────────┘
```

### 4.2 与选品 Agent 的协作

```
市场洞察 Agent                              选品 Agent
     │                                          │
     │ 发现: "recliner spring"                   │
     │ 搜索量连续3周上升15%                       │
     │                                          │
     │──── Event: trend_discovered ──────────────▶│
     │     {                                     │
     │       category: "recliner spring",        │
     │       signal: "search_volume_rising",     │ ──▶ 自动触发选品分析
     │       growth_rate: 0.15,                  │
     │       confidence: 0.82                    │
     │     }                                     │
     │                                          │
     │◀──── Event: scout_result ─────────────────│
     │      {                                    │
     │        category: "recliner spring",       │ ◀── 选品结果反馈
     │        opportunity_score: 78,             │     纳入趋势追踪
     │        top_candidate: "B0XXXXX"           │
     │      }                                    │
```

---

## 五、成本控制

### 5.1 分级采集策略

| 级别 | 对象 | 采集频率 | Keepa Token | LLM 调用 |
|------|------|---------|-------------|---------|
| **核心监控** | 已上架/计划上架的竞品 (5-10 ASIN) | 每 6 小时 | ~200/天 | 0 |
| **重点关注** | 品类 Top 20 (20-40 ASIN) | 每日 | ~100/天 | Haiku ×1 |
| **广泛扫描** | 品类 Top 100 + 新品 | 每周 | ~200/周 | Sonnet ×1 |
| **趋势探测** | 30 个关键词 Google Trends | 每周 | 0 | Haiku ×1 |

### 5.2 月度成本预估

| 项目 | 月成本 |
|------|--------|
| Keepa API (约 10K tokens/月) | ~$15 |
| Claude Sonnet (周报 ×4 + 月报 ×1) | ~$0.50 |
| Claude Haiku (日报 ×30 + 告警处理) | ~$0.10 |
| **月度合计** | **~$16** |

---

## 六、迭代路线

| 版本 | 能力 | 阶段 |
|------|------|------|
| v0.1 | 竞品价格追踪 + 基础告警 | Phase 1 M1 |
| v0.2 | + 差评情报 + 日报自动生成 | Phase 1 M2 |
| v0.3 | + 趋势发现 + 竞争格局分析 + 与选品Agent联动 | Phase 1 M3 |
| v1.0 | + 周报/月报 + 历史趋势对比 | Phase 2 |
| v2.0 | + 多站点监控 + 预测模型 | Phase 3 |

---

*本文档定义了市场洞察 Agent 的完整设计，代码实现见 `ai-agent-prototype/src/agents/market_insight.py`*

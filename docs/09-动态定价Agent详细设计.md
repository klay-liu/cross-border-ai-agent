# 动态定价 Agent 详细设计

**版本**: v1.0
**日期**: 2026-02-26
**优先级**: P3 — Phase 3

---

## 一、Agent 定位

### 1.1 核心使命

将定价从「上架定一个价不动」转变为「基于市场实时动态调整的智能定价」：

```
传统定价:
参考竞品定个价 → 卖不动就降价 → 打价格战 → 利润越来越薄

Agent 定价:
竞品价格监控 → 库存水位联动 → 利润目标约束 → 心理学定价 → 动态调整
                                                      ↓
                                         促销策略 → 利润最大化而非销量最大化
```

### 1.2 核心能力矩阵

| 能力 | 说明 | 数据源 |
|------|------|--------|
| **竞品价格追踪** | 实时监控竞品价格变动，识别价格战信号 | Keepa + Amazon |
| **库存联动定价** | 库存多时促销清仓，库存少时适当提价 | FBA 库存数据 |
| **利润优化** | 在销量和利润之间寻找最优平衡点 | 成本结构 + 销量弹性 |
| **促销策略** | 自动规划 Coupon/Deal/价格调整 | Amazon Promotions |
| **心理学定价** | 应用 .99/.97 等价格尾数策略 | 定价规则库 |
| **价格位置分析** | 分析自身价格在市场中的位置 | 竞品价格分布 |

---

## 二、定价约束与红线

### 2.1 核心定价规则

```python
PRICING_RULES = {
    "hard_limits": {
        "never_below_cost": True,
        # 绝对底线: 售价 ≥ 总成本 (产品成本 + FBA费用 + 佣金 + 头程)
        # 确保不会亏本销售

        "never_trigger_amazon_alert": True,
        # Amazon 会对价格异常波动发出警告
        # 单次调价幅度 ≤ 20%
        # 不低于同ASIN历史最低价的70%

        "min_margin_pct": 0.10,
        # 最低毛利率 10% (极端促销场景)

        "target_margin_pct": 0.25,
        # 目标毛利率 25%
    },
    "new_product_rules": {
        "no_major_price_change_days": 90,
        # 新品上架前3个月不做大幅价格调整
        # 避免影响 Amazon 价格锚定算法

        "max_change_pct_first_90d": 0.05,
        # 前90天单次调价不超过5%

        "launch_discount_allowed": True,
        # 允许新品上架 Coupon (但不直接降价)
    },
    "frequency_limits": {
        "max_price_changes_per_day": 2,
        # 每天最多调价2次

        "min_hours_between_changes": 6,
        # 两次调价间隔至少6小时

        "max_price_changes_per_week": 5,
        # 每周最多调价5次
    }
}
```

### 2.2 成本结构模型

```python
def calculate_floor_price(product: dict) -> PriceFloor:
    """
    计算价格地板（绝对不能低于此价格）
    """
    # 产品成本
    product_cost_usd = product["factory_cost_rmb"] / 7.15  # 汇率

    # FBA 费用
    fba_fee = get_fba_fee(
        product["weight_oz"],
        product["dimensions"],
        product["category"]
    )

    # Amazon 佣金 (通常 15%)
    # 注意: 佣金是基于售价的百分比，需要反算
    commission_rate = 0.15

    # 头程物流分摊
    shipping_per_unit = product["shipping_cost_per_cbm"] * product["volume_cbm"]

    # 地板价公式:
    # floor_price = (product_cost + fba_fee + shipping) / (1 - commission_rate - min_margin)
    floor_price = (
        (product_cost_usd + fba_fee + shipping_per_unit)
        / (1 - commission_rate - PRICING_RULES["hard_limits"]["min_margin_pct"])
    )

    return PriceFloor(
        floor_price=round(floor_price, 2),
        breakdown={
            "product_cost": product_cost_usd,
            "fba_fee": fba_fee,
            "shipping": shipping_per_unit,
            "commission_rate": commission_rate,
            "min_margin": PRICING_RULES["hard_limits"]["min_margin_pct"],
        }
    )
```

---

## 三、价格位置分析

### 3.1 竞品价格分布图

```
竞品价格分布 (trash can spring replacement)
─────────────────────────────────────────────

$4.00  │ ██ (2个竞品)             低价区 - 利润太薄
$5.00  │ ███ (3个竞品)
$6.00  │ █████ (5个竞品)          <-- 低价竞争密集区
$7.00  │ ████████ (8个竞品)       <-- 主战场
$8.00  │ ██████ (6个竞品)         <-- 目标价格带
$9.00  │ ███ (3个竞品)            <-- 差异化溢价区
$10.00 │ ██ (2个竞品)
$12.00 │ █ (1个竞品)              高端套装
       └──────────────────────

我方定位: $8.99 (高于平均 $7.20, 差异化定价)
价格分位: P72 (高于72%的竞品)
策略: 品质溢价 + 差异化卖点支撑
```

### 3.2 价格位置评估

```python
def analyze_price_position(asin: str) -> PricePosition:
    """
    分析产品在市场中的价格位置
    """
    # 采集品类 Top 30 竞品价格
    competitors = get_competitor_prices(asin, top_n=30)
    prices = [c["price"] for c in competitors]

    my_price = get_current_price(asin)

    # 计算统计指标
    avg_price = sum(prices) / len(prices)
    median_price = sorted(prices)[len(prices) // 2]
    min_price = min(prices)
    max_price = max(prices)
    percentile = sum(1 for p in prices if p <= my_price) / len(prices)

    # 价格带分析
    price_bands = categorize_price_bands(prices)

    # 竞争密度 (同价格带 ±10% 的竞品数量)
    same_band_count = sum(
        1 for p in prices
        if my_price * 0.9 <= p <= my_price * 1.1
    )

    return PricePosition(
        my_price=my_price,
        avg_market_price=avg_price,
        median_price=median_price,
        percentile=percentile,
        price_premium_pct=(my_price - avg_price) / avg_price,
        same_band_competitors=same_band_count,
        price_bands=price_bands,
        recommendation=generate_price_recommendation(
            my_price, avg_price, percentile, same_band_count
        )
    )
```

---

## 四、竞品价格响应决策树

```
竞品价格变动检测
    │
    ▼
┌──────────────────────────┐
│ 变动类型判断               │
└───┬──────────┬───────────┘
    │          │
    ▼          ▼
 竞品降价    竞品提价
    │          │
    ▼          ▼
降幅 > 20%?  ┌──────────────────┐
┌──┴──┐     │ 评估跟涨可行性    │
│     │     │ 我方有差异化优势?  │
▼     ▼     └──┬───────┬───────┘
YES   NO       YES     NO
│     │        │       │
▼     ▼        ▼       ▼
┌─────┐ ┌────┐ ┌─────┐ ┌────────┐
│观望  │ │评估│ │跟涨  │ │维持    │
│不跟  │ │是否│ │50%  │ │当前价格│
│可能  │ │需要│ │幅度  │ └────────┘
│清仓  │ │跟进│ └─────┘
└─────┘ └──┬─┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
  影响我方     不影响
  BSR/销量?    (不同价格带)
     │           │
     ▼           ▼
┌─────────┐ ┌────────┐
│小幅跟进  │ │不调整  │
│降5-10%  │ │继续    │
│观察7天  │ │监控    │
└─────────┘ └────────┘
```

### 4.1 竞品响应规则

```python
COMPETITOR_RESPONSE_RULES = {
    "competitor_price_drop": {
        "major_drop": {
            # 竞品大幅降价 (>20%)
            "condition": "competitor_price_change_pct < -0.20",
            "action": "observe_7_days",
            "reason": "可能是清仓/错误定价，不急于跟进",
            "alert": "high",
        },
        "moderate_drop": {
            # 竞品中等降价 (10-20%)
            "condition": "-0.20 <= competitor_price_change_pct < -0.10",
            "action": "evaluate_impact",
            "evaluation": [
                "检查我方近7天BSR变化",
                "检查我方近7天销量变化",
                "如果销量下降>15%，考虑跟进降价5-10%",
                "如果销量稳定，维持价格不变",
            ]
        },
        "minor_drop": {
            # 竞品小幅降价 (<10%)
            "condition": "competitor_price_change_pct >= -0.10",
            "action": "monitor_only",
            "reason": "小幅波动属正常，无需反应",
        }
    },
    "competitor_price_increase": {
        "action": "evaluate_follow",
        "rules": [
            "如果我方有差异化优势，跟涨50%幅度",
            "如果我方无明显优势，保持不变享受相对价格优势",
            "如果多个竞品同时提价，可能是成本上升信号，适当跟涨",
        ]
    }
}
```

---

## 五、库存联动定价

### 5.1 库存-价格联动模型

```python
INVENTORY_PRICING_RULES = {
    "overstocked": {
        # 库存积压 (可售天数 > 120天)
        "condition": "days_of_supply > 120",
        "price_action": "降价促销",
        "strategies": [
            {"method": "coupon", "discount": "10-15%", "duration": "14天"},
            {"method": "lightning_deal", "discount": "20%", "if": "临近大促"},
            {"method": "price_reduction", "max": "10%", "if": "coupon效果不佳"},
        ],
        "goal": "加速周转，避免长期仓储费",
    },
    "healthy": {
        # 库存健康 (可售天数 45-120天)
        "condition": "45 <= days_of_supply <= 120",
        "price_action": "维持目标价格",
        "strategies": [
            {"method": "maintain_price", "target_margin": "25%"},
            {"method": "small_coupon", "discount": "5%", "if": "需提升转化率"},
        ],
        "goal": "利润最大化",
    },
    "low_stock": {
        # 库存偏低 (可售天数 < 45天)
        "condition": "days_of_supply < 45",
        "price_action": "考虑提价",
        "strategies": [
            {"method": "remove_coupons", "immediate": True},
            {"method": "price_increase", "max": "5-10%", "gradual": True},
            {"method": "pause_ads", "if": "days_of_supply < 20"},
        ],
        "goal": "减缓销速，等待补货到达",
    },
    "near_stockout": {
        # 即将断货 (可售天数 < 15天)
        "condition": "days_of_supply < 15",
        "price_action": "显著提价",
        "strategies": [
            {"method": "price_increase", "amount": "15-25%"},
            {"method": "pause_all_ads", "immediate": True},
            {"method": "reduce_fba_shipments", "if": "有多渠道库存"},
        ],
        "goal": "最大化剩余库存的利润，避免断货排名损失",
    }
}
```

---

## 六、心理学定价策略

### 6.1 价格尾数规则

```python
PSYCHOLOGICAL_PRICING = {
    "charm_pricing": {
        # .99 定价 - 主流策略
        "rule": "价格尾数使用 .99",
        "examples": ["$7.99", "$12.99", "$24.99"],
        "applicable": "大多数产品的常规定价",
        "psychology": "左位数效应: $7.99感知为$7而非$8",
    },
    "just_below": {
        # .97 定价 - 促销感
        "rule": "价格尾数使用 .97",
        "examples": ["$7.97", "$12.97"],
        "applicable": "希望暗示折扣/促销的场景",
        "psychology": "非整数的奇特感暗示这是特价",
    },
    "premium_pricing": {
        # .00 定价 - 品质感
        "rule": "使用整数价格",
        "examples": ["$10.00", "$25.00"],
        "applicable": "高端/品质定位的产品",
        "psychology": "整数价格传递品质和信心",
    },
    "bundle_anchor": {
        # 套装锚定
        "rule": "单件价格用 .99，套装价格略低于心理关口",
        "examples": [
            "单件 $7.99, 3件套 $19.99 (单件$6.66)",
            "5件套 $24.97 (单件$4.99)",
        ],
        "psychology": "套装价格跨越价格锚点，感知更划算",
    }
}

def apply_psychological_pricing(raw_price: float, strategy: str = "charm") -> float:
    """
    应用心理学定价规则
    """
    if strategy == "charm":
        return math.floor(raw_price) + 0.99 if raw_price % 1 > 0.5 \
            else math.floor(raw_price) - 0.01
    elif strategy == "just_below":
        return math.floor(raw_price) + 0.97 if raw_price % 1 > 0.5 \
            else math.floor(raw_price) - 0.03
    elif strategy == "premium":
        return round(raw_price)
    return round(raw_price, 2)
```

---

## 七、工作流程

```
每日 10:00 AM + 18:00 PM 自动触发（两次）
    │
    ▼
┌─────────────────────────────────────┐
│ Step 1: 竞品价格采集                 │
│ 监控目标竞品当前价格                 │
│ 与上次快照对比，检测变动             │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Step 2: 库存状态同步                 │
│ 获取当前 FBA 库存 + 在途库存         │
│ 计算可售天数                         │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Step 3: 价格位置分析                 │
│ 计算市场分位 + 竞争密度              │
│ 评估当前价格合理性                   │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Step 4: 定价决策                     │
│ 竞品响应 + 库存联动 + 利润约束       │
│ 输出: 建议价格 + 调整理由            │
└──────────┬──────────────────────────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
 需要调价?    不需要调价
     │           │
     ▼           ▼
┌──────────┐ ┌──────────┐
│ 合规检查  │ │ 记录日志  │
│ 红线校验  │ └──────────┘
└────┬─────┘
     │
     ▼
 调价幅度 > 10%?
 ┌───┴───┐
YES     NO
 │       │
 ▼       ▼
┌──────┐┌──────────┐
│人工  ││自动执行   │
│审核  ││调价+记录  │
└──────┘└──────────┘
```

---

## 八、Prompt 设计

### 8.1 定价策略分析 Prompt

```
你是跨境电商定价策略专家。基于以下数据，给出定价建议。

产品信息:
- 产品: {product_name}
- 当前售价: ${current_price}
- 成本结构: {cost_breakdown}
- 当前毛利率: {current_margin}%

市场数据:
- 竞品价格分布: {competitor_prices}
- 我方价格分位: P{percentile}
- 近7天BSR变化: {bsr_change}
- 近7天日均销量: {avg_daily_sales}

库存状态:
- 可售天数: {days_of_supply}天
- 在途库存: {in_transit}件

约束条件:
- 价格地板: ${floor_price}
- 目标毛利率: ≥25%
- 新品前90天调价幅度 ≤5%
- 不触发 Amazon 价格警告

请分析并给出:
1. 当前价格评估 (偏高/合理/偏低)
2. 建议价格及理由
3. 调价时机建议
4. 促销策略建议 (是否需要Coupon/Deal)
5. 风险提示

输出 JSON 格式。
```

---

## 九、数据模型

### 9.1 价格记录

```python
class PriceRecord:
    record_id: str                # 记录ID
    asin: str                     # ASIN
    record_type: str              # 类型(my_price/competitor)
    price: float                  # 价格
    was_price: float              # 原价(如有划线价)
    coupon_pct: float             # Coupon折扣百分比
    effective_price: float        # 实际到手价
    bsr_rank: int                 # 当时BSR
    recorded_at: datetime         # 记录时间
```

### 9.2 定价决策记录

```python
class PricingDecision:
    decision_id: str              # 决策ID
    asin: str                     # ASIN
    old_price: float              # 原价格
    new_price: float              # 新价格
    change_pct: float             # 变动百分比
    reason: str                   # 调价原因
    trigger: str                  # 触发因素(competitor/inventory/manual/scheduled)
    expected_margin: float        # 预期毛利率
    approval_status: str          # 审批状态(auto/pending/approved/rejected)
    executed: bool                # 是否已执行
    executed_at: datetime         # 执行时间
    impact_7d: dict               # 7天后效果回溯
    # {sales_change_pct, bsr_change, margin_actual}
```

### 9.3 促销记录

```python
class PromotionRecord:
    promotion_id: str             # 促销ID
    asin: str                     # ASIN
    promotion_type: str           # 类型(coupon/lightning_deal/price_reduction)
    discount_pct: float           # 折扣百分比
    start_date: datetime          # 开始时间
    end_date: datetime            # 结束时间
    budget: float                 # 预算
    redemptions: int              # 使用次数
    incremental_sales: int        # 增量销售
    cost: float                   # 促销成本
    roi: float                    # 促销ROI
```

---

## 十、成本控制

| 环节 | LLM 调用 | 预估 Token | 月度成本 |
|------|---------|-----------|---------|
| 竞品价格采集 (规则引擎) | 0 | 0 | $0 |
| 每日定价评估 (规则引擎为主) | Haiku ×2/天 | ~4K/天 | ~$0.36 |
| 周度定价策略深度分析 | Sonnet ×1/周 | ~8K/周 | ~$0.96 |
| 促销策略建议 (~4次/月) | Sonnet ×4/月 | ~20K | ~$0.60 |
| **月度合计** | | | **~$1.92** |

---

## 十一、迭代路线

| 版本 | 能力 | 阶段 |
|------|------|------|
| v0.1 | 竞品价格监控 + 价格位置分析 + 基础告警 | Phase 3 M1 |
| v0.2 | + 库存联动定价 + 心理学定价规则 | Phase 3 M2 |
| v0.3 | + 竞品响应决策树 + 自动调价(小幅度) | Phase 3 M3 |
| v1.0 | + 促销策略自动化 + 利润优化模型 + 效果回溯 | Phase 3 M4 |
| v2.0 | + 价格弹性建模 + 多站点定价协调 + A/B测试 | Phase 4 |

---

*本文档定义了动态定价 Agent 的完整设计，代码实现见 `ai-agent-prototype/src/agents/dynamic_pricing.py`*

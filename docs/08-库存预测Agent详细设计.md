# 库存预测 Agent 详细设计

**版本**: v1.0
**日期**: 2026-02-26
**优先级**: P3 — Phase 3

---

## 一、Agent 定位

### 1.1 核心使命

将库存管理从「拍脑袋补货」转变为「数据预测驱动的精准补货」，避免断货和积压：

```
传统库存管理:
感觉快卖完了 → 赶紧下单补货 → 海运45天 → 到货时要么断货了要么积压了

Agent 库存管理:
销量预测 → 提前计算补货点 → 自动触发补货提醒 → 考虑物流时效 → 精准到货
                                                      ↓
                                               仓储成本优化 → 利润最大化
```

### 1.2 核心能力矩阵

| 能力 | 说明 | 数据源 |
|------|------|--------|
| **需求预测** | 移动平均 + 季节性 + 趋势的综合预测模型 | 历史销量数据 |
| **补货计算** | 基于物流时效自动计算最优补货时间和数量 | 预测 + 物流参数 |
| **断货预警** | 实时监控库存水位，三级预警（红/黄/绿） | FBA 库存 + 在途库存 |
| **仓储优化** | 监控 FBA 仓储费，优化库存周转率 | FBA 费用报表 |
| **季节性规划** | 识别季节性品类，提前规划大促备货 | 历史数据 + 日历事件 |
| **多仓协调** | 工厂 → 国内仓 → 海运 → FBA 全链路跟踪 | 物流系统 |

---

## 二、物流时效参数

### 2.1 供应链关键节点

```
┌──────────┐   7-15天   ┌──────────┐   3-5天   ┌──────────┐
│ 工厂生产  │──────────▶│ 国内仓备货 │─────────▶│ 出口报关  │
└──────────┘           └──────────┘           └────┬─────┘
                                                    │
                                              35-45天│ 海运
                                                    │
┌──────────┐  7-14天   ┌──────────┐   5-7天   ┌────▼─────┐
│ FBA上架   │◀─────────│ FBA入仓   │◀─────────│ 目的港清关│
│ 可售     │           │ 接收处理  │           └──────────┘
└──────────┘           └──────────┘
```

### 2.2 时效参数配置

```python
LOGISTICS_PARAMS = {
    "production": {
        "standard_days": 10,         # 标准生产周期
        "range": (7, 15),            # 范围 7-15 天
        "rush_surcharge": 0.15,      # 加急费加价 15%
    },
    "domestic_warehouse": {
        "processing_days": 4,        # 国内仓处理
        "range": (3, 5),
    },
    "sea_freight": {
        "standard_days": 40,         # 标准海运
        "range": (35, 45),           # 范围 35-45 天
        "cost_per_cbm": 35.00,       # 每立方米 $35
    },
    "customs_clearance": {
        "standard_days": 6,          # 清关
        "range": (5, 7),
    },
    "fba_inbound": {
        "standard_days": 10,         # FBA 入仓处理
        "range": (7, 14),            # 范围 7-14 天
        "peak_season_days": 21,      # 旺季可能延长到 21 天
    },
    # 全链路总计
    "total_lead_time": {
        "standard_days": 70,         # 标准总时效 ~70 天
        "range": (57, 86),           # 最快57天，最慢86天
        "planning_buffer": 1.5,      # 安全系数 1.5
    }
}
```

---

## 三、需求预测模型

### 3.1 预测算法

```python
def forecast_demand(asin: str, forecast_days: int = 90) -> ForecastResult:
    """
    综合预测模型: 移动平均 + 季节性因子 + 趋势修正

    forecast = base_demand × seasonal_factor × trend_multiplier
    """
    # 获取历史销量数据（至少90天）
    history = get_sales_history(asin, days=180)

    # 1. 基础需求 (加权移动平均)
    #    近7天权重最高，逐步递减
    base_demand = weighted_moving_average(
        history,
        weights={
            "last_7d": 0.40,     # 近7天
            "last_14d": 0.25,    # 近14天
            "last_30d": 0.20,    # 近30天
            "last_90d": 0.15,    # 近90天
        }
    )

    # 2. 季节性因子
    #    对比去年同期（如有数据）
    seasonal_factor = calc_seasonal_factor(
        asin,
        target_month=forecast_month,
        baseline_months=get_baseline_months(history)
    )

    # 3. 趋势修正
    #    检测近30天是上升/下降/稳定趋势
    trend = detect_trend(history, window=30)
    trend_multiplier = {
        "strong_rising": 1.20,
        "rising": 1.10,
        "stable": 1.00,
        "declining": 0.90,
        "strong_declining": 0.80,
    }[trend.direction]

    # 4. 综合预测
    daily_forecast = base_demand * seasonal_factor * trend_multiplier

    return ForecastResult(
        asin=asin,
        daily_forecast=daily_forecast,
        forecast_days=forecast_days,
        total_forecast=daily_forecast * forecast_days,
        confidence_interval=(
            daily_forecast * 0.75,  # 下界
            daily_forecast * 1.30,  # 上界
        ),
        model_inputs={
            "base_demand": base_demand,
            "seasonal_factor": seasonal_factor,
            "trend": trend.direction,
            "trend_multiplier": trend_multiplier,
        }
    )
```

### 3.2 季节性日历

```python
SEASONAL_EVENTS = {
    "Q1": [
        {"event": "New Year", "dates": "01-01~01-07", "impact": 0.8},
        {"event": "Valentine's Day", "dates": "02-07~02-14", "impact": 1.0},
        {"event": "President's Day", "dates": "02-17~02-20", "impact": 1.1},
    ],
    "Q2": [
        {"event": "Spring Season", "dates": "03-15~05-15", "impact": 1.2},
        {"event": "Mother's Day", "dates": "05-05~05-12", "impact": 1.1},
        {"event": "Memorial Day", "dates": "05-22~05-28", "impact": 1.15},
    ],
    "Q3": [
        {"event": "Prime Day", "dates": "07-10~07-15", "impact": 2.0},
        {"event": "Back to School", "dates": "08-01~09-05", "impact": 1.3},
        {"event": "Labor Day", "dates": "09-01~09-05", "impact": 1.1},
    ],
    "Q4": [
        {"event": "Halloween", "dates": "10-15~10-31", "impact": 1.1},
        {"event": "Black Friday", "dates": "11-20~11-30", "impact": 2.5},
        {"event": "Cyber Monday", "dates": "12-01~12-03", "impact": 2.0},
        {"event": "Christmas", "dates": "12-01~12-25", "impact": 1.8},
    ],
}
```

---

## 四、补货计算与预警

### 4.1 补货点公式

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  补货点 (Reorder Point)                                      │
│  = 日均销量 × 补货前置时间 × 安全系数                          │
│  = daily_sales × total_lead_time × safety_factor            │
│                                                             │
│  示例:                                                       │
│  日均销量 5 件 × 前置时间 70 天 × 安全系数 1.5               │
│  = 525 件                                                   │
│  → 当 FBA可售库存 + 在途库存 ≤ 525 件时，触发补货            │
│                                                             │
│  补货数量 (Reorder Quantity)                                 │
│  = 日均销量 × 补货周期天数 × 安全系数                         │
│  = daily_sales × reorder_cycle_days × safety_factor         │
│                                                             │
│  示例:                                                       │
│  日均销量 5 件 × 补货周期 90 天 × 安全系数 1.5               │
│  = 675 件 (本批次补货量)                                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 三级库存预警

```python
INVENTORY_ALERT_LEVELS = {
    "red": {
        # 红色预警: 即将断货
        "condition": "available_stock + in_transit < daily_sales * 30",
        "description": "可售库存不足30天，且在途库存无法覆盖缺口",
        "urgency": "紧急",
        "actions": [
            "立即飞书告警 + 短信通知",
            "评估是否需要空运补货",
            "考虑临时提价降低销速",
            "联系工厂确认最快交期",
        ],
        "icon": "RED",
    },
    "yellow": {
        # 黄色预警: 需要启动补货
        "condition": "available_stock + in_transit < reorder_point",
        "description": "库存已到补货点，需立即启动补货流程",
        "urgency": "重要",
        "actions": [
            "飞书通知运营人员",
            "自动生成补货建议单",
            "计算最优补货数量",
            "评估是否合并其他SKU一起发货",
        ],
        "icon": "YELLOW",
    },
    "green": {
        # 绿色: 库存健康
        "condition": "available_stock + in_transit >= reorder_point",
        "description": "库存水位正常",
        "urgency": "正常",
        "actions": [
            "常规监控，无需操作",
        ],
        "icon": "GREEN",
    },
}
```

### 4.3 库存预警看板

```
┌──────────────────────────────────────────────────────────────┐
│                    库存健康看板                                │
│                    2026-02-26                                 │
├──────────┬──────┬──────┬──────┬───────┬───────┬─────────────┤
│ SKU      │ 日销 │ FBA  │ 在途 │ 可售天 │ 补货点 │ 状态        │
│          │      │ 库存 │ 库存 │ 数     │       │             │
├──────────┼──────┼──────┼──────┼───────┼───────┼─────────────┤
│ 弹簧5件套 │  5   │  80  │ 300  │  76天  │  525  │ [GREEN] 健康│
│ U型螺栓   │  3   │  25  │   0  │   8天  │  315  │ [RED] 紧急  │
│ S挂钩10件 │  2   │  90  │ 200  │ 145天  │  210  │ [GREEN] 健康│
│ 卡簧套装  │  4   │ 150  │   0  │  38天  │  420  │ [YELLOW]补货│
└──────────┴──────┴──────┴──────┴───────┴───────┴─────────────┘
```

---

## 五、工作流程

```
每日 08:00 AM 自动触发
    │
    ▼
┌─────────────────────────────────────┐
│ Step 1: 数据采集                     │
│ FBA 库存数量 + 在途库存              │
│ 近30天日销量 + 退货数据              │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Step 2: 需求预测                     │
│ 加权移动平均 × 季节因子 × 趋势修正   │
│ 输出: 未来90天日均销量预测            │
└──────────┬──────────────────────────┘
           │
           ▼
┌─────────────────────────────────────┐
│ Step 3: 库存水位评估                 │
│ 计算可售天数                         │
│ 对比补货点 → 确定预警级别            │
└──────────┬──────────────────────────┘
           │
     ┌─────┴──────────────┐
     │                    │
     ▼                    ▼
 红色/黄色预警?         绿色(健康)
     │                    │
     ▼                    ▼
┌──────────┐       ┌──────────┐
│ 计算补货  │       │ 记录日志  │
│ 数量+时间 │       │ 无需操作  │
└────┬─────┘       └──────────┘
     │
     ▼
┌──────────────────────────────────────┐
│ Step 4: 生成补货建议                  │
│ 补货数量 + 建议发货方式(海运/空运)    │
│ 预计到货时间 + 成本估算               │
└──────────┬───────────────────────────┘
           │
           ▼
┌──────────────────────────────────────┐
│ Step 5: 推送通知                      │
│ 飞书推送库存日报 + 补货提醒           │
│ 红色预警 → 额外短信通知               │
└──────────────────────────────────────┘
```

---

## 六、仓储成本优化

### 6.1 FBA 仓储费监控

```python
FBA_STORAGE_COSTS = {
    "standard_size": {
        "jan_sep": 0.87,     # $/立方英尺/月 (1-9月)
        "oct_dec": 2.40,     # $/立方英尺/月 (10-12月旺季)
    },
    "oversize": {
        "jan_sep": 0.56,
        "oct_dec": 1.40,
    },
    "long_term_storage": {
        "181_365_days": 6.90,    # 超180天 $6.90/立方英尺
        "over_365_days": 6.90,   # 超365天 $6.90/立方英尺 或 $0.15/件
    },
    "aged_inventory_surcharge": {
        "271_365_days": 1.50,    # 额外附加费
        "over_365_days": 6.90,
    }
}

def optimize_storage(asin: str) -> StorageOptimization:
    """
    仓储成本优化建议
    """
    inventory = get_fba_inventory(asin)
    age_distribution = get_inventory_age(asin)

    recommendations = []

    # 1. 检查长期仓储风险
    if age_distribution["over_180_days"] > 0:
        recommendations.append({
            "action": "清理超龄库存",
            "units": age_distribution["over_180_days"],
            "potential_saving": calc_long_term_fee(age_distribution),
            "methods": ["降价促销", "站外清仓", "创建移除订单"]
        })

    # 2. 检查库存周转率
    turnover_days = inventory["units"] / daily_sales
    if turnover_days > 90:
        recommendations.append({
            "action": "减少下批补货量，提高周转率",
            "current_turnover_days": turnover_days,
            "target_turnover_days": 60,
        })

    # 3. Q4 仓储费预警
    if current_month >= 8 and turnover_days > 60:
        recommendations.append({
            "action": "Q4仓储费即将翻倍，建议降低库存水位",
            "current_monthly_cost": calc_monthly_storage(inventory),
            "q4_monthly_cost": calc_monthly_storage(inventory, peak=True),
        })

    return StorageOptimization(recommendations=recommendations)
```

---

## 七、Prompt 设计

### 7.1 补货建议生成 Prompt

```
基于以下库存和销售数据，生成补货建议报告。

SKU: {sku_name}
ASIN: {asin}

库存状态:
- FBA 可售库存: {fba_available} 件
- FBA 不可售: {fba_unsellable} 件
- 在途库存: {in_transit} 件 (预计到货: {eta})
- 工厂库存: {factory_stock} 件

销售数据:
- 近7天日均: {avg_7d} 件/天
- 近30天日均: {avg_30d} 件/天
- 近90天日均: {avg_90d} 件/天
- 趋势方向: {trend}

物流参数:
- 生产周期: {production_days} 天
- 海运时效: {shipping_days} 天
- FBA入仓: {fba_inbound_days} 天

请输出:
1. 当前库存可售天数
2. 预警级别 (红/黄/绿)
3. 是否需要立即补货
4. 建议补货数量和发货方式
5. 预计到货时间
6. 成本估算
7. 风险提示（断货风险/积压风险）
```

---

## 八、数据模型

### 8.1 库存快照

```python
class InventorySnapshot:
    snapshot_id: str              # 快照ID
    asin: str                     # ASIN
    sku: str                      # SKU
    snapshot_date: date           # 快照日期
    fba_available: int            # FBA可售库存
    fba_inbound: int              # FBA入库中
    fba_reserved: int             # FBA预留
    fba_unsellable: int           # FBA不可售
    in_transit_sea: int           # 海运在途
    in_transit_air: int           # 空运在途
    factory_stock: int            # 工厂库存
    daily_sales_avg: float        # 日均销量
    days_of_supply: float         # 可售天数
    alert_level: str              # 预警级别(red/yellow/green)
    reorder_point: int            # 补货点
    storage_cost_monthly: float   # 月仓储费
```

### 8.2 补货记录

```python
class ReplenishmentOrder:
    order_id: str                 # 补货单号
    asin: str                     # ASIN
    quantity: int                 # 补货数量
    shipping_method: str          # 运输方式(sea/air/express)
    order_date: date              # 下单日期
    production_start: date        # 开始生产
    production_end: date          # 生产完成
    ship_date: date               # 发货日期
    estimated_arrival: date       # 预计到达FBA
    actual_arrival: date          # 实际到达
    unit_cost: float              # 单位成本
    shipping_cost: float          # 运费
    total_cost: float             # 总成本
    status: str                   # 状态(planned/producing/shipped/arrived)
    triggered_by: str             # 触发方式(auto/manual)
```

---

## 九、成本控制

| 环节 | LLM 调用 | 预估 Token | 月度成本 |
|------|---------|-----------|---------|
| 每日库存评估 (规则引擎) | 0 | 0 | $0 |
| 补货建议报告 (~10次/月) | Haiku ×10 | ~20K | ~$0.06 |
| 周度库存深度分析 | Sonnet ×4/月 | ~20K | ~$0.60 |
| 季节性规划 (季度) | Sonnet ×1/季 | ~10K | ~$0.09 |
| **月度合计** | | | **~$0.75** |

---

## 十、迭代路线

| 版本 | 能力 | 阶段 |
|------|------|------|
| v0.1 | FBA 库存监控 + 简单移动平均预测 + 三级预警 | Phase 3 M1 |
| v0.2 | + 季节性因子 + 补货计算 + 飞书推送 | Phase 3 M2 |
| v0.3 | + 仓储成本优化 + 多SKU合并发货建议 | Phase 3 M3 |
| v1.0 | + 全链路物流跟踪 + 自动下补货单 | Phase 3 M4 |
| v2.0 | + ML预测模型 + 多站点库存协调 + 供应链可视化 | Phase 4 |

---

*本文档定义了库存预测 Agent 的完整设计，代码实现见 `ai-agent-prototype/src/agents/inventory_forecast.py`*

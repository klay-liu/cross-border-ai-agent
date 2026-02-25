# 智能选品 Agent 详细设计

**版本**: v1.0
**日期**: 2026-02-25
**优先级**: P0 — Phase 1 核心模块

---

## 一、Agent 定位

### 1.1 核心使命

将选品从「人工经验驱动」转变为「数据+AI 驱动」：

```
传统选品流程（3-5天/次）:
人工刷Amazon → 凭经验筛选 → Excel记录 → 拍脑袋决策

Agent选品流程（2-4小时/次）:
关键词输入 → 自动扫描1000+ SKU → 多维评分 → 工厂匹配 → 生成报告 → 人审批
```

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| **关键词发现** | 从种子关键词扩展长尾词，发现潜在蓝海品类 |
| **市场扫描** | 批量采集搜索结果、价格、评分、销量、BSR |
| **竞争度评估** | 评估头部集中度、进入壁垒、差异化空间 |
| **差评痛点挖掘** | NLP 分析 1-3 星评论，提取可改进的产品痛点 |
| **利润率测算** | 自动计算 FBA 费用、佣金、头程，输出利润率 |
| **工厂匹配** | 对照工厂产品目录，评估可生产性 |
| **综合评分** | 多维度加权打分，输出排序的候选列表 |

---

## 二、选品漏斗模型

```
                    ┌─────────────────────────┐
                    │   Level 1: 关键词发现     │
                    │   输入种子词 → 扩展长尾    │
                    │   产出: 50-100 个关键词    │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │   Level 2: 市场扫描       │
                    │   每个关键词 Top 20 产品   │
                    │   产出: 500-2000 SKU      │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │   Level 3: 初筛过滤       │
                    │   规则引擎硬过滤          │
                    │   产出: 100-300 SKU       │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │   Level 4: 深度分析       │
                    │   LLM 分析差评+竞争格局   │
                    │   产出: 20-50 候选品      │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │   Level 5: 综合评分       │
                    │   多维打分+工厂匹配       │
                    │   产出: Top 10 推荐       │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │   Level 6: 人工审批       │
                    │   运营者最终决策          │
                    │   产出: 3-5 确认 SKU      │
                    └─────────────────────────┘
```

---

## 三、各层级详细设计

### 3.1 Level 1: 关键词发现

**输入**: 种子关键词（如 "spring replacement", "U bolt stainless steel"）

**扩展策略**:

| 策略 | 方法 | 示例 |
|------|------|------|
| 场景扩展 | LLM 推理使用场景 | spring → trash can spring, door spring, sofa spring |
| 材质扩展 | 枚举材质变体 | U bolt → 304 SS U bolt, galvanized U bolt |
| 规格扩展 | 枚举尺寸规格 | M6 U bolt, M8 U bolt, 1/4" U bolt |
| Amazon 联想 | 采集搜索联想词 | 输入 "spring" → Amazon 返回的联想建议 |
| 竞品关键词 | 从竞品 Listing 反向提取 | 分析 Top 卖家的标题/后台关键词 |

**输出**: 关键词列表 + 预估搜索量 + 品类归属

### 3.2 Level 2: 市场扫描

**对每个关键词执行**:

```python
scan_result = {
    "keyword": "trash can spring replacement",
    "total_results": 880,
    "top_products": [
        {
            "asin": "B0XXXXXX",
            "title": "5 Pcs Universal Adjustable 3-Coil Torsion Springs",
            "price": 7.99,
            "rating": 4.4,
            "review_count": 11,
            "bsr_rank": 45632,
            "monthly_sales_est": 150,
            "brand": "Cilky",
            "seller_country": "CN",
            "fba": True,
            "image_url": "...",
            "listing_date": "2024-06-15"
        },
        # ... top 20
    ]
}
```

### 3.3 Level 3: 初筛过滤（规则引擎，不消耗 LLM token）

**硬性过滤规则**:

```python
FILTER_RULES = {
    # 需求信号
    "min_monthly_sales": 100,         # 月销 ≥ 100（证明有需求）
    "min_search_results": 200,        # 搜索结果 ≥ 200（市场存在）
    "max_search_results": 50000,      # 搜索结果 ≤ 50000（避免红海）

    # 竞争度
    "max_top1_review_count": 2000,    # 头部评论数 ≤ 2000（可追赶）
    "max_top1_monthly_sales": 10000,  # 头部月销 ≤ 10000（非垄断）
    "max_avg_rating": 4.5,            # 平均评分 ≤ 4.5（有改进空间）

    # 利润空间
    "min_price": 6.0,                 # 售价 ≥ $6（覆盖FBA费用）
    "max_price": 50.0,                # 售价 ≤ $50（五金配件定位）
    "min_estimated_margin": 0.15,     # 预估毛利率 ≥ 15%

    # 红线排除
    "exclude_categories": [            # 排除品类
        "Electronics", "Toys", "Food"
    ],
    "exclude_brands_dominant": True,   # 排除品牌集中度 CR3 > 70%
    "exclude_seasonal": True,          # 排除季节性产品
    "exclude_certification_needed": [  # 排除需认证的
        "UL", "CE", "FCC", "FDA"
    ]
}
```

### 3.4 Level 4: 深度分析（LLM 驱动）

**对通过初筛的候选品，进行两个维度的深度分析**:

#### A. 差评痛点挖掘

```
System Prompt:
你是一位跨境电商产品分析专家。你需要分析 Amazon 产品的 1-3 星差评，
提取用户的核心痛点，并评估这些痛点是否可以通过产品改进来解决。

分析维度：
1. 质量问题（材质、耐用性、做工）
2. 尺寸/规格问题（不匹配、尺寸偏差）
3. 包装问题（数量不足、缺件、破损）
4. 功能问题（不好用、不符合预期）
5. 说明问题（没有说明书、规格不清楚）

对每个痛点评估：
- 出现频率（高/中/低）
- 改进可行性（容易/中等/困难）
- 改进后的竞争优势（强/中/弱）
```

**输出格式**:

```json
{
    "asin": "B0XXXXXX",
    "total_reviews_analyzed": 35,
    "pain_points": [
        {
            "category": "尺寸/规格",
            "description": "弹簧尺寸不匹配大多数垃圾桶型号",
            "frequency": "高",
            "example_reviews": ["Didn't fit my Simple Human...", "Too small for..."],
            "improvability": "中等",
            "improvement_suggestion": "提供多尺寸套装或可调节弹簧",
            "competitive_advantage": "强"
        },
        {
            "category": "质量",
            "description": "弹力不足，几个月后失去弹性",
            "frequency": "中",
            "example_reviews": ["Lost tension after 3 months..."],
            "improvability": "容易",
            "improvement_suggestion": "使用更高品质的304不锈钢线材，加粗线径",
            "competitive_advantage": "强"
        }
    ],
    "overall_opportunity": "该品类差评集中在规格匹配和耐用性，均可通过工厂改进解决"
}
```

#### B. 竞争格局分析

```
System Prompt:
你是跨境电商市场分析专家。基于以下产品数据，分析该细分市场的竞争格局，
评估新卖家进入的可行性和建议策略。

分析维度：
1. 市场集中度（CR3/CR5）
2. 头部卖家特征（品牌力、评论壁垒、价格策略）
3. 新品机会窗口（近6个月是否有新品冲到前10）
4. 价格带分布和空白
5. 差异化切入点
```

### 3.5 Level 5: 综合评分模型

```python
SCORING_WEIGHTS = {
    "demand_score": 0.20,          # 需求强度（搜索量、月销量）
    "competition_score": 0.25,     # 竞争可行性（越低越好的竞争度）
    "profit_score": 0.20,          # 利润空间
    "improvement_score": 0.15,     # 差评改进空间
    "factory_match_score": 0.10,   # 工厂匹配度
    "trend_score": 0.10,           # 趋势方向（上升/稳定/下降）
}

# 各维度评分标准（0-100）

demand_scoring = {
    "monthly_sales_avg >= 500": 90,
    "monthly_sales_avg >= 200": 70,
    "monthly_sales_avg >= 100": 50,
    "monthly_sales_avg < 100": 20,
}

competition_scoring = {
    "top1_reviews < 50 and no_best_seller": 95,   # 蓝海
    "top1_reviews < 200 and avg_rating < 4.3": 80, # 有机会
    "top1_reviews < 500": 60,                       # 中等竞争
    "top1_reviews < 1000": 40,                      # 较难
    "top1_reviews >= 1000": 15,                     # 红海
}

profit_scoring = {
    "estimated_margin >= 40%": 95,
    "estimated_margin >= 30%": 80,
    "estimated_margin >= 20%": 60,
    "estimated_margin >= 15%": 40,
    "estimated_margin < 15%": 15,
}

factory_match_scoring = {
    "can_produce_directly": 100,        # 工厂直接生产
    "minor_modification_needed": 80,    # 小改动可做
    "need_new_mold": 50,               # 需要开模
    "need_external_sourcing": 30,      # 需要外部采购
    "cannot_produce": 0,               # 无法生产
}
```

### 3.6 Level 6: 输出报告模板

```markdown
# 选品分析报告

**生成时间**: 2026-02-25 14:30
**分析范围**: 五金弹簧替换件
**扫描关键词数**: 45
**扫描SKU数**: 876
**通过初筛**: 124
**深度分析**: 38
**最终推荐**: Top 10

---

## 推荐排名

| # | 关键词/品类 | 代表ASIN | 综合评分 | 月销量 | 售价 | 预估利润率 | 工厂匹配 | 核心机会 |
|---|-----------|---------|---------|--------|------|-----------|---------|---------|
| 1 | trash can lid spring | B0XXX | 87.5 | 150 | $7.99 | 28% | ✅直产 | 差评多，品质提升空间大 |
| 2 | recliner spring kit | B0YYY | 82.3 | 220 | $12.99 | 32% | ✅直产 | 无头部卖家，蓝海 |
| ...

## Top 1 详细分析

### trash can lid spring replacement

**市场概况**:
- 搜索结果: 880
- 头部月销: 150 套
- 头部评分: 4.4 (11条评论)
- 市场集中度: CR3 = 35%（分散）

**差评痛点 Top 3**:
1. 尺寸不匹配 (出现率 45%) → 改进方案：多尺寸套装
2. 弹力不足 (出现率 30%) → 改进方案：加粗线径
3. 安装困难 (出现率 15%) → 改进方案：附安装视频二维码

**利润测算**:
- 建议售价: $8.99 (5件套)
- 生产成本: ¥4.5 ≈ $0.63
- 头程物流: $0.40
- FBA费用: $3.24
- 佣金(15%): $1.35
- **预估净利: $3.37 → 毛利率 37.5%**

**工厂匹配**: ✅ 弹簧系列 → 扭簧系列，工厂可直接生产
**建议**: ⭐⭐⭐⭐⭐ 强烈推荐，首批测试100套
```

---

## 四、工厂产品匹配引擎

### 4.1 工厂产品目录建模

基于现有工厂产品线（来自「生产产品.md」），构建结构化目录：

```python
FACTORY_CATALOG = {
    "弹簧系列": {
        "capability": ["压簧", "拉簧", "扭簧", "门簧", "塔簧", "扁簧", "电池弹簧"],
        "materials": ["304不锈钢", "65Mn弹簧钢", "碳钢"],
        "size_range": "线径0.3-6mm, 长度5-1000mm",
        "moq": 100,
        "lead_time_days": 7,
        "can_customize": True,
        "amazon_mapping": [
            "trash can spring", "door spring", "recliner spring",
            "compression spring kit", "torsion spring", "extension spring"
        ]
    },
    "304螺栓": {
        "capability": ["杯头内六角", "全牙外六角", "沉头内六角", "U型螺栓", "蝶形螺栓"],
        "materials": ["304不锈钢", "316不锈钢"],
        "size_range": "M3-M20",
        "moq": 500,
        "lead_time_days": 10,
        "can_customize": True,
        "amazon_mapping": [
            "stainless steel U bolt", "hex bolt kit", "socket cap screw",
            "butterfly bolt", "marine U bolt"
        ]
    },
    "吊具锁具": {
        "capability": ["万向旋转环", "S型挂钩", "吊环螺钉", "万向旋转钩", "D型扣", "三角环"],
        "materials": ["304不锈钢", "316不锈钢"],
        "size_range": "承重50-2000kg",
        "moq": 200,
        "lead_time_days": 7,
        "can_customize": True,
        "amazon_mapping": [
            "S hook heavy duty", "swivel hook", "hammock hardware",
            "swing hook", "D ring", "eye bolt"
        ]
    },
    "螺母垫圈": {
        "capability": ["六角螺母", "防松螺母", "蝶形螺母", "法兰螺母", "弹垫圈", "平垫圈"],
        "materials": ["304不锈钢"],
        "size_range": "M3-M20",
        "moq": 1000,
        "lead_time_days": 5,
        "can_customize": False,
        "amazon_mapping": [
            "hex nut kit", "lock nut", "washer assortment",
            "wing nut", "flange nut"
        ]
    },
    "挡圈卡簧": {
        "capability": ["轴用卡簧", "孔用卡簧", "E型卡簧"],
        "materials": ["65Mn", "304不锈钢"],
        "size_range": "内径3-80mm",
        "moq": 500,
        "lead_time_days": 7,
        "can_customize": True,
        "amazon_mapping": [
            "snap ring kit", "retaining ring assortment", "E-clip kit",
            "circlip set"
        ]
    },
    "销轴铆钉": {
        "capability": ["捷花轴", "抽芯铆钉", "圆钉", "子母钉"],
        "materials": ["304不锈钢", "铝合金"],
        "size_range": "直径2-6mm",
        "moq": 1000,
        "lead_time_days": 5,
        "can_customize": False,
        "amazon_mapping": [
            "rivet kit", "blind rivet assortment", "clevis pin"
        ]
    }
}
```

### 4.2 匹配算法

```python
def match_factory_capability(product_description: str, product_specs: dict) -> MatchResult:
    """
    匹配逻辑：
    1. 关键词匹配：产品描述 vs amazon_mapping 关键词
    2. 材质匹配：产品要求 vs 工厂可用材质
    3. 规格匹配：产品尺寸 vs 工厂能力范围
    4. LLM 辅助判断：边界情况由 LLM 判断可行性
    """
    # Step 1: 关键词粗匹配
    matched_categories = keyword_match(product_description)

    # Step 2: 规格精匹配
    for cat in matched_categories:
        if spec_in_range(product_specs, FACTORY_CATALOG[cat]):
            return MatchResult(
                match_level="direct",  # 可直接生产
                category=cat,
                confidence=0.95
            )

    # Step 3: LLM 判断边界情况
    llm_result = llm_assess_producibility(product_description, matched_categories)
    return llm_result
```

---

## 五、调度与运行策略

### 5.1 运行模式

| 模式 | 触发方式 | 频率 | 场景 |
|------|---------|------|------|
| **手动选品** | CLI 命令 / 飞书指令 | 按需 | 主动探索新品类 |
| **定时扫描** | Cron 定时任务 | 每周一次 | 持续发现新机会 |
| **事件触发** | 市场洞察 Agent 通知 | 自动 | 发现趋势后自动分析 |

### 5.2 成本控制

| 环节 | LLM 调用 | 预估 Token | 单次成本 |
|------|---------|-----------|---------|
| 关键词扩展 | 1 次 Sonnet | ~2K | $0.006 |
| 市场扫描 | 0（纯 API） | 0 | $0 |
| 初筛过滤 | 0（规则引擎） | 0 | $0 |
| 差评分析 ×20 品 | 20 次 Sonnet | ~40K | $0.12 |
| 竞争格局分析 | 1 次 Sonnet | ~5K | $0.015 |
| 综合评分+报告 | 1 次 Sonnet | ~3K | $0.009 |
| **单次选品总计** | **~23 次** | **~50K** | **~$0.15** |

---

## 六、迭代路线

| 版本 | 能力 | 阶段 |
|------|------|------|
| v0.1 | 关键词搜索 + 基础数据采集 + 规则初筛 | Phase 1 M1 |
| v0.2 | + 差评分析 + 利润计算 + 工厂匹配 | Phase 1 M2 |
| v0.3 | + 综合评分 + 报告生成 + 飞书推送 | Phase 1 M3 |
| v1.0 | + 历史数据学习 + 选品成功率追踪 | Phase 2 |
| v2.0 | + 自动发现新品类 + 跨站点分析 | Phase 3 |

---

*本文档定义了智能选品 Agent 的完整设计，代码实现见 `ai-agent-prototype/src/agents/product_scout.py`*

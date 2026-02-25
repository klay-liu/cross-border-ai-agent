# 智能客服 Agent 详细设计

**版本**: v1.0
**日期**: 2026-02-26
**优先级**: P2 — Phase 2

---

## 一、Agent 定位

### 1.1 核心使命

将客服从「人工逐条回复」转变为「AI 自动处理 + 人工兜底」，实现 24 小时响应：

```
传统客服流程:
买家消息 → 人工查看(平均6-12h) → 手动回复 → 遗漏/延迟 → 差评/A-to-Z

Agent 客服流程:
买家消息 → 自动分类(秒级) → 模板+AI生成回复 → 人工审核(可选) → 自动发送
                                                      ↓
                                               复杂case → 升级人工
```

### 1.2 核心能力矩阵

| 能力 | 说明 | 数据源 |
|------|------|--------|
| **消息分类** | 自动识别消息类型：咨询/投诉/退换货/物流/评论 | Amazon Buyer Messages |
| **自动回复** | 基于分类和上下文生成专业回复 | LLM + 回复模板库 |
| **评论回复** | 对差评/好评自动生成合规的卖家回复 | Amazon Reviews |
| **退换货自动化** | 根据规则自动处理退换货请求 | Amazon Returns API |
| **升级机制** | 识别高风险 case 自动升级人工处理 | 规则引擎 + LLM 判断 |
| **客服报表** | 统计响应时间、处理量、满意度等指标 | 综合 |

---

## 二、消息优先级与 SLA

### 2.1 优先级定义

| 优先级 | 类型 | 响应 SLA | 处理方式 |
|--------|------|----------|---------|
| **P0 紧急** | A-to-Z Claim / 平台警告 | ≤ 2 小时 | 立即升级人工 + 飞书告警 |
| **P1 高** | 退换货请求 / 产品缺陷投诉 | ≤ 6 小时 | AI 生成方案 + 人工审核 |
| **P2 中** | 售前咨询 / 物流查询 | ≤ 12 小时 | AI 自动回复 |
| **P3 低** | 感谢/好评/一般问题 | ≤ 24 小时 | AI 自动回复 |

### 2.2 24 小时 SLA 合规策略

```python
SLA_CONFIG = {
    "max_response_time_hours": 24,      # Amazon 要求 24h 内回复
    "target_response_time_hours": 6,     # 内部目标 6h
    "auto_reply_enabled": True,          # 开启自动回复
    "human_review_required": {
        "P0": True,                      # P0 必须人工审核
        "P1": True,                      # P1 必须人工审核
        "P2": False,                     # P2 可自动发送
        "P3": False,                     # P3 可自动发送
    },
    "escalation_channels": ["feishu", "sms"],  # 升级通知渠道
}
```

---

## 三、工作流程

```
买家消息/评论到达
    │
    ▼
┌─────────────────────────────────────┐
│ Step 1: 消息分类                     │
│ 规则引擎预分类 + LLM 精分类          │
│ 输出: 类型 + 优先级 + 情绪分数       │
└──────────┬──────────────────────────┘
           │
     ┌─────┴─────────────────┐
     │                       │
     ▼                       ▼
┌──────────┐          ┌──────────────┐
│ P0/P1    │          │ P2/P3        │
│ 高优先级  │          │ 常规消息      │
└────┬─────┘          └──────┬───────┘
     │                       │
     ▼                       ▼
┌──────────┐          ┌──────────────┐
│ 飞书告警  │          │ AI 自动生成   │
│ 升级人工  │          │ 回复内容      │
└────┬─────┘          └──────┬───────┘
     │                       │
     ▼                       ▼
┌──────────┐          ┌──────────────┐
│ AI 生成   │          │ 合规性检查    │
│ 参考回复  │          │ 敏感词过滤    │
└────┬─────┘          └──────┬───────┘
     │                       │
     ▼                       ▼
┌──────────┐          ┌──────────────┐
│ 人工审核  │          │ 自动发送      │
│ 修改+发送 │          │ 记录日志      │
└──────────┘          └──────────────┘
```

---

## 四、消息分类引擎

### 4.1 分类体系

```python
MESSAGE_CATEGORIES = {
    "inquiry": {
        "sub_types": [
            "product_spec",       # 产品规格咨询
            "compatibility",      # 兼容性咨询
            "shipping_time",      # 物流时间咨询
            "stock_availability", # 库存咨询
            "bulk_order",         # 批量订单咨询
        ],
        "priority": "P2",
        "auto_reply": True,
    },
    "complaint": {
        "sub_types": [
            "product_defect",     # 产品缺陷
            "wrong_item",         # 发错货
            "missing_parts",      # 缺件
            "not_as_described",   # 与描述不符
            "quality_issue",      # 质量问题
        ],
        "priority": "P1",
        "auto_reply": False,    # 需人工审核
    },
    "return_exchange": {
        "sub_types": [
            "return_request",     # 退货请求
            "exchange_request",   # 换货请求
            "refund_inquiry",     # 退款咨询
        ],
        "priority": "P1",
        "auto_reply": False,
    },
    "shipping": {
        "sub_types": [
            "tracking_inquiry",   # 物流追踪
            "delivery_issue",     # 配送问题
            "address_change",     # 地址修改
            "lost_package",       # 包裹丢失
        ],
        "priority": "P2",
        "auto_reply": True,
    },
    "review_response": {
        "sub_types": [
            "negative_review",    # 差评(1-3星)
            "positive_review",    # 好评(4-5星)
            "review_with_issue",  # 带问题的评论
        ],
        "priority": "P2",
        "auto_reply": True,
    },
    "critical": {
        "sub_types": [
            "a_to_z_claim",       # A-to-Z 索赔
            "ip_complaint",       # 知识产权投诉
            "safety_report",      # 安全问题报告
            "platform_warning",   # 平台警告
        ],
        "priority": "P0",
        "auto_reply": False,    # 必须人工处理
    }
}
```

### 4.2 分类 Prompt

```
你是一个 Amazon 卖家客服消息分类器。根据消息内容判断类型和优先级。

消息内容:
{message_content}

订单信息(如有):
{order_context}

请输出 JSON:
{
    "category": "inquiry|complaint|return_exchange|shipping|review_response|critical",
    "sub_type": "具体子类型",
    "priority": "P0|P1|P2|P3",
    "sentiment": "positive|neutral|negative|angry",
    "sentiment_score": 0.0-1.0,
    "key_issue": "核心问题一句话总结",
    "requires_order_lookup": true/false,
    "suggested_action": "建议的处理动作"
}
```

---

## 五、退换货自动化规则

### 5.1 成本优化决策树

```python
RETURN_RULES = {
    "refund_no_return": {
        # 仅退款不退货（节省逆向物流成本）
        "conditions": [
            "item_price < 15.00",              # 商品价值 < $15
            "order_age_days <= 30",             # 订单30天内
            "customer_lifetime_claims <= 2",    # 该客户历史索赔 ≤ 2次
        ],
        "action": "full_refund",
        "message": "已为您安排全额退款，无需退回商品。"
    },
    "partial_refund": {
        # 部分退款（客户满意度 + 成本平衡）
        "conditions": [
            "item_price >= 15.00 AND item_price < 30.00",
            "complaint_type IN ('missing_parts', 'minor_defect')",
        ],
        "action": "partial_refund_50pct",
        "message": "已为您安排50%退款补偿，如需完整退款请退回商品。"
    },
    "standard_return": {
        # 标准退货流程
        "conditions": [
            "item_price >= 30.00",
            "OR customer_lifetime_claims > 2",
        ],
        "action": "generate_return_label",
        "message": "已生成退货标签，请在14天内退回商品。"
    },
    "replacement": {
        # 补发（针对缺件/损坏）
        "conditions": [
            "complaint_type IN ('missing_parts', 'damaged_in_transit')",
            "replacement_cost < item_price * 0.3",
        ],
        "action": "send_replacement",
        "message": "已为您安排补发，预计3-5个工作日送达。"
    }
}
```

### 5.2 退换货流程图

```
退换货请求到达
    │
    ▼
┌──────────────────┐
│ 查询订单信息      │
│ 商品价格/订单时间  │
│ 客户历史记录      │
└────────┬─────────┘
         │
         ▼
    商品价值 < $15?
    ┌────┴────┐
   YES       NO
    │         │
    ▼         ▼
┌────────┐  $15-$30 且缺件/小缺陷?
│仅退款   │  ┌────┴────┐
│不退货   │ YES       NO
└────────┘  │         │
            ▼         ▼
       ┌────────┐ ┌────────┐
       │50%退款  │ │标准退货 │
       │补偿    │ │流程    │
       └────────┘ └────────┘
```

---

## 六、Prompt 设计

### 6.1 自动回复生成 Prompt

```
你是 {brand_name} 品牌的 Amazon 客服代表。请基于以下信息生成专业、友好的回复。

消息分类: {category}
买家消息: {buyer_message}
订单信息: {order_info}
产品信息: {product_info}

回复要求:
1. 语气: 专业、友好、有同理心
2. 结构: 致歉/感谢 → 解决方案 → 后续步骤
3. 长度: 50-150词
4. 合规: 不包含外部链接、不引导站外交易、不提及竞品
5. 不使用 "Dear friend" 等不专业称呼
6. 使用 "Hi {buyer_name}" 开头

禁止内容:
- 不提供个人联系方式
- 不承诺 Amazon 政策之外的内容
- 不使用过度道歉或卑微语气
- 不暗示或明示好评激励
```

### 6.2 差评回复 Prompt

```
你是 {brand_name} 品牌的 Amazon 卖家。请对以下差评生成公开回复。

评论内容: {review_text}
评分: {star_rating}/5
产品: {product_name}

回复策略:
1. 感谢买家反馈（不要说"sorry for the inconvenience"这种套话）
2. 针对具体问题给出解决方案或解释
3. 提供联系方式邀请进一步沟通
4. 展示品牌的专业性和负责任态度
5. 长度: 50-100词

合规要求:
- 不提及退款/补偿（避免被认为是收买好评）
- 不否认或辩解客户体验
- 不泄露订单/客户隐私信息
```

---

## 七、Amazon 消息政策合规

### 7.1 合规约束

```python
COMPLIANCE_RULES = {
    "prohibited_content": [
        "external_links",            # 禁止外部链接
        "marketing_promotions",      # 禁止营销推广
        "review_solicitation",       # 禁止索评
        "competitor_mention",        # 禁止提及竞品
        "off_platform_transaction",  # 禁止引导站外交易
        "personal_contact_info",     # 禁止个人联系方式
    ],
    "required_elements": [
        "respond_to_buyer_question", # 必须回应买家问题
        "professional_tone",         # 专业语气
    ],
    "response_limits": {
        "max_proactive_messages": 1, # 每个订单最多主动联系1次
        "allowed_proactive_types": [
            "shipping_confirmation",
            "delivery_issue_resolution",
        ],
    }
}
```

### 7.2 合规检查流程

```python
def compliance_check(reply_text: str) -> ComplianceResult:
    """
    发送前的合规性检查
    """
    violations = []

    # 1. 外部链接检测
    if re.search(r'https?://(?!www\.amazon\.)', reply_text):
        violations.append("external_link_detected")

    # 2. 敏感词检测
    sensitive_words = ["review", "feedback", "5 star", "positive",
                       "discount", "coupon", "free gift"]
    for word in sensitive_words:
        if word.lower() in reply_text.lower():
            violations.append(f"sensitive_word: {word}")

    # 3. 个人信息检测
    if re.search(r'[\w\.-]+@[\w\.-]+\.\w+', reply_text):
        violations.append("personal_email_detected")
    if re.search(r'\+?\d{10,}', reply_text):
        violations.append("phone_number_detected")

    return ComplianceResult(
        is_compliant=len(violations) == 0,
        violations=violations
    )
```

---

## 八、数据模型

### 8.1 客服消息记录

```python
class CustomerMessage:
    message_id: str               # 消息唯一ID
    order_id: str                 # 关联订单号
    asin: str                     # 关联ASIN
    buyer_id: str                 # 买家ID
    message_type: str             # 消息类型(buyer/seller/system)
    category: str                 # 分类结果
    sub_type: str                 # 子类型
    priority: str                 # 优先级(P0-P3)
    sentiment: str                # 情绪
    sentiment_score: float        # 情绪分数
    original_text: str            # 原始消息
    reply_text: str               # 回复内容
    reply_method: str             # 回复方式(auto/human/hybrid)
    response_time_minutes: int    # 响应时间(分钟)
    resolved: bool                # 是否已解决
    escalated: bool               # 是否升级
    created_at: datetime          # 创建时间
    replied_at: datetime          # 回复时间
```

### 8.2 退换货记录

```python
class ReturnRecord:
    return_id: str                # 退换货ID
    order_id: str                 # 订单号
    asin: str                     # ASIN
    return_reason: str            # 退货原因
    item_price: float             # 商品价格
    handling_method: str          # 处理方式
    refund_amount: float          # 退款金额
    replacement_sent: bool        # 是否补发
    cost_saved: float             # 相比标准退货节省的成本
    customer_satisfied: bool      # 客户是否满意
    created_at: datetime          # 创建时间
```

---

## 九、成本控制

| 环节 | LLM 调用 | 预估 Token | 月度成本 |
|------|---------|-----------|---------|
| 消息分类 (~50条/天) | Haiku ×50/天 | ~25K/天 | ~$2.25 |
| P2/P3 自动回复 (~30条/天) | Haiku ×30/天 | ~30K/天 | ~$2.70 |
| P1 参考回复 (~5条/天) | Sonnet ×5/天 | ~10K/天 | ~$0.90 |
| 评论回复 (~3条/天) | Sonnet ×3/天 | ~6K/天 | ~$0.54 |
| **月度合计** | | | **~$6.39** |

---

## 十、迭代路线

| 版本 | 能力 | 阶段 |
|------|------|------|
| v0.1 | 消息分类 + 模板回复 + 基础合规检查 | Phase 2 M1 |
| v0.2 | + AI 生成回复 + 退换货自动化规则 | Phase 2 M2 |
| v0.3 | + 评论自动回复 + 升级机制 + 飞书告警 | Phase 2 M3 |
| v1.0 | + 客服报表 + 满意度追踪 + 多语言支持 | Phase 2 M4 |
| v2.0 | + 主动客服(发货通知) + 客户画像 + 预测性服务 | Phase 3 |

---

*本文档定义了智能客服 Agent 的完整设计，代码实现见 `ai-agent-prototype/src/agents/customer_service.py`*

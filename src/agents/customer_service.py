"""
智能客服 Agent - 多语言客户服务与工单自动化

功能：
1. 买家消息自动分类（咨询/投诉/退换货/物流/差评）
2. 智能回复生成（模板+LLM 混合）
3. 差评自动回复与申诉建议
4. 退换货流程自动化
5. 升级机制（自动判断是否需要人工介入）
6. 客服数据统计与分析
"""
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.agents.base_agent import BaseAgent, ToolResult
from src.config.prompts import (
    CUSTOMER_SERVICE_SYSTEM,
    CUSTOMER_REPLY_PROMPT,
    REVIEW_RESPONSE_PROMPT,
)
from src.config.settings import REPORTS_DIR


@dataclass
class Ticket:
    """客服工单"""
    ticket_id: str
    order_id: str
    customer_name: str
    message_type: str  # inquiry / complaint / return / shipping / review
    priority: str  # P0 / P1 / P2 / P3
    status: str  # open / in_progress / resolved / escalated
    original_message: str
    reply: str = ""
    action: str = ""
    created_at: str = ""
    resolved_at: str = ""
    escalated: bool = False
    escalate_reason: str = ""


class CustomerServiceAgent(BaseAgent):
    """智能客服 Agent"""

    def __init__(self):
        super().__init__(
            name="CustomerService",
            system_prompt=CUSTOMER_SERVICE_SYSTEM,
        )
        self.tickets: List[Ticket] = []
        self._ticket_counter = 0

    def _register_tools(self):
        """注册客服 Agent 的可用工具"""

        self.register_tool(
            name="classify_message",
            description="对买家消息进行分类，判断消息类型和优先级",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "买家消息内容"},
                    "order_id": {"type": "string", "description": "订单号"},
                },
                "required": ["message"],
            },
            handler=self._tool_classify_message,
        )

        self.register_tool(
            name="generate_reply",
            description="基于消息类型和上下文生成回复",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "买家消息"},
                    "message_type": {"type": "string", "description": "消息类型"},
                    "order_id": {"type": "string", "description": "订单号"},
                    "product_name": {"type": "string", "description": "产品名称"},
                },
                "required": ["message", "message_type"],
            },
            handler=self._tool_generate_reply,
        )

        self.register_tool(
            name="handle_return_request",
            description="处理退换货请求，计算成本并给出建议方案",
            input_schema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "reason": {"type": "string", "description": "退货原因"},
                    "order_amount": {"type": "number", "description": "订单金额"},
                    "days_since_purchase": {"type": "integer", "description": "购买天数"},
                },
                "required": ["order_id", "reason", "order_amount"],
            },
            handler=self._tool_handle_return,
        )

        self.register_tool(
            name="respond_to_review",
            description="生成差评回复",
            input_schema={
                "type": "object",
                "properties": {
                    "rating": {"type": "integer", "description": "评分1-5"},
                    "review_title": {"type": "string"},
                    "review_content": {"type": "string"},
                    "product_name": {"type": "string"},
                },
                "required": ["rating", "review_content", "product_name"],
            },
            handler=self._tool_respond_review,
        )

        self.register_tool(
            name="get_ticket_stats",
            description="获取客服工单统计数据",
            input_schema={
                "type": "object",
                "properties": {},
            },
            handler=self._tool_get_stats,
        )

    # ============================================================
    # 工具实现
    # ============================================================

    def _tool_classify_message(self, message: str, order_id: str = "") -> dict:
        """消息分类"""
        message_lower = message.lower()

        # 基于关键词的规则分类
        if any(w in message_lower for w in ["refund", "return", "exchange", "money back", "send back"]):
            msg_type = "return"
            priority = "P1"
        elif any(w in message_lower for w in ["broken", "damaged", "defective", "wrong", "not working", "poor quality"]):
            msg_type = "complaint"
            priority = "P0"
        elif any(w in message_lower for w in ["where", "tracking", "shipped", "delivery", "when will"]):
            msg_type = "shipping"
            priority = "P2"
        elif any(w in message_lower for w in ["a-to-z", "claim", "dispute"]):
            msg_type = "complaint"
            priority = "P0"
        elif any(w in message_lower for w in ["size", "compatible", "fit", "dimension", "how to"]):
            msg_type = "inquiry"
            priority = "P2"
        else:
            msg_type = "inquiry"
            priority = "P3"

        # 判断是否需要升级
        escalate = priority == "P0" and any(
            w in message_lower for w in ["a-to-z", "lawyer", "legal", "bbb", "report"]
        )

        return {
            "message_type": msg_type,
            "priority": priority,
            "escalate": escalate,
            "escalate_reason": "客户提及法律/投诉渠道，建议人工处理" if escalate else "",
            "confidence": 0.85,
        }

    def _tool_generate_reply(self, message: str, message_type: str,
                              order_id: str = "", product_name: str = "") -> dict:
        """生成回复"""
        templates = {
            "inquiry": (
                "Thank you for reaching out! {answer} "
                "If you have any other questions, please don't hesitate to ask. "
                "We're here to help!"
            ),
            "complaint": (
                "We sincerely apologize for the inconvenience you've experienced. "
                "We take quality issues very seriously. {solution} "
                "Please don't hesitate to contact us directly so we can make this right."
            ),
            "return": (
                "We're sorry to hear that the product didn't meet your expectations. "
                "{solution} "
                "Please let us know how you'd like to proceed, and we'll take care of it right away."
            ),
            "shipping": (
                "Thank you for your inquiry about your order. "
                "{answer} "
                "If you need any further assistance, please let us know!"
            ),
        }

        # 基于消息类型选择模板并填充
        template = templates.get(message_type, templates["inquiry"])
        message_lower = message.lower()

        if message_type == "complaint":
            solution = (
                "We'd like to offer you a replacement or a full refund — whichever you prefer."
            )
            action = "offer_replacement_or_refund"
        elif message_type == "return":
            solution = (
                "We can process a full refund for you. No need to return the item — "
                "please keep it or donate it."
            )
            action = "process_refund_no_return"
        elif message_type == "shipping":
            answer = (
                "Your order is currently being processed and should arrive within "
                "3-5 business days. You can track your package using the tracking "
                "number in your order details."
            )
            action = "provide_tracking"
        else:
            answer = (
                "Great question! Our product is made from premium stainless steel "
                "and comes in multiple sizes to fit various applications. "
                "Please check the product description for detailed specifications."
            )
            action = "answer_inquiry"

        reply = template.format(
            answer=locals().get("answer", ""),
            solution=locals().get("solution", ""),
        )

        return {
            "reply": reply,
            "action": action,
            "message_type": message_type,
            "auto_generated": True,
        }

    def _tool_handle_return(self, order_id: str, reason: str,
                             order_amount: float, days_since_purchase: int = 30) -> dict:
        """处理退换货"""
        # 成本计算
        return_shipping_cost = 5.0  # 预估退货运费
        restocking_fee = 0.0

        # 策略判断
        if order_amount < 15.0:
            # 低价产品直接退款不退货（成本考虑）
            strategy = "refund_no_return"
            refund_amount = order_amount
            recommendation = "产品金额较低，退款不退货更经济"
        elif days_since_purchase > 30:
            # 超过30天，部分退款
            strategy = "partial_refund"
            refund_amount = round(order_amount * 0.7, 2)
            recommendation = "超过30天退货窗口，建议部分退款70%"
        elif "defective" in reason.lower() or "broken" in reason.lower():
            # 质量问题，全额退款
            strategy = "full_refund_no_return"
            refund_amount = order_amount
            recommendation = "质量问题，全额退款+不退货，维护客户关系"
        else:
            strategy = "standard_return"
            refund_amount = order_amount
            recommendation = "标准退换货流程"

        return {
            "order_id": order_id,
            "strategy": strategy,
            "refund_amount": refund_amount,
            "return_required": strategy == "standard_return",
            "estimated_cost": return_shipping_cost if strategy == "standard_return" else 0,
            "recommendation": recommendation,
            "reply_template": (
                f"We apologize for the issue. We'd like to process a "
                f"{'full' if refund_amount == order_amount else 'partial'} refund "
                f"of ${refund_amount:.2f}. "
                f"{'No need to return the item.' if 'no_return' in strategy else 'Please ship the item back using the prepaid label.'}"
            ),
        }

    def _tool_respond_review(self, rating: int, review_content: str,
                              product_name: str, review_title: str = "") -> dict:
        """生成差评回复"""
        if rating <= 2:
            reply = (
                f"We're truly sorry about your experience with our {product_name}. "
                f"This is not the quality standard we strive for. "
                f"Please contact us directly through Amazon messaging — "
                f"we'd love the opportunity to make this right with a replacement "
                f"or full refund. Your satisfaction matters most to us."
            )
            urgency = "high"
        elif rating == 3:
            reply = (
                f"Thank you for your honest feedback about our {product_name}. "
                f"We appreciate you taking the time to share your experience. "
                f"We're always looking to improve, and your input helps us do that. "
                f"If there's anything we can do to improve your experience, "
                f"please reach out to us."
            )
            urgency = "medium"
        else:
            reply = (
                f"Thank you for your review! We're glad you're enjoying our "
                f"{product_name}. If you ever need assistance, we're here for you."
            )
            urgency = "low"

        return {
            "reply": reply,
            "urgency": urgency,
            "rating": rating,
            "follow_up_action": "contact_buyer" if rating <= 2 else "none",
        }

    def _tool_get_stats(self) -> dict:
        """获取工单统计"""
        total = len(self.tickets)
        by_type = {}
        by_priority = {}
        by_status = {}

        for t in self.tickets:
            by_type[t.message_type] = by_type.get(t.message_type, 0) + 1
            by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
            by_status[t.status] = by_status.get(t.status, 0) + 1

        return {
            "total_tickets": total,
            "by_type": by_type,
            "by_priority": by_priority,
            "by_status": by_status,
            "escalated_count": sum(1 for t in self.tickets if t.escalated),
            "avg_response_time": "< 1 second (auto-reply)",
        }

    # ============================================================
    # 核心业务逻辑
    # ============================================================

    def run(self, task: str, **kwargs) -> dict:
        """执行客服任务"""
        task_type = kwargs.get("task_type", "process_messages")

        if task_type == "process_messages":
            return self.process_messages(kwargs.get("messages", []))
        elif task_type == "handle_reviews":
            return self.handle_reviews(kwargs.get("reviews", []))
        elif task_type == "stats":
            return self._tool_get_stats()
        elif task_type == "agent_loop":
            return self.run_agent_loop(task, **kwargs)
        else:
            return self.process_messages(kwargs.get("messages", []))

    def process_messages(self, messages: List[dict]) -> dict:
        """批量处理买家消息"""
        if not messages:
            messages = self._get_mock_messages()

        print(f"\n[CustomerService] 开始处理 {len(messages)} 条买家消息")

        results = {
            "started_at": datetime.now().isoformat(),
            "total_messages": len(messages),
            "processed": [],
            "escalated": [],
        }

        for msg in messages:
            # 1. 分类
            classification = self._tool_classify_message(
                msg.get("message", ""),
                msg.get("order_id", ""),
            )

            # 2. 判断是否升级
            if classification["escalate"]:
                self._ticket_counter += 1
                ticket = Ticket(
                    ticket_id=f"T{self._ticket_counter:04d}",
                    order_id=msg.get("order_id", ""),
                    customer_name=msg.get("customer_name", "Customer"),
                    message_type=classification["message_type"],
                    priority=classification["priority"],
                    status="escalated",
                    original_message=msg.get("message", ""),
                    escalated=True,
                    escalate_reason=classification["escalate_reason"],
                    created_at=datetime.now().isoformat(),
                )
                self.tickets.append(ticket)
                results["escalated"].append({
                    "ticket_id": ticket.ticket_id,
                    "reason": ticket.escalate_reason,
                })
                print(f"  [ESCALATE] {ticket.ticket_id}: {ticket.escalate_reason}")
                continue

            # 3. 生成回复
            reply_data = self._tool_generate_reply(
                message=msg.get("message", ""),
                message_type=classification["message_type"],
                order_id=msg.get("order_id", ""),
                product_name=msg.get("product_name", ""),
            )

            # 4. 处理退换货（如果需要）
            return_info = None
            if classification["message_type"] == "return":
                return_info = self._tool_handle_return(
                    order_id=msg.get("order_id", "N/A"),
                    reason=msg.get("message", ""),
                    order_amount=msg.get("order_amount", 10.0),
                )

            # 5. 创建工单
            self._ticket_counter += 1
            ticket = Ticket(
                ticket_id=f"T{self._ticket_counter:04d}",
                order_id=msg.get("order_id", ""),
                customer_name=msg.get("customer_name", "Customer"),
                message_type=classification["message_type"],
                priority=classification["priority"],
                status="resolved",
                original_message=msg.get("message", ""),
                reply=reply_data["reply"],
                action=reply_data["action"],
                created_at=datetime.now().isoformat(),
                resolved_at=datetime.now().isoformat(),
            )
            self.tickets.append(ticket)

            results["processed"].append({
                "ticket_id": ticket.ticket_id,
                "type": classification["message_type"],
                "priority": classification["priority"],
                "reply_preview": reply_data["reply"][:80] + "...",
                "action": reply_data["action"],
            })

            print(f"  [{classification['priority']}] {ticket.ticket_id} "
                  f"({classification['message_type']}): 自动回复已生成")

        results["completed_at"] = datetime.now().isoformat()
        results["stats"] = self._tool_get_stats()
        print(f"\n[CustomerService] 处理完成: {len(results['processed'])} 已回复, "
              f"{len(results['escalated'])} 已升级")

        return results

    def handle_reviews(self, reviews: List[dict]) -> dict:
        """批量处理差评"""
        if not reviews:
            reviews = self._get_mock_reviews()

        print(f"\n[CustomerService] 开始处理 {len(reviews)} 条评论")

        results = {
            "total_reviews": len(reviews),
            "responses": [],
        }

        for review in reviews:
            response = self._tool_respond_review(
                rating=review.get("rating", 3),
                review_content=review.get("content", ""),
                product_name=review.get("product_name", "product"),
                review_title=review.get("title", ""),
            )
            results["responses"].append({
                "rating": review.get("rating"),
                "review_preview": review.get("content", "")[:50],
                "reply_preview": response["reply"][:80] + "...",
                "urgency": response["urgency"],
            })
            print(f"  [{response['urgency'].upper()}] {review.get('rating')}星评论: 回复已生成")

        return results

    # ============================================================
    # 模拟数据
    # ============================================================

    def _get_mock_messages(self) -> List[dict]:
        """模拟买家消息"""
        return [
            {
                "order_id": "114-3941689-8772232",
                "customer_name": "John Smith",
                "product_name": "300PCS Compression Spring Kit",
                "message": "I received the springs but several sizes are missing from the kit. "
                           "The box was damaged and some compartments were empty. Very disappointed.",
                "order_amount": 8.99,
            },
            {
                "order_id": "112-7654321-1234567",
                "customer_name": "Sarah Johnson",
                "product_name": "Stainless Steel U-Bolt Set",
                "message": "Where is my order? It's been 10 days and I still haven't received it. "
                           "Tracking shows it's stuck in transit.",
                "order_amount": 14.99,
            },
            {
                "order_id": "113-9876543-7654321",
                "customer_name": "Mike Davis",
                "product_name": "200PCS Spring Assortment Kit",
                "message": "I want a refund. The springs are too weak and don't hold any tension. "
                           "They are not suitable for the application described.",
                "order_amount": 6.99,
            },
            {
                "order_id": "115-1111111-2222222",
                "customer_name": "Emily Chen",
                "product_name": "Compression Spring Kit",
                "message": "Hi, I was wondering if these springs are compatible with a "
                           "Simplehuman trash can model ST2018? What sizes would I need?",
                "order_amount": 8.99,
            },
        ]

    def _get_mock_reviews(self) -> List[dict]:
        """模拟差评数据"""
        return [
            {
                "rating": 1,
                "title": "Terrible quality",
                "content": "Springs broke after 2 weeks of use. Total waste of money. "
                           "The stainless steel claim is fake - they rust immediately.",
                "product_name": "Compression Spring Kit",
                "date": "2026-02-20",
            },
            {
                "rating": 2,
                "title": "Missing pieces",
                "content": "Only received about 200 out of 300 springs. "
                           "Several compartments were completely empty. Packaging was poor.",
                "product_name": "300PCS Spring Assortment",
                "date": "2026-02-18",
            },
            {
                "rating": 3,
                "title": "Okay but sizes are off",
                "content": "The springs work but the sizes listed don't match what's in the box. "
                           "Had to measure each one to find what I needed. Decent value though.",
                "product_name": "Spring Assortment Kit",
                "date": "2026-02-15",
            },
        ]

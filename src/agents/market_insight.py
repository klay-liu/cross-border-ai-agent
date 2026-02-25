"""
市场洞察 Agent - 实时市场感知与趋势研判

功能：
1. 竞品价格/BSR/评论追踪
2. 变动检测与告警
3. 趋势研判（多信号融合）
4. 日报/周报自动生成
5. 与选品Agent的事件协作
"""
import json
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Optional

from src.agents.base_agent import BaseAgent, ToolResult
from src.config.prompts import (
    MARKET_INSIGHT_SYSTEM, DAILY_REPORT_PROMPT,
    WEEKLY_REPORT_PROMPT, TREND_ANALYSIS_PROMPT,
)
from src.config.settings import ALERT_THRESHOLDS
from src.utils.database import (
    get_price_history, record_price_snapshot,
    save_competitor_event, upsert_product,
)


@dataclass
class CompetitorAlert:
    """竞品告警"""
    asin: str
    event_type: str
    severity: str  # low / medium / high / critical
    message: str
    old_value: str
    new_value: str
    timestamp: str


class MarketInsightAgent(BaseAgent):
    """市场洞察 Agent"""

    def __init__(self):
        super().__init__(
            name="MarketInsight",
            system_prompt=MARKET_INSIGHT_SYSTEM,
        )
        # 监控列表
        self.watchlist = {}
        # 最新快照缓存
        self._latest_snapshots = {}

    def _register_tools(self):
        """注册市场洞察 Agent 的可用工具"""

        self.register_tool(
            name="get_product_current_data",
            description="获取指定ASIN的当前数据（价格、BSR、评论数等）",
            input_schema={
                "type": "object",
                "properties": {
                    "asin": {"type": "string", "description": "Amazon产品ASIN"},
                },
                "required": ["asin"],
            },
            handler=self._tool_get_current_data,
        )

        self.register_tool(
            name="get_price_history",
            description="获取指定ASIN的价格历史数据",
            input_schema={
                "type": "object",
                "properties": {
                    "asin": {"type": "string"},
                    "days": {"type": "integer", "default": 30},
                },
                "required": ["asin"],
            },
            handler=self._tool_get_price_history,
        )

        self.register_tool(
            name="detect_changes",
            description="对比当前数据与上次快照，检测变动",
            input_schema={
                "type": "object",
                "properties": {
                    "asin": {"type": "string"},
                    "current_data": {"type": "object"},
                },
                "required": ["asin", "current_data"],
            },
            handler=self._tool_detect_changes,
        )

        self.register_tool(
            name="send_alert",
            description="发送告警通知到飞书/微信",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
                },
                "required": ["message", "severity"],
            },
            handler=self._tool_send_alert,
        )

    # ============================================================
    # 工具实现
    # ============================================================

    def _tool_get_current_data(self, asin: str) -> dict:
        """
        获取产品当前数据

        MVP: 从缓存/模拟数据获取
        正式: 调用 Keepa API / SP-API
        """
        mock_data = self._get_mock_product_data(asin)
        return mock_data

    def _tool_get_price_history(self, asin: str, days: int = 30) -> dict:
        """获取价格历史"""
        history = get_price_history(asin, days)
        if history:
            return {"asin": asin, "history": history, "source": "database"}

        # 无历史数据时返回模拟数据
        return {
            "asin": asin,
            "history": self._generate_mock_history(asin, days),
            "source": "mock",
        }

    def _tool_detect_changes(self, asin: str, current_data: dict) -> dict:
        """检测数据变动"""
        alerts = []
        previous = self._latest_snapshots.get(asin, {})

        if not previous:
            # 首次采集，记录快照，不触发告警
            self._latest_snapshots[asin] = current_data
            return {"asin": asin, "alerts": [], "first_snapshot": True}

        thresholds = ALERT_THRESHOLDS

        # 价格变动检测
        old_price = previous.get("price", 0)
        new_price = current_data.get("price", 0)
        if old_price > 0 and new_price > 0:
            change_pct = abs(new_price - old_price) / old_price * 100
            if change_pct >= thresholds["price_change_pct"]:
                direction = "上涨" if new_price > old_price else "下降"
                alerts.append(CompetitorAlert(
                    asin=asin,
                    event_type="price_change",
                    severity="high",
                    message=f"价格{direction}: ${old_price:.2f} → ${new_price:.2f} ({change_pct:+.1f}%)",
                    old_value=str(old_price),
                    new_value=str(new_price),
                    timestamp=datetime.now().isoformat(),
                ))

        # BSR 变动检测
        old_bsr = previous.get("bsr_rank", 0)
        new_bsr = current_data.get("bsr_rank", 0)
        if old_bsr > 0 and new_bsr > 0:
            bsr_change_pct = (old_bsr - new_bsr) / old_bsr * 100  # 正数=排名上升
            if abs(bsr_change_pct) >= thresholds["bsr_surge_pct"]:
                direction = "上升" if bsr_change_pct > 0 else "下降"
                alerts.append(CompetitorAlert(
                    asin=asin,
                    event_type="bsr_change",
                    severity="medium",
                    message=f"BSR排名{direction}: #{old_bsr} → #{new_bsr} ({bsr_change_pct:+.1f}%)",
                    old_value=str(old_bsr),
                    new_value=str(new_bsr),
                    timestamp=datetime.now().isoformat(),
                ))

        # 评论数变动
        old_reviews = previous.get("review_count", 0)
        new_reviews = current_data.get("review_count", 0)
        review_diff = new_reviews - old_reviews
        if review_diff >= thresholds["review_surge_count"]:
            alerts.append(CompetitorAlert(
                asin=asin,
                event_type="review_surge",
                severity="medium",
                message=f"评论激增: {old_reviews} → {new_reviews} (新增{review_diff}条)",
                old_value=str(old_reviews),
                new_value=str(new_reviews),
                timestamp=datetime.now().isoformat(),
            ))

        # 评分下降
        old_rating = previous.get("rating", 0)
        new_rating = current_data.get("rating", 0)
        if old_rating > 0 and new_rating > 0:
            rating_diff = new_rating - old_rating
            if rating_diff <= -thresholds["rating_drop"]:
                alerts.append(CompetitorAlert(
                    asin=asin,
                    event_type="rating_drop",
                    severity="medium",
                    message=f"评分下降: {old_rating:.1f} → {new_rating:.1f}",
                    old_value=str(old_rating),
                    new_value=str(new_rating),
                    timestamp=datetime.now().isoformat(),
                ))

        # 断货检测
        if current_data.get("in_stock") is False and previous.get("in_stock") is True:
            alerts.append(CompetitorAlert(
                asin=asin,
                event_type="stock_out",
                severity="critical",
                message=f"竞品断货！{asin} ({current_data.get('brand', '')}) 当前缺货",
                old_value="in_stock",
                new_value="out_of_stock",
                timestamp=datetime.now().isoformat(),
            ))

        # 更新快照
        self._latest_snapshots[asin] = current_data

        # 保存告警到数据库
        for alert in alerts:
            save_competitor_event(
                asin=alert.asin,
                event_type=alert.event_type,
                old_value=alert.old_value,
                new_value=alert.new_value,
                severity=alert.severity,
            )

        return {
            "asin": asin,
            "alerts": [
                {
                    "event_type": a.event_type,
                    "severity": a.severity,
                    "message": a.message,
                }
                for a in alerts
            ],
            "alert_count": len(alerts),
        }

    def _tool_send_alert(self, message: str, severity: str = "medium") -> dict:
        """
        发送告警

        MVP: 打印到控制台
        正式: 发送到飞书 Webhook
        """
        severity_emoji = {
            "low": "🟢",
            "medium": "🟡",
            "high": "🟠",
            "critical": "🔴",
        }
        emoji = severity_emoji.get(severity, "⚪")
        formatted = f"{emoji} [{severity.upper()}] {message}"
        print(f"  [ALERT] {formatted}")

        # TODO: 正式部署时接入飞书 Webhook
        # self._send_feishu_webhook(formatted)

        return {"sent": True, "channel": "console", "message": formatted}

    # ============================================================
    # 核心业务逻辑
    # ============================================================

    def run(self, task: str, **kwargs) -> dict:
        """执行市场洞察任务"""
        task_type = kwargs.get("task_type", "monitor")

        if task_type == "monitor":
            return self.run_monitoring_cycle(kwargs.get("asins", []))
        elif task_type == "daily_report":
            return self.generate_daily_report()
        elif task_type == "trend_analysis":
            return self.analyze_trend(kwargs.get("category", ""))
        elif task_type == "agent_loop":
            return self.run_agent_loop(task, **kwargs)
        else:
            return self.run_monitoring_cycle(kwargs.get("asins", []))

    def run_monitoring_cycle(self, asins: Optional[List[str]] = None) -> dict:
        """
        执行一轮竞品监控周期

        1. 采集所有监控 ASIN 的当前数据
        2. 对比上次快照，检测变动
        3. 触发告警
        4. 记录数据快照
        """
        if not asins:
            asins = self._get_default_watchlist()

        print(f"\n[MarketInsight] 开始监控周期: {len(asins)} 个ASIN")

        results = {
            "cycle_time": datetime.now().isoformat(),
            "monitored_count": len(asins),
            "alerts": [],
            "snapshots": [],
        }

        for asin in asins:
            # 1. 获取当前数据
            current = self._tool_get_current_data(asin)

            # 确保产品存在于 products 表（满足外键约束）
            upsert_product({
                "asin": asin,
                "title": current.get("title"),
                "brand": current.get("brand"),
                "price": current.get("price"),
                "rating": current.get("rating"),
                "review_count": current.get("review_count"),
                "bsr_rank": current.get("bsr_rank"),
                "monthly_sales_est": current.get("monthly_sales_est"),
            })

            results["snapshots"].append({
                "asin": asin,
                "price": current.get("price"),
                "bsr_rank": current.get("bsr_rank"),
                "rating": current.get("rating"),
                "review_count": current.get("review_count"),
            })

            # 2. 检测变动
            changes = self._tool_detect_changes(asin, current)

            # 3. 触发告警
            for alert in changes.get("alerts", []):
                results["alerts"].append(alert)
                self._tool_send_alert(alert["message"], alert["severity"])

            # 4. 记录快照
            record_price_snapshot(
                asin=asin,
                price=current.get("price", 0),
                bsr_rank=current.get("bsr_rank"),
                review_count=current.get("review_count"),
                rating=current.get("rating"),
            )

        print(f"[MarketInsight] 监控完成: {len(results['alerts'])} 个告警")
        return results

    def generate_daily_report(self) -> dict:
        """生成市场日报"""
        print(f"\n[MarketInsight] 生成市场日报...")

        # 收集今日数据
        today = datetime.now().strftime("%Y-%m-%d")
        asins = self._get_default_watchlist()

        # 采集数据并检测变动
        monitoring_result = self.run_monitoring_cycle(asins)

        # 构建日报
        report_lines = [
            f"# 市场日报 - {today}",
            f"",
            f"## 监控概况",
            f"- 监控产品数: {monitoring_result['monitored_count']}",
            f"- 告警数: {len(monitoring_result['alerts'])}",
            f"",
        ]

        if monitoring_result['alerts']:
            report_lines.append("## 告警事件")
            report_lines.append("")
            for alert in monitoring_result['alerts']:
                severity_emoji = {"low": "🟢", "medium": "🟡", "high": "🟠", "critical": "🔴"}
                emoji = severity_emoji.get(alert.get("severity", ""), "⚪")
                report_lines.append(f"- {emoji} {alert['message']}")
            report_lines.append("")

        report_lines.extend([
            "## 数据快照",
            "",
            "| ASIN | 价格 | BSR | 评分 | 评论数 |",
            "|------|------|-----|------|--------|",
        ])

        for snap in monitoring_result['snapshots']:
            report_lines.append(
                f"| {snap['asin'][:12]}... | "
                f"${snap.get('price', 'N/A')} | "
                f"#{snap.get('bsr_rank', 'N/A')} | "
                f"{snap.get('rating', 'N/A')} | "
                f"{snap.get('review_count', 'N/A')} |"
            )

        report_lines.extend([
            "",
            "---",
            f"*报告由 MarketInsight Agent 自动生成 - {today}*",
        ])

        report = "\n".join(report_lines)
        print(f"[MarketInsight] 日报生成完成 ({len(report)} 字符)")

        return {
            "report_type": "daily",
            "date": today,
            "report": report,
            "alert_count": len(monitoring_result['alerts']),
            "monitoring_result": monitoring_result,
        }

    def analyze_trend(self, category: str) -> dict:
        """趋势分析（简化版）"""
        print(f"\n[MarketInsight] 分析趋势: {category}")

        # MVP: 基于已有数据的简化趋势判断
        trend_data = self._get_mock_trend_data(category)

        # 多信号融合评分
        score = 0

        # 搜索量趋势
        sv_trend = trend_data.get("search_volume_trend", "stable")
        if sv_trend == "rising":
            score += 30
        elif sv_trend == "stable":
            score += 15
        else:
            score -= 10

        # BSR 趋势
        bsr_change = trend_data.get("avg_bsr_change_pct", 0)
        if bsr_change < -10:
            score += 25  # BSR下降 = 销量上升
        elif bsr_change < 0:
            score += 15

        # 新品密度
        new_listings = trend_data.get("new_listings_90d", 0)
        if new_listings > 10:
            score += 15
        elif new_listings > 5:
            score += 8

        # 评论增速
        review_growth = trend_data.get("review_growth_rate", 0)
        if review_growth > 0.2:
            score += 10
        elif review_growth > 0.1:
            score += 5

        # 趋势判定
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

        result = {
            "category": category,
            "trend_direction": direction,
            "confidence_score": min(score, 100),
            "signals": trend_data,
            "assessment": self._get_trend_assessment(direction, category),
        }

        print(f"[MarketInsight] 趋势判定: {category} → {direction} (置信度: {score})")
        return result

    # ============================================================
    # 辅助方法
    # ============================================================

    def _get_default_watchlist(self) -> List[str]:
        """默认监控列表"""
        return [
            "B0BVTDP29W",  # Dianrui 弹簧套装
            "B0FG2DQYY7",  # Fgruh 螺丝套装
            "B0FGV5FCBN",  # Fgruh M3螺丝
            "B0CF8LB4PF",  # Foliv 螺栓套装
            "B0C1SPRING1", # 垃圾桶弹簧 #1
        ]

    def _get_mock_product_data(self, asin: str) -> dict:
        """模拟产品数据"""
        mock_db = {
            "B0BVTDP29W": {
                "asin": "B0BVTDP29W", "title": "Dianrui 300PCS Compression Springs",
                "brand": "Dianrui", "price": 7.49, "rating": 4.6,
                "review_count": 715, "bsr_rank": 1050,
                "monthly_sales_est": 2900, "in_stock": True,
            },
            "B0FG2DQYY7": {
                "asin": "B0FG2DQYY7", "title": "Fgruh 640PCS Machine Screw Kit",
                "brand": "Fgruh", "price": 12.99, "rating": 4.6,
                "review_count": 580, "bsr_rank": 85,
                "monthly_sales_est": 16000, "in_stock": True,
            },
            "B0FGV5FCBN": {
                "asin": "B0FGV5FCBN", "title": "Fgruh M3 750PCS Screw Kit",
                "brand": "Fgruh", "price": 9.99, "rating": 4.6,
                "review_count": 580, "bsr_rank": 85,
                "monthly_sales_est": 16000, "in_stock": True,
            },
            "B0CF8LB4PF": {
                "asin": "B0CF8LB4PF", "title": "Foliv Grade 8 Bolt Kit 523PCS",
                "brand": "Foliv", "price": 49.99, "rating": 4.7,
                "review_count": 548, "bsr_rank": 12500,
                "monthly_sales_est": 490, "in_stock": True,
            },
            "B0C1SPRING1": {
                "asin": "B0C1SPRING1", "title": "5 Pcs Torsion Springs for Trash Can",
                "brand": "Cilky", "price": 7.99, "rating": 4.4,
                "review_count": 14, "bsr_rank": 43000,
                "monthly_sales_est": 160, "in_stock": True,
            },
        }
        return mock_db.get(asin, {
            "asin": asin, "title": f"Unknown Product {asin}",
            "price": 0, "rating": 0, "review_count": 0,
            "bsr_rank": 0, "in_stock": True,
        })

    def _generate_mock_history(self, asin: str, days: int) -> List[dict]:
        """生成模拟历史数据"""
        import random
        current = self._get_mock_product_data(asin)
        base_price = current.get("price", 10.0)
        base_bsr = current.get("bsr_rank", 10000)

        history = []
        for i in range(days, 0, -1):
            date = (datetime.now() - timedelta(days=i)).isoformat()
            price_jitter = random.uniform(-0.5, 0.5)
            bsr_jitter = random.randint(-2000, 2000)
            history.append({
                "price": round(base_price + price_jitter, 2),
                "bsr_rank": max(1, base_bsr + bsr_jitter),
                "recorded_at": date,
            })
        return history

    def _get_mock_trend_data(self, category: str) -> dict:
        """模拟趋势数据"""
        trends = {
            "弹簧": {
                "search_volume_trend": "rising",
                "avg_bsr_change_pct": -12,
                "new_listings_90d": 8,
                "review_growth_rate": 0.15,
            },
            "螺栓": {
                "search_volume_trend": "stable",
                "avg_bsr_change_pct": -3,
                "new_listings_90d": 5,
                "review_growth_rate": 0.08,
            },
            "挂钩": {
                "search_volume_trend": "stable",
                "avg_bsr_change_pct": 2,
                "new_listings_90d": 3,
                "review_growth_rate": 0.05,
            },
        }

        for key, data in trends.items():
            if key in category:
                return data

        return {
            "search_volume_trend": "stable",
            "avg_bsr_change_pct": 0,
            "new_listings_90d": 3,
            "review_growth_rate": 0.05,
        }

    def _get_trend_assessment(self, direction: str, category: str) -> str:
        """生成趋势评估文本"""
        assessments = {
            "strong_rising": f"{category}品类强势上升，建议加速选品进度，抢占窗口期",
            "rising": f"{category}品类温和上升，市场机会正在扩大，可以稳步推进",
            "stable": f"{category}品类保持稳定，适合稳健入场，关注差异化",
            "declining": f"{category}品类出现下降信号，建议谨慎评估，等待趋势确认",
            "strong_declining": f"{category}品类明显下滑，不建议此时入场",
        }
        return assessments.get(direction, "趋势不明确，建议持续观察")

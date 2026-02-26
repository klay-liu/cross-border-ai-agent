"""
动态定价 Agent - 智能价格优化与竞品联动定价

功能：
1. 竞品价格监控与联动：自动跟踪竞品价格并评估跟价策略
2. 库存驱动定价：基于库存水位动态调整价格
3. 利润优化：在竞争力和利润率之间找到最优平衡点
4. 促销策略：Coupon/Deal/降价时机建议
5. 心理定价：.99/.97 价格锚点优化
6. 价格弹性分析：基于历史数据估算价格-销量关系
"""
import json
from datetime import datetime
from typing import Dict, List, Optional

from src.agents.base_agent import BaseAgent, ToolResult
from src.config.prompts import (
    DYNAMIC_PRICING_SYSTEM,
    PRICING_STRATEGY_PROMPT,
    PRICE_ADJUSTMENT_PROMPT,
)
from src.config.settings import REPORTS_DIR


class DynamicPricingAgent(BaseAgent):
    """动态定价 Agent"""

    def __init__(self):
        super().__init__(
            name="DynamicPricing",
            system_prompt=DYNAMIC_PRICING_SYSTEM,
        )

    def _register_tools(self):
        """注册定价 Agent 的可用工具"""

        self.register_tool(
            name="analyze_price_position",
            description="分析产品在竞品中的价格定位",
            input_schema={
                "type": "object",
                "properties": {
                    "my_price": {"type": "number"},
                    "competitor_prices": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "my_cost": {"type": "number", "description": "总成本(含FBA+佣金+产品成本)"},
                },
                "required": ["my_price", "competitor_prices", "my_cost"],
            },
            handler=self._tool_analyze_price_position,
        )

        self.register_tool(
            name="calculate_optimal_price",
            description="计算最优定价",
            input_schema={
                "type": "object",
                "properties": {
                    "cost": {"type": "number"},
                    "competitor_avg_price": {"type": "number"},
                    "current_daily_sales": {"type": "number"},
                    "current_stock": {"type": "integer"},
                    "target_margin": {"type": "number", "default": 0.25},
                },
                "required": ["cost", "competitor_avg_price"],
            },
            handler=self._tool_calculate_optimal_price,
        )

        self.register_tool(
            name="evaluate_price_change",
            description="评估竞品价格变动后是否需要跟价",
            input_schema={
                "type": "object",
                "properties": {
                    "my_price": {"type": "number"},
                    "my_cost": {"type": "number"},
                    "competitor_old_price": {"type": "number"},
                    "competitor_new_price": {"type": "number"},
                    "competitor_asin": {"type": "string"},
                },
                "required": ["my_price", "my_cost", "competitor_old_price", "competitor_new_price"],
            },
            handler=self._tool_evaluate_price_change,
        )

        self.register_tool(
            name="suggest_promotion",
            description="基于库存和竞争情况建议促销策略",
            input_schema={
                "type": "object",
                "properties": {
                    "asin": {"type": "string"},
                    "current_price": {"type": "number"},
                    "cost": {"type": "number"},
                    "current_stock": {"type": "integer"},
                    "daily_sales": {"type": "number"},
                    "days_since_launch": {"type": "integer"},
                },
                "required": ["current_price", "cost"],
            },
            handler=self._tool_suggest_promotion,
        )

    # ============================================================
    # 工具实现
    # ============================================================

    def _tool_analyze_price_position(self, my_price: float,
                                      competitor_prices: List[dict],
                                      my_cost: float) -> dict:
        """分析价格定位"""
        prices = [c.get("price", 0) for c in competitor_prices if c.get("price", 0) > 0]

        if not prices:
            return {"error": "No competitor prices available"}

        avg_price = sum(prices) / len(prices)
        min_price = min(prices)
        max_price = max(prices)
        median_price = sorted(prices)[len(prices) // 2]

        # 价格百分位
        lower_count = sum(1 for p in prices if p < my_price)
        percentile = (lower_count / len(prices)) * 100

        # 利润分析
        my_margin = (my_price - my_cost) / my_price if my_price > 0 else 0

        # 定位判断
        if my_price < avg_price * 0.85:
            position = "low_price"
            position_desc = "低价位，可能牺牲利润"
        elif my_price <= avg_price * 1.15:
            position = "mid_price"
            position_desc = "中间价位，竞争力适中"
        else:
            position = "high_price"
            position_desc = "高价位，需要强差异化支撑"

        return {
            "my_price": my_price,
            "my_cost": my_cost,
            "my_margin": round(my_margin * 100, 1),
            "market_overview": {
                "avg_price": round(avg_price, 2),
                "min_price": round(min_price, 2),
                "max_price": round(max_price, 2),
                "median_price": round(median_price, 2),
                "competitor_count": len(prices),
            },
            "position": position,
            "position_description": position_desc,
            "price_percentile": round(percentile, 1),
            "vs_average": round((my_price - avg_price) / avg_price * 100, 1),
        }

    def _tool_calculate_optimal_price(self, cost: float,
                                       competitor_avg_price: float,
                                       current_daily_sales: float = 5,
                                       current_stock: int = 200,
                                       target_margin: float = 0.25) -> dict:
        """计算最优定价"""
        # 最低价（保证最低利润）
        min_price = round(cost / (1 - 0.10), 2)  # 最低10%利润率

        # 目标价（基于目标利润率）
        target_price = round(cost / (1 - target_margin), 2)

        # 竞争价（参考竞品均价）
        competitive_price = round(competitor_avg_price * 0.95, 2)  # 比均价低5%

        # 最优价（综合考虑）
        # 如果库存积压，偏向低价；如果库存紧张，偏向高价
        days_of_stock = current_stock / current_daily_sales if current_daily_sales > 0 else 999

        if days_of_stock > 120:
            # 库存积压，降价促销
            optimal = min(competitive_price, target_price)
            strategy = "clearance"
            reason = "库存积压(>120天)，建议降价促进周转"
        elif days_of_stock < 30:
            # 库存紧张，可以涨价
            optimal = max(target_price, competitive_price * 1.05)
            strategy = "premium"
            reason = "库存紧张(<30天)，可适当提价保利润"
        else:
            # 正常状态，追求利润率
            optimal = target_price
            strategy = "balanced"
            reason = "库存正常，以目标利润率定价"

        # 心理价格调整 (.99)
        optimal = round(optimal) - 0.01 if optimal > 5 else round(optimal, 2)

        return {
            "optimal_price": optimal,
            "price_range": {
                "minimum": min_price,
                "target": target_price,
                "competitive": competitive_price,
                "recommended": optimal,
            },
            "strategy": strategy,
            "reason": reason,
            "expected_margin": round((optimal - cost) / optimal * 100, 1),
            "days_of_stock": round(days_of_stock, 1),
        }

    def _tool_evaluate_price_change(self, my_price: float, my_cost: float,
                                     competitor_old_price: float,
                                     competitor_new_price: float,
                                     competitor_asin: str = "") -> dict:
        """评估是否跟价"""
        change_pct = (competitor_new_price - competitor_old_price) / competitor_old_price * 100

        # 如果竞品降价
        if competitor_new_price < competitor_old_price:
            price_gap = my_price - competitor_new_price
            gap_pct = price_gap / competitor_new_price * 100

            if gap_pct > 30:
                # 价差过大，需要跟价
                suggested = round(competitor_new_price * 1.05, 2)
                # 检查是否低于成本
                if suggested < my_cost * 1.1:
                    action = "hold"
                    reason = (f"竞品降价{abs(change_pct):.1f}%，但跟价将低于成本线，"
                             f"建议通过Listing优化和广告提升竞争力")
                    suggested = my_price
                else:
                    action = "follow"
                    reason = f"竞品降价{abs(change_pct):.1f}%，价差{gap_pct:.1f}%过大，建议适度跟价"
            elif gap_pct > 15:
                action = "monitor"
                reason = f"竞品降价{abs(change_pct):.1f}%，价差{gap_pct:.1f}%可接受，持续观察"
                suggested = my_price
            else:
                action = "hold"
                reason = f"竞品小幅降价{abs(change_pct):.1f}%，我方价格仍有竞争力"
                suggested = my_price
        else:
            # 竞品涨价 → 机会
            action = "opportunity"
            reason = f"竞品涨价{change_pct:.1f}%，可考虑小幅提价增加利润"
            suggested = round(min(my_price * 1.05, competitor_new_price * 0.95), 2)

        new_margin = (suggested - my_cost) / suggested * 100 if suggested > 0 else 0

        return {
            "action": action,
            "reason": reason,
            "current_price": my_price,
            "suggested_price": suggested,
            "competitor_change": {
                "asin": competitor_asin,
                "old_price": competitor_old_price,
                "new_price": competitor_new_price,
                "change_pct": round(change_pct, 1),
            },
            "impact": {
                "new_margin": round(new_margin, 1),
                "price_change": round(suggested - my_price, 2),
            },
        }

    def _tool_suggest_promotion(self, current_price: float, cost: float,
                                 asin: str = "", current_stock: int = 200,
                                 daily_sales: float = 5,
                                 days_since_launch: int = 60) -> dict:
        """促销策略建议"""
        days_of_stock = current_stock / daily_sales if daily_sales > 0 else 999
        margin = (current_price - cost) / current_price if current_price > 0 else 0

        suggestions = []

        # 新品期 Coupon
        if days_since_launch < 90:
            coupon_pct = 15 if days_since_launch < 30 else 10
            suggestions.append({
                "type": "coupon",
                "value": f"{coupon_pct}% off",
                "reason": "新品期，Coupon 可提升点击率和转化率",
                "estimated_impact": f"+{coupon_pct * 2}% 销量提升",
                "cost": round(current_price * coupon_pct / 100, 2),
            })

        # 库存积压 → Lightning Deal
        if days_of_stock > 90:
            deal_price = round(current_price * 0.80, 2)
            if deal_price > cost * 1.05:
                suggestions.append({
                    "type": "lightning_deal",
                    "value": f"${deal_price} (20% off)",
                    "reason": f"库存积压({int(days_of_stock)}天)，Flash Deal 加速周转",
                    "estimated_impact": "+300% 销量 (Deal期间)",
                    "cost": round((current_price - deal_price) * daily_sales * 3, 2),
                })

        # 高利润 → 可以做降价
        if margin > 0.35:
            new_price = round(current_price * 0.90, 2)
            suggestions.append({
                "type": "price_reduction",
                "value": f"${current_price} → ${new_price}",
                "reason": f"利润率{margin:.0%}较高，降价10%可提升竞争力",
                "estimated_impact": "+20-30% 销量提升",
                "cost": round((current_price - new_price) * daily_sales * 30, 2),
            })

        # 如果没有特别建议
        if not suggestions:
            suggestions.append({
                "type": "hold",
                "value": "维持现价",
                "reason": "当前价格、库存、利润率均在健康范围",
                "estimated_impact": "稳定",
                "cost": 0,
            })

        return {
            "asin": asin,
            "current_price": current_price,
            "cost": cost,
            "margin": round(margin * 100, 1),
            "days_of_stock": round(days_of_stock, 1),
            "days_since_launch": days_since_launch,
            "suggestions": suggestions,
        }

    # ============================================================
    # 核心业务逻辑
    # ============================================================

    def run(self, task: str, **kwargs) -> dict:
        """执行定价任务"""
        task_type = kwargs.get("task_type", "full_analysis")

        if task_type == "price_check":
            return self._run_price_check(**kwargs)
        elif task_type == "competitor_response":
            return self._run_competitor_response(**kwargs)
        elif task_type == "full_analysis":
            return self._run_full_analysis(**kwargs)
        elif task_type == "agent_loop":
            return self.run_agent_loop(task, **kwargs)
        else:
            return self._run_full_analysis(**kwargs)

    def _run_full_analysis(self, **kwargs) -> dict:
        """完整定价分析"""
        products = kwargs.get("products", self._get_mock_products())

        print(f"\n[DynamicPricing] 开始定价分析: {len(products)} 个产品")

        results = {
            "started_at": datetime.now().isoformat(),
            "product_count": len(products),
            "analyses": [],
        }

        for product in products:
            name = product.get("name", "")
            my_price = product.get("price", 0)
            my_cost = product.get("cost", 0)
            competitors = product.get("competitors", [])

            print(f"\n[DynamicPricing] 分析: {name}")

            # 1. 价格定位分析
            position = self._tool_analyze_price_position(my_price, competitors, my_cost)
            print(f"  定位: {position['position_description']} "
                  f"(市场均价${position['market_overview']['avg_price']})")

            # 2. 最优定价计算
            avg_price = position["market_overview"]["avg_price"]
            optimal = self._tool_calculate_optimal_price(
                cost=my_cost,
                competitor_avg_price=avg_price,
                current_daily_sales=product.get("daily_sales", 5),
                current_stock=product.get("stock", 200),
            )
            print(f"  建议价: ${optimal['optimal_price']} "
                  f"({optimal['strategy']}, 利润率{optimal['expected_margin']}%)")

            # 3. 促销建议
            promo = self._tool_suggest_promotion(
                current_price=my_price,
                cost=my_cost,
                current_stock=product.get("stock", 200),
                daily_sales=product.get("daily_sales", 5),
                days_since_launch=product.get("days_since_launch", 60),
            )
            for s in promo["suggestions"]:
                print(f"  促销: [{s['type']}] {s['value']} - {s['reason']}")

            results["analyses"].append({
                "product_name": name,
                "current_price": my_price,
                "position": position,
                "optimal_pricing": optimal,
                "promotion": promo,
            })

        results["completed_at"] = datetime.now().isoformat()
        print(f"\n[DynamicPricing] 定价分析完成！")
        return results

    def _run_price_check(self, **kwargs) -> dict:
        """仅价格定位检查"""
        return self._tool_analyze_price_position(
            my_price=kwargs.get("my_price", 8.99),
            competitor_prices=kwargs.get("competitor_prices", []),
            my_cost=kwargs.get("my_cost", 5.0),
        )

    def _run_competitor_response(self, **kwargs) -> dict:
        """竞品价格变动响应"""
        return self._tool_evaluate_price_change(
            my_price=kwargs.get("my_price", 8.99),
            my_cost=kwargs.get("my_cost", 5.0),
            competitor_old_price=kwargs.get("competitor_old_price", 6.99),
            competitor_new_price=kwargs.get("competitor_new_price", 5.99),
            competitor_asin=kwargs.get("competitor_asin", ""),
        )

    # ============================================================
    # 模拟数据
    # ============================================================

    def _get_mock_products(self) -> List[dict]:
        """模拟产品数据"""
        return [
            {
                "name": "200PCS Spring Assortment Kit",
                "asin": "B0COMPSP02",
                "price": 8.99,
                "cost": 6.18,  # 产品+FBA+佣金+头程
                "stock": 150,
                "daily_sales": 8,
                "days_since_launch": 45,
                "competitors": [
                    {"asin": "B0BVTDP29W", "price": 6.99, "brand": "Dianrui", "rating": 4.6},
                    {"asin": "B0FG2COMP3", "price": 12.99, "brand": "Fgruh", "rating": 4.5},
                    {"asin": "B0COMP0004", "price": 5.99, "brand": "SpringPro", "rating": 4.1},
                    {"asin": "B0COMP0005", "price": 15.99, "brand": "HeavySpring", "rating": 4.4},
                ],
            },
            {
                "name": "5Pcs Torsion Springs",
                "asin": "B0C1SPRING1",
                "price": 7.99,
                "cost": 5.77,
                "stock": 45,
                "daily_sales": 3,
                "days_since_launch": 20,
                "competitors": [
                    {"asin": "B0C2SPRING2", "price": 4.59, "brand": "FUNOMOCYA", "rating": 3.4},
                    {"asin": "B0C3SPRING3", "price": 6.98, "brand": "Generic", "rating": 3.6},
                    {"asin": "B0C5SPRING5", "price": 6.16, "brand": "Mipcase", "rating": 3.5},
                ],
            },
        ]

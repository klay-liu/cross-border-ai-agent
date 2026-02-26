"""
库存预测 Agent - FBA 库存智能管理与需求预测

功能：
1. 需求预测：基于历史销量+季节性+趋势的多模型预测
2. 补货建议：考虑全链路提前期的智能补货方案
3. 断货预警：预判断货风险并提前告警
4. 仓储成本优化：平衡库存深度与仓储费用
5. 多仓调拨建议：FBA仓间调拨优化
"""
import json
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from src.agents.base_agent import BaseAgent, ToolResult
from src.config.prompts import (
    INVENTORY_FORECAST_SYSTEM,
    DEMAND_FORECAST_PROMPT,
    REPLENISHMENT_PROMPT,
)
from src.config.settings import REPORTS_DIR


class InventoryForecastAgent(BaseAgent):
    """库存预测 Agent"""

    def __init__(self):
        super().__init__(
            name="InventoryForecast",
            system_prompt=INVENTORY_FORECAST_SYSTEM,
        )

    def _register_tools(self):
        """注册库存预测 Agent 的可用工具"""

        self.register_tool(
            name="forecast_demand",
            description="基于历史销售数据预测未来需求",
            input_schema={
                "type": "object",
                "properties": {
                    "asin": {"type": "string"},
                    "sales_history": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "历史销售数据 [{date, units}]",
                    },
                    "forecast_days": {"type": "integer", "default": 90},
                },
                "required": ["asin"],
            },
            handler=self._tool_forecast_demand,
        )

        self.register_tool(
            name="calculate_replenishment",
            description="计算补货建议（数量+时间）",
            input_schema={
                "type": "object",
                "properties": {
                    "asin": {"type": "string"},
                    "current_stock": {"type": "integer"},
                    "daily_sales": {"type": "number"},
                    "in_transit": {"type": "integer", "default": 0},
                    "production_days": {"type": "integer", "default": 10},
                    "shipping_days": {"type": "integer", "default": 40},
                    "inbound_days": {"type": "integer", "default": 10},
                },
                "required": ["asin", "current_stock", "daily_sales"],
            },
            handler=self._tool_calculate_replenishment,
        )

        self.register_tool(
            name="check_stockout_risk",
            description="检查断货风险等级",
            input_schema={
                "type": "object",
                "properties": {
                    "inventory_status": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "各SKU库存状态列表",
                    },
                },
                "required": ["inventory_status"],
            },
            handler=self._tool_check_stockout_risk,
        )

        self.register_tool(
            name="calculate_storage_cost",
            description="计算FBA仓储费用",
            input_schema={
                "type": "object",
                "properties": {
                    "units": {"type": "integer"},
                    "volume_cuft_per_unit": {"type": "number", "default": 0.05},
                    "month": {"type": "integer", "description": "月份1-12"},
                },
                "required": ["units"],
            },
            handler=self._tool_calculate_storage_cost,
        )

    # ============================================================
    # 工具实现
    # ============================================================

    def _tool_forecast_demand(self, asin: str,
                               sales_history: Optional[List[dict]] = None,
                               forecast_days: int = 90) -> dict:
        """需求预测"""
        if not sales_history:
            sales_history = self._get_mock_sales_history(asin)

        # 简单移动平均预测
        recent_30d = sales_history[-30:] if len(sales_history) >= 30 else sales_history
        recent_7d = sales_history[-7:] if len(sales_history) >= 7 else sales_history

        avg_30d = sum(d.get("units", 0) for d in recent_30d) / max(len(recent_30d), 1)
        avg_7d = sum(d.get("units", 0) for d in recent_7d) / max(len(recent_7d), 1)

        # 趋势调整
        if avg_7d > avg_30d * 1.1:
            trend = "rising"
            trend_factor = 1.1
        elif avg_7d < avg_30d * 0.9:
            trend = "declining"
            trend_factor = 0.9
        else:
            trend = "stable"
            trend_factor = 1.0

        # 季节性调整（Q4旺季）
        current_month = datetime.now().month
        seasonal_factors = {
            1: 0.85, 2: 0.80, 3: 0.90, 4: 0.95,
            5: 1.00, 6: 1.05, 7: 1.10, 8: 1.05,
            9: 1.00, 10: 1.15, 11: 1.30, 12: 1.25,
        }
        seasonal = seasonal_factors.get(current_month, 1.0)

        base_daily = avg_30d
        adjusted_daily = base_daily * trend_factor * seasonal

        return {
            "asin": asin,
            "forecast_period_days": forecast_days,
            "base_daily_sales": round(base_daily, 1),
            "trend": trend,
            "trend_factor": trend_factor,
            "seasonal_factor": seasonal,
            "forecast": {
                "daily_avg": round(adjusted_daily, 1),
                "next_30d_total": round(adjusted_daily * 30),
                "next_60d_total": round(adjusted_daily * 60),
                "next_90d_total": round(adjusted_daily * 90),
            },
            "confidence_intervals": {
                "optimistic": round(adjusted_daily * 1.3, 1),
                "base": round(adjusted_daily, 1),
                "conservative": round(adjusted_daily * 0.7, 1),
            },
            "data_points_used": len(sales_history),
        }

    def _tool_calculate_replenishment(self, asin: str, current_stock: int,
                                       daily_sales: float, in_transit: int = 0,
                                       production_days: int = 10,
                                       shipping_days: int = 40,
                                       inbound_days: int = 10) -> dict:
        """计算补货建议"""
        total_lead_time = production_days + shipping_days + inbound_days
        safety_stock_days = 15  # 安全库存天数
        safety_stock = math.ceil(daily_sales * safety_stock_days)

        # 可售天数
        effective_stock = current_stock + in_transit
        days_of_stock = effective_stock / daily_sales if daily_sales > 0 else 999

        # 补货触发点 = 提前期日销量 + 安全库存
        reorder_point = math.ceil(daily_sales * total_lead_time) + safety_stock

        # 是否需要补货
        need_reorder = effective_stock <= reorder_point

        # 建议补货量 = 60天销量目标
        target_days = 60
        order_quantity = max(0, math.ceil(daily_sales * target_days) - effective_stock + safety_stock)

        # 紧急程度
        if days_of_stock < total_lead_time:
            urgency = "red"
            urgency_msg = "断货风险极高！库存不足以覆盖补货周期"
        elif days_of_stock < total_lead_time + safety_stock_days:
            urgency = "yellow"
            urgency_msg = "接近补货点，建议立即下单"
        else:
            urgency = "green"
            urgency_msg = "库存充足"

        # 建议下单日期
        days_until_order = max(0, int(days_of_stock - total_lead_time - safety_stock_days))
        order_date = (datetime.now() + timedelta(days=days_until_order)).strftime("%Y-%m-%d")

        return {
            "asin": asin,
            "current_stock": current_stock,
            "in_transit": in_transit,
            "effective_stock": effective_stock,
            "daily_sales": daily_sales,
            "days_of_stock": round(days_of_stock, 1),
            "total_lead_time_days": total_lead_time,
            "safety_stock": safety_stock,
            "reorder_point": reorder_point,
            "need_reorder": need_reorder,
            "order_quantity": order_quantity,
            "suggested_order_date": order_date,
            "urgency": urgency,
            "urgency_message": urgency_msg,
        }

    def _tool_check_stockout_risk(self, inventory_status: List[dict]) -> dict:
        """断货风险检查"""
        risks = {"red": [], "yellow": [], "green": []}

        for item in inventory_status:
            asin = item.get("asin", "")
            stock = item.get("current_stock", 0)
            daily_sales = item.get("daily_sales", 1)
            in_transit = item.get("in_transit", 0)

            days = (stock + in_transit) / daily_sales if daily_sales > 0 else 999

            if days < 30:
                risks["red"].append({
                    "asin": asin,
                    "days_of_stock": round(days, 1),
                    "action": "立即补货",
                })
            elif days < 60:
                risks["yellow"].append({
                    "asin": asin,
                    "days_of_stock": round(days, 1),
                    "action": "计划补货",
                })
            else:
                risks["green"].append({
                    "asin": asin,
                    "days_of_stock": round(days, 1),
                    "action": "库存充足",
                })

        return {
            "total_skus": len(inventory_status),
            "risk_summary": {
                "red": len(risks["red"]),
                "yellow": len(risks["yellow"]),
                "green": len(risks["green"]),
            },
            "risks": risks,
        }

    def _tool_calculate_storage_cost(self, units: int,
                                      volume_cuft_per_unit: float = 0.05,
                                      month: int = 0) -> dict:
        """计算仓储费"""
        if month == 0:
            month = datetime.now().month

        # Amazon FBA 仓储费率
        if 1 <= month <= 9:
            rate = 0.87  # $/cubic foot/month
            season = "standard"
        else:
            rate = 2.40  # Q4 旺季费率
            season = "peak"

        total_volume = units * volume_cuft_per_unit
        monthly_cost = total_volume * rate

        # 长期仓储附加费（>365天）
        long_term_surcharge = 0  # 简化处理

        return {
            "units": units,
            "volume_per_unit_cuft": volume_cuft_per_unit,
            "total_volume_cuft": round(total_volume, 2),
            "season": season,
            "rate_per_cuft": rate,
            "monthly_storage_cost": round(monthly_cost, 2),
            "annual_estimate": round(monthly_cost * 12, 2),
            "cost_per_unit_per_month": round(monthly_cost / units, 4) if units > 0 else 0,
        }

    # ============================================================
    # 核心业务逻辑
    # ============================================================

    def run(self, task: str, **kwargs) -> dict:
        """执行库存管理任务"""
        task_type = kwargs.get("task_type", "full_analysis")

        if task_type == "forecast":
            return self._tool_forecast_demand(
                asin=kwargs.get("asin", ""),
                forecast_days=kwargs.get("forecast_days", 90),
            )
        elif task_type == "replenishment":
            return self._run_replenishment_check(**kwargs)
        elif task_type == "full_analysis":
            return self._run_full_analysis(**kwargs)
        elif task_type == "agent_loop":
            return self.run_agent_loop(task, **kwargs)
        else:
            return self._run_full_analysis(**kwargs)

    def _run_full_analysis(self, **kwargs) -> dict:
        """完整库存分析流程"""
        skus = kwargs.get("skus", self._get_mock_sku_list())

        print(f"\n[InventoryForecast] 开始库存分析: {len(skus)} 个SKU")

        results = {
            "started_at": datetime.now().isoformat(),
            "sku_count": len(skus),
            "steps": {},
            "sku_details": [],
        }

        # Step 1: 需求预测
        print(f"\n[InventoryForecast] Step 1: 需求预测")
        forecasts = {}
        for sku in skus:
            asin = sku["asin"]
            forecast = self._tool_forecast_demand(asin)
            forecasts[asin] = forecast
            print(f"  {asin}: 日均{forecast['forecast']['daily_avg']}件 "
                  f"({forecast['trend']})")

        # Step 2: 补货建议
        print(f"\n[InventoryForecast] Step 2: 补货建议")
        replenishments = {}
        for sku in skus:
            asin = sku["asin"]
            daily_sales = forecasts[asin]["forecast"]["daily_avg"]
            repl = self._tool_calculate_replenishment(
                asin=asin,
                current_stock=sku.get("current_stock", 0),
                daily_sales=daily_sales,
                in_transit=sku.get("in_transit", 0),
            )
            replenishments[asin] = repl
            emoji = {"red": "!!!", "yellow": "!", "green": "OK"}
            print(f"  {asin}: [{emoji[repl['urgency']]}] "
                  f"可售{repl['days_of_stock']}天 | "
                  f"建议补{repl['order_quantity']}件")

        # Step 3: 断货风险检查
        print(f"\n[InventoryForecast] Step 3: 断货风险检查")
        inventory_status = [
            {
                "asin": sku["asin"],
                "current_stock": sku.get("current_stock", 0),
                "daily_sales": forecasts[sku["asin"]]["forecast"]["daily_avg"],
                "in_transit": sku.get("in_transit", 0),
            }
            for sku in skus
        ]
        risk_check = self._tool_check_stockout_risk(inventory_status)
        results["steps"]["risk_check"] = risk_check["risk_summary"]
        print(f"  红色: {risk_check['risk_summary']['red']} | "
              f"黄色: {risk_check['risk_summary']['yellow']} | "
              f"绿色: {risk_check['risk_summary']['green']}")

        # Step 4: 仓储成本
        print(f"\n[InventoryForecast] Step 4: 仓储成本计算")
        total_units = sum(sku.get("current_stock", 0) for sku in skus)
        storage = self._tool_calculate_storage_cost(total_units)
        results["steps"]["storage_cost"] = storage
        print(f"  总库存: {total_units}件 | 月仓储费: ${storage['monthly_storage_cost']:.2f}")

        # 汇总
        for sku in skus:
            asin = sku["asin"]
            results["sku_details"].append({
                "asin": asin,
                "product_name": sku.get("product_name", ""),
                "current_stock": sku.get("current_stock", 0),
                "forecast_daily": forecasts[asin]["forecast"]["daily_avg"],
                "days_of_stock": replenishments[asin]["days_of_stock"],
                "urgency": replenishments[asin]["urgency"],
                "order_quantity": replenishments[asin]["order_quantity"],
                "order_date": replenishments[asin]["suggested_order_date"],
            })

        results["completed_at"] = datetime.now().isoformat()
        print(f"\n[InventoryForecast] 库存分析完成！")
        return results

    def _run_replenishment_check(self, **kwargs) -> dict:
        """仅补货检查"""
        return self._tool_calculate_replenishment(
            asin=kwargs.get("asin", ""),
            current_stock=kwargs.get("current_stock", 0),
            daily_sales=kwargs.get("daily_sales", 5),
        )

    # ============================================================
    # 模拟数据
    # ============================================================

    def _get_mock_sku_list(self) -> List[dict]:
        """模拟SKU列表"""
        return [
            {"asin": "B0COMPSP02", "product_name": "200PCS Spring Assortment Kit",
             "current_stock": 150, "in_transit": 200},
            {"asin": "B0C1SPRING1", "product_name": "5Pcs Torsion Springs",
             "current_stock": 45, "in_transit": 0},
            {"asin": "B0UBOLT001", "product_name": "304 SS U-Bolt Set",
             "current_stock": 300, "in_transit": 100},
        ]

    def _get_mock_sales_history(self, asin: str) -> List[dict]:
        """模拟销售历史"""
        import random
        random.seed(hash(asin) % 100)

        base_sales = {
            "B0COMPSP02": 8,
            "B0C1SPRING1": 3,
            "B0UBOLT001": 5,
        }.get(asin, 4)

        history = []
        for i in range(90, 0, -1):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            daily = max(0, int(base_sales + random.gauss(0, base_sales * 0.3)))
            history.append({"date": date, "units": daily})

        return history

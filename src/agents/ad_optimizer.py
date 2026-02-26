"""
广告投放 Agent - Amazon PPC 广告自动优化引擎

功能：
1. 广告活动架构设计（Campaign/AdGroup/Keyword 层级）
2. 关键词竞价策略（精确/词组/广泛分层投放）
3. ACOS 优化（基于表现数据自动调价）
4. 否定关键词管理（减少无效花费）
5. 搜索词报告分析（发现新机会词）
6. 广告表现日报/周报
"""
import json
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional

from src.agents.base_agent import BaseAgent, ToolResult
from src.config.prompts import (
    AD_OPTIMIZER_SYSTEM,
    AD_CAMPAIGN_PROMPT,
    AD_OPTIMIZATION_PROMPT,
)
from src.config.settings import REPORTS_DIR


@dataclass
class KeywordBid:
    """关键词竞价"""
    keyword: str
    match_type: str  # exact / phrase / broad
    bid: float
    status: str  # active / paused
    impressions: int = 0
    clicks: int = 0
    spend: float = 0.0
    sales: float = 0.0
    orders: int = 0

    @property
    def ctr(self) -> float:
        return (self.clicks / self.impressions * 100) if self.impressions > 0 else 0.0

    @property
    def cvr(self) -> float:
        return (self.orders / self.clicks * 100) if self.clicks > 0 else 0.0

    @property
    def acos(self) -> float:
        return (self.spend / self.sales * 100) if self.sales > 0 else float('inf')

    @property
    def roas(self) -> float:
        return (self.sales / self.spend) if self.spend > 0 else 0.0


class AdOptimizerAgent(BaseAgent):
    """广告投放 Agent"""

    def __init__(self):
        super().__init__(
            name="AdOptimizer",
            system_prompt=AD_OPTIMIZER_SYSTEM,
        )

    def _register_tools(self):
        """注册广告 Agent 的可用工具"""

        self.register_tool(
            name="design_campaign",
            description="设计广告活动架构，包含Campaign/AdGroup/关键词分组",
            input_schema={
                "type": "object",
                "properties": {
                    "asin": {"type": "string"},
                    "product_name": {"type": "string"},
                    "selling_price": {"type": "number"},
                    "daily_budget": {"type": "number", "default": 20.0},
                    "target_acos": {"type": "number", "default": 25.0},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["asin", "product_name", "selling_price"],
            },
            handler=self._tool_design_campaign,
        )

        self.register_tool(
            name="optimize_bids",
            description="基于广告表现数据优化关键词竞价",
            input_schema={
                "type": "object",
                "properties": {
                    "keyword_data": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "关键词表现数据列表",
                    },
                    "target_acos": {"type": "number", "default": 25.0},
                },
                "required": ["keyword_data"],
            },
            handler=self._tool_optimize_bids,
        )

        self.register_tool(
            name="analyze_search_terms",
            description="分析搜索词报告，发现新机会词和否定词",
            input_schema={
                "type": "object",
                "properties": {
                    "search_term_data": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                },
                "required": ["search_term_data"],
            },
            handler=self._tool_analyze_search_terms,
        )

        self.register_tool(
            name="generate_ad_report",
            description="生成广告表现报告",
            input_schema={
                "type": "object",
                "properties": {
                    "campaign_data": {"type": "object"},
                    "date_range": {"type": "string"},
                },
                "required": ["campaign_data"],
            },
            handler=self._tool_generate_report,
        )

    # ============================================================
    # 工具实现
    # ============================================================

    def _tool_design_campaign(self, asin: str, product_name: str,
                               selling_price: float, daily_budget: float = 20.0,
                               target_acos: float = 25.0,
                               keywords: Optional[List[str]] = None) -> dict:
        """设计广告活动架构"""
        if not keywords:
            keywords = self._get_default_keywords(product_name)

        # 计算建议出价 (基于售价和目标ACOS)
        max_cpc = selling_price * (target_acos / 100) * 0.15  # 假设15%转化率
        base_bid = round(min(max_cpc, 1.50), 2)

        # 分层关键词结构
        campaigns = {
            "campaign_name": f"SP - {product_name[:30]} - Manual",
            "daily_budget": daily_budget,
            "target_acos": target_acos,
            "ad_groups": [
                {
                    "name": "Exact - Core Keywords",
                    "match_type": "exact",
                    "budget_pct": 50,
                    "keywords": [
                        {"keyword": kw, "bid": round(base_bid * 1.2, 2), "status": "active"}
                        for kw in keywords[:5]
                    ],
                },
                {
                    "name": "Phrase - Extended Keywords",
                    "match_type": "phrase",
                    "budget_pct": 30,
                    "keywords": [
                        {"keyword": kw, "bid": round(base_bid * 0.9, 2), "status": "active"}
                        for kw in keywords[:8]
                    ],
                },
                {
                    "name": "Broad - Discovery",
                    "match_type": "broad",
                    "budget_pct": 20,
                    "keywords": [
                        {"keyword": kw, "bid": round(base_bid * 0.7, 2), "status": "active"}
                        for kw in keywords[:5]
                    ],
                },
            ],
            "auto_campaign": {
                "name": f"SP - {product_name[:30]} - Auto",
                "daily_budget": round(daily_budget * 0.3, 2),
                "default_bid": round(base_bid * 0.6, 2),
                "purpose": "关键词挖掘，发现新的转化词后迁移到手动Campaign",
            },
            "negative_keywords": [
                "wholesale", "bulk 1000", "industrial lot",
                "used", "cheap", "free",
            ],
        }

        return campaigns

    def _tool_optimize_bids(self, keyword_data: List[dict],
                             target_acos: float = 25.0) -> dict:
        """优化关键词竞价"""
        optimizations = {
            "increase_bid": [],   # 高效词加价
            "decrease_bid": [],   # 低效词降价
            "pause": [],          # 暂停烧钱词
            "maintain": [],       # 保持现状
        }

        for kw in keyword_data:
            keyword = kw.get("keyword", "")
            current_bid = kw.get("bid", 0.5)
            acos = kw.get("acos", 0)
            clicks = kw.get("clicks", 0)
            impressions = kw.get("impressions", 0)
            orders = kw.get("orders", 0)
            spend = kw.get("spend", 0)

            ctr = (clicks / impressions * 100) if impressions > 0 else 0
            cvr = (orders / clicks * 100) if clicks > 0 else 0

            if orders > 0 and acos < target_acos * 0.8:
                # 高效词：ACOS远低于目标，加价抢更多流量
                new_bid = round(current_bid * 1.2, 2)
                optimizations["increase_bid"].append({
                    "keyword": keyword,
                    "current_bid": current_bid,
                    "new_bid": new_bid,
                    "reason": f"ACOS {acos:.1f}% 远低于目标 {target_acos}%，加价20%",
                    "current_acos": acos,
                })
            elif orders > 0 and acos <= target_acos * 1.2:
                # 正常表现，保持
                optimizations["maintain"].append({
                    "keyword": keyword,
                    "current_bid": current_bid,
                    "reason": f"ACOS {acos:.1f}% 在目标范围内",
                })
            elif clicks >= 20 and orders == 0:
                # 烧钱词：高点击零转化
                optimizations["pause"].append({
                    "keyword": keyword,
                    "current_bid": current_bid,
                    "wasted_spend": spend,
                    "reason": f"{clicks}次点击0转化，累计花费${spend:.2f}",
                })
            elif acos > target_acos * 1.5:
                # 低效词：ACOS过高
                new_bid = round(current_bid * 0.7, 2)
                optimizations["decrease_bid"].append({
                    "keyword": keyword,
                    "current_bid": current_bid,
                    "new_bid": new_bid,
                    "reason": f"ACOS {acos:.1f}% 远高于目标，降价30%",
                })
            else:
                optimizations["maintain"].append({
                    "keyword": keyword,
                    "current_bid": current_bid,
                    "reason": "数据不足，继续观察",
                })

        return {
            "target_acos": target_acos,
            "total_keywords": len(keyword_data),
            "optimizations": optimizations,
            "summary": {
                "increase": len(optimizations["increase_bid"]),
                "decrease": len(optimizations["decrease_bid"]),
                "pause": len(optimizations["pause"]),
                "maintain": len(optimizations["maintain"]),
            },
        }

    def _tool_analyze_search_terms(self, search_term_data: List[dict]) -> dict:
        """分析搜索词报告"""
        new_opportunities = []
        negative_candidates = []

        for st in search_term_data:
            term = st.get("search_term", "")
            clicks = st.get("clicks", 0)
            orders = st.get("orders", 0)
            spend = st.get("spend", 0)
            sales = st.get("sales", 0)

            acos = (spend / sales * 100) if sales > 0 else float('inf')
            cvr = (orders / clicks * 100) if clicks > 0 else 0

            if orders >= 2 and acos < 30:
                new_opportunities.append({
                    "search_term": term,
                    "orders": orders,
                    "acos": round(acos, 1),
                    "recommendation": "添加为精确匹配关键词",
                })
            elif clicks >= 15 and orders == 0:
                negative_candidates.append({
                    "search_term": term,
                    "clicks": clicks,
                    "wasted_spend": spend,
                    "recommendation": "添加为否定关键词",
                })

        return {
            "new_opportunities": new_opportunities,
            "negative_candidates": negative_candidates,
            "opportunity_count": len(new_opportunities),
            "negative_count": len(negative_candidates),
        }

    def _tool_generate_report(self, campaign_data: dict,
                               date_range: str = "Last 7 days") -> dict:
        """生成广告表现报告"""
        total_spend = campaign_data.get("total_spend", 0)
        total_sales = campaign_data.get("total_sales", 0)
        total_orders = campaign_data.get("total_orders", 0)
        total_clicks = campaign_data.get("total_clicks", 0)
        total_impressions = campaign_data.get("total_impressions", 0)

        acos = (total_spend / total_sales * 100) if total_sales > 0 else 0
        roas = (total_sales / total_spend) if total_spend > 0 else 0
        ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        cvr = (total_orders / total_clicks * 100) if total_clicks > 0 else 0
        cpc = (total_spend / total_clicks) if total_clicks > 0 else 0

        return {
            "date_range": date_range,
            "metrics": {
                "total_spend": round(total_spend, 2),
                "total_sales": round(total_sales, 2),
                "total_orders": total_orders,
                "acos": round(acos, 1),
                "roas": round(roas, 2),
                "ctr": round(ctr, 2),
                "cvr": round(cvr, 1),
                "cpc": round(cpc, 2),
            },
            "assessment": self._assess_performance(acos, ctr, cvr),
        }

    def _assess_performance(self, acos: float, ctr: float, cvr: float) -> str:
        """评估广告表现"""
        issues = []
        if acos > 30:
            issues.append(f"ACOS偏高({acos:.1f}%)，需优化竞价或暂停低效词")
        if ctr < 0.3:
            issues.append(f"CTR偏低({ctr:.2f}%)，需优化主图或标题")
        if cvr < 8:
            issues.append(f"CVR偏低({cvr:.1f}%)，需优化Listing或调整关键词精准度")

        if not issues:
            return "广告表现良好，各指标在健康范围内"
        return "需要优化: " + "; ".join(issues)

    # ============================================================
    # 核心业务逻辑
    # ============================================================

    def run(self, task: str, **kwargs) -> dict:
        """执行广告优化任务"""
        task_type = kwargs.get("task_type", "full_optimization")

        if task_type == "design":
            return self._run_campaign_design(**kwargs)
        elif task_type == "optimize":
            return self._run_bid_optimization(**kwargs)
        elif task_type == "full_optimization":
            return self._run_full_optimization(**kwargs)
        elif task_type == "agent_loop":
            return self.run_agent_loop(task, **kwargs)
        else:
            return self._run_full_optimization(**kwargs)

    def _run_full_optimization(self, **kwargs) -> dict:
        """完整广告优化流程"""
        asin = kwargs.get("asin", "B0COMPSP02")
        product_name = kwargs.get("product_name", "200PCS Spring Assortment Kit")
        selling_price = kwargs.get("selling_price", 8.99)

        print(f"\n[AdOptimizer] 开始广告优化: {product_name}")

        results = {
            "started_at": datetime.now().isoformat(),
            "steps": {},
        }

        # Step 1: 设计广告架构
        print(f"\n[AdOptimizer] Step 1: 设计广告活动架构")
        campaign = self._tool_design_campaign(
            asin=asin,
            product_name=product_name,
            selling_price=selling_price,
        )
        results["steps"]["campaign_design"] = {
            "campaign_name": campaign["campaign_name"],
            "ad_groups": len(campaign["ad_groups"]),
            "daily_budget": campaign["daily_budget"],
        }
        print(f"  创建 {len(campaign['ad_groups'])} 个广告组 + 1 个自动Campaign")

        # Step 2: 模拟运行数据 & 优化竞价
        print(f"\n[AdOptimizer] Step 2: 分析广告数据 & 优化竞价")
        mock_performance = self._get_mock_keyword_performance()
        optimization = self._tool_optimize_bids(mock_performance)
        results["steps"]["bid_optimization"] = optimization["summary"]
        print(f"  加价: {optimization['summary']['increase']} | "
              f"降价: {optimization['summary']['decrease']} | "
              f"暂停: {optimization['summary']['pause']} | "
              f"保持: {optimization['summary']['maintain']}")

        # Step 3: 搜索词分析
        print(f"\n[AdOptimizer] Step 3: 搜索词报告分析")
        mock_search_terms = self._get_mock_search_terms()
        search_analysis = self._tool_analyze_search_terms(mock_search_terms)
        results["steps"]["search_term_analysis"] = {
            "new_opportunities": search_analysis["opportunity_count"],
            "negative_candidates": search_analysis["negative_count"],
        }
        print(f"  发现 {search_analysis['opportunity_count']} 个新机会词, "
              f"{search_analysis['negative_count']} 个否定词候选")

        # Step 4: 生成报告
        print(f"\n[AdOptimizer] Step 4: 生成广告表现报告")
        mock_campaign_data = {
            "total_spend": 156.78,
            "total_sales": 589.32,
            "total_orders": 42,
            "total_clicks": 892,
            "total_impressions": 45600,
        }
        report = self._tool_generate_report(mock_campaign_data)
        results["steps"]["report"] = report

        results["campaign"] = campaign
        results["optimization"] = optimization
        results["search_analysis"] = search_analysis
        results["report"] = report
        results["completed_at"] = datetime.now().isoformat()

        print(f"\n[AdOptimizer] 广告优化完成！ACOS: {report['metrics']['acos']}%")
        return results

    def _run_campaign_design(self, **kwargs) -> dict:
        """仅设计广告架构"""
        return self._tool_design_campaign(
            asin=kwargs.get("asin", "B0COMPSP02"),
            product_name=kwargs.get("product_name", "Spring Kit"),
            selling_price=kwargs.get("selling_price", 8.99),
            keywords=kwargs.get("keywords"),
        )

    def _run_bid_optimization(self, **kwargs) -> dict:
        """仅优化竞价"""
        keyword_data = kwargs.get("keyword_data", self._get_mock_keyword_performance())
        return self._tool_optimize_bids(keyword_data)

    # ============================================================
    # 辅助方法
    # ============================================================

    def _get_default_keywords(self, product_name: str) -> List[str]:
        """获取默认关键词"""
        name_lower = product_name.lower()
        if "spring" in name_lower:
            return [
                "compression spring kit", "spring assortment",
                "small springs", "stainless steel springs",
                "spring set hardware", "compression spring assortment",
                "replacement springs", "mini spring kit",
            ]
        elif "bolt" in name_lower or "screw" in name_lower:
            return [
                "stainless steel bolts", "bolt assortment kit",
                "hex bolt set", "machine screw kit",
                "U bolt stainless", "bolt and nut set",
            ]
        return [
            "hardware kit", "fastener assortment",
            "stainless steel hardware", "repair kit",
        ]

    def _get_mock_keyword_performance(self) -> List[dict]:
        """模拟关键词表现数据"""
        return [
            {"keyword": "compression spring kit", "bid": 0.85, "impressions": 12000,
             "clicks": 180, "spend": 45.90, "sales": 215.73, "orders": 18, "acos": 21.3},
            {"keyword": "spring assortment", "bid": 0.72, "impressions": 8500,
             "clicks": 120, "spend": 32.40, "sales": 143.82, "orders": 12, "acos": 22.5},
            {"keyword": "small springs", "bid": 0.65, "impressions": 6200,
             "clicks": 85, "spend": 21.25, "sales": 53.94, "orders": 4, "acos": 39.4},
            {"keyword": "stainless steel springs", "bid": 0.78, "impressions": 4800,
             "clicks": 52, "spend": 15.60, "sales": 89.90, "orders": 7, "acos": 17.4},
            {"keyword": "metal spring set", "bid": 0.55, "impressions": 3200,
             "clicks": 28, "spend": 11.20, "sales": 0, "orders": 0, "acos": 0},
            {"keyword": "spring replacement parts", "bid": 0.60, "impressions": 2100,
             "clicks": 15, "spend": 6.75, "sales": 17.98, "orders": 1, "acos": 37.5},
        ]

    def _get_mock_search_terms(self) -> List[dict]:
        """模拟搜索词报告"""
        return [
            {"search_term": "trash can spring replacement", "clicks": 45,
             "orders": 5, "spend": 18.90, "sales": 44.95},
            {"search_term": "compression spring for 3d printer", "clicks": 22,
             "orders": 0, "spend": 9.90, "sales": 0},
            {"search_term": "spring kit for recliner", "clicks": 38,
             "orders": 3, "spend": 15.20, "sales": 26.97},
            {"search_term": "jewelry making springs", "clicks": 18,
             "orders": 0, "spend": 7.20, "sales": 0},
            {"search_term": "heavy duty garage door spring", "clicks": 25,
             "orders": 0, "spend": 12.50, "sales": 0},
        ]

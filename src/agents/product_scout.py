"""
智能选品 Agent - 核心选品分析引擎

功能：
1. 关键词扩展：从种子词发现长尾机会
2. 市场扫描：批量采集 Amazon 搜索结果
3. 初筛过滤：规则引擎硬过滤
4. 深度分析：LLM 差评分析 + 竞争格局
5. 综合评分：多维度加权打分
6. 报告生成：输出结构化选品报告
"""
import json
from datetime import datetime
from typing import List, Optional

from src.agents.base_agent import BaseAgent, ToolResult
from src.config.prompts import (
    PRODUCT_SCOUT_SYSTEM, KEYWORD_EXPANSION_PROMPT,
    REVIEW_ANALYSIS_PROMPT, COMPETITION_ANALYSIS_PROMPT,
    SCOUT_REPORT_PROMPT,
)
from src.config.settings import PRODUCT_FILTER_RULES, SCORING_WEIGHTS
from src.config.factory_catalog import match_product_to_factory, FACTORY_CATALOG
from src.tools.fba_calculator import calculate_fba_profit, quick_estimate_hardware


class ProductScoutAgent(BaseAgent):
    """智能选品 Agent"""

    def __init__(self):
        super().__init__(
            name="ProductScout",
            system_prompt=PRODUCT_SCOUT_SYSTEM,
        )

    def _register_tools(self):
        """注册选品 Agent 的可用工具"""

        self.register_tool(
            name="search_amazon_products",
            description="搜索 Amazon 产品并返回搜索结果列表，包含价格、评分、评论数、BSR等数据",
            input_schema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词"},
                    "max_results": {"type": "integer", "default": 20, "description": "返回结果数量"},
                },
                "required": ["keyword"],
            },
            handler=self._tool_search_amazon,
        )

        self.register_tool(
            name="analyze_reviews",
            description="分析指定ASIN的差评（1-3星），提取用户痛点和改进机会",
            input_schema={
                "type": "object",
                "properties": {
                    "asin": {"type": "string", "description": "Amazon产品ASIN"},
                    "max_reviews": {"type": "integer", "default": 30},
                },
                "required": ["asin"],
            },
            handler=self._tool_analyze_reviews,
        )

        self.register_tool(
            name="calculate_profitability",
            description="计算产品在 Amazon FBA 模式下的利润率",
            input_schema={
                "type": "object",
                "properties": {
                    "selling_price": {"type": "number", "description": "售价USD"},
                    "product_cost_rmb": {"type": "number", "description": "产品成本RMB"},
                    "weight_grams": {"type": "number", "description": "重量克", "default": 100},
                },
                "required": ["selling_price", "product_cost_rmb"],
            },
            handler=self._tool_calculate_profit,
        )

        self.register_tool(
            name="check_factory_capability",
            description="检查工厂是否能生产指定产品，返回匹配度和生产参数",
            input_schema={
                "type": "object",
                "properties": {
                    "product_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "产品关键词列表",
                    },
                },
                "required": ["product_keywords"],
            },
            handler=self._tool_check_factory,
        )

        self.register_tool(
            name="filter_candidates",
            description="对一批产品应用初筛规则，过滤不符合条件的",
            input_schema={
                "type": "object",
                "properties": {
                    "products": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "产品列表",
                    },
                },
                "required": ["products"],
            },
            handler=self._tool_filter_candidates,
        )

    # ============================================================
    # 工具实现
    # ============================================================

    def _tool_search_amazon(self, keyword: str, max_results: int = 20) -> dict:
        """
        搜索 Amazon 产品

        MVP 阶段：返回模拟数据 / 调用已有的数据缓存
        正式阶段：接入 Amazon SP-API 或 Playwright 爬虫
        """
        # MVP: 从已有市场调研数据返回
        # 实际部署时替换为 SP-API 调用
        mock_data = self._get_cached_or_mock_data(keyword)
        return {
            "keyword": keyword,
            "total_results": mock_data.get("total_results", 0),
            "products": mock_data.get("products", [])[:max_results],
            "source": "cache" if mock_data.get("from_cache") else "mock",
        }

    def _tool_analyze_reviews(self, asin: str, max_reviews: int = 30) -> dict:
        """
        分析差评

        MVP 阶段：返回模拟分析结果
        正式阶段：Playwright 爬取评论 → LLM 分析
        """
        # MVP: 模拟差评分析结果（基于已有的市场调研）
        return {
            "asin": asin,
            "total_reviews_analyzed": max_reviews,
            "pain_points": [
                {
                    "category": "尺寸规格",
                    "description": "产品尺寸与实际需求不匹配",
                    "frequency": "高",
                    "mention_count": 12,
                    "improvability": "中等",
                    "improvement_suggestion": "提供多尺寸套装或可调节设计",
                    "competitive_advantage": "强",
                },
                {
                    "category": "质量",
                    "description": "材质不够耐用，使用几个月后失效",
                    "frequency": "中",
                    "mention_count": 8,
                    "improvability": "容易",
                    "improvement_suggestion": "使用更高品质的304不锈钢，加粗线径",
                    "competitive_advantage": "强",
                },
                {
                    "category": "包装",
                    "description": "缺少安装说明或规格标注不清",
                    "frequency": "低",
                    "mention_count": 4,
                    "improvability": "容易",
                    "improvement_suggestion": "附上详细安装指南和规格对照表",
                    "competitive_advantage": "中",
                },
            ],
            "overall_assessment": "差评集中在规格匹配和耐用性，均可通过工厂改进解决",
            "source": "mock",
        }

    def _tool_calculate_profit(self, selling_price: float,
                                product_cost_rmb: float,
                                weight_grams: float = 100) -> dict:
        """计算 FBA 利润"""
        result = quick_estimate_hardware(
            selling_price=selling_price,
            product_cost_rmb=product_cost_rmb,
            weight_grams=weight_grams,
        )
        return result.to_dict()

    def _tool_check_factory(self, product_keywords: List[str]) -> dict:
        """检查工厂生产能力"""
        matches = match_product_to_factory(product_keywords)
        if matches:
            best = matches[0]
            return {
                "match_found": True,
                "best_match": best,
                "all_matches": matches[:3],
                "can_produce": best["match_score"] >= 5,
                "recommendation": (
                    "工厂可直接生产" if best["match_score"] >= 10
                    else "工厂需小幅调整后可生产" if best["match_score"] >= 5
                    else "需进一步评估"
                ),
            }
        return {
            "match_found": False,
            "can_produce": False,
            "recommendation": "工厂现有产品线无法覆盖，需要外部采购",
        }

    def _tool_filter_candidates(self, products: List[dict]) -> dict:
        """初筛过滤"""
        rules = PRODUCT_FILTER_RULES
        passed = []
        filtered_out = []

        for p in products:
            reasons = []

            if p.get("monthly_sales_est", 0) < rules["min_monthly_sales"]:
                reasons.append(f"月销量{p.get('monthly_sales_est', 0)} < {rules['min_monthly_sales']}")

            if p.get("price", 0) < rules["min_price"]:
                reasons.append(f"售价${p.get('price', 0)} < ${rules['min_price']}")

            if p.get("price", 0) > rules["max_price"]:
                reasons.append(f"售价${p.get('price', 0)} > ${rules['max_price']}")

            if p.get("review_count", 0) > rules["max_top1_review_count"]:
                reasons.append(f"评论数{p.get('review_count', 0)} > {rules['max_top1_review_count']}")

            avg_rating = p.get("rating", 5.0)
            # 评分太高说明改进空间小（反直觉但合理）
            # 这里不过滤，在评分阶段降权

            if reasons:
                filtered_out.append({"product": p, "reasons": reasons})
            else:
                passed.append(p)

        return {
            "total_input": len(products),
            "passed": len(passed),
            "filtered_out": len(filtered_out),
            "passed_products": passed,
            "filter_details": filtered_out[:5],  # 只返回前5个被过滤的原因
        }

    # ============================================================
    # 核心业务逻辑
    # ============================================================

    def run(self, task: str, **kwargs) -> dict:
        """
        执行选品分析任务

        支持两种模式：
        1. Agent Loop 模式：LLM 自主规划步骤（灵活但消耗更多 token）
        2. Pipeline 模式：固定流程执行（确定性高，成本低）
        """
        mode = kwargs.get("mode", "pipeline")

        if mode == "agent_loop":
            return self.run_agent_loop(task, **kwargs)
        else:
            return self.run_pipeline(task, **kwargs)

    def run_pipeline(self, task: str, seed_keywords: Optional[List[str]] = None,
                     **kwargs) -> dict:
        """
        Pipeline 模式：固定选品流程

        Step 1: 关键词 → 搜索
        Step 2: 搜索结果 → 初筛
        Step 3: 初筛通过 → 利润计算 + 工厂匹配
        Step 4: 综合评分 → 排序
        Step 5: Top N → 生成报告
        """
        if not seed_keywords:
            seed_keywords = self._extract_keywords_from_task(task)

        results = {
            "task": task,
            "seed_keywords": seed_keywords,
            "started_at": datetime.now().isoformat(),
            "steps": {},
        }

        # Step 1: 市场扫描
        print(f"\n[ProductScout] Step 1: 市场扫描 ({len(seed_keywords)} 个关键词)")
        all_products = []
        for kw in seed_keywords:
            search_result = self._tool_search_amazon(kw)
            all_products.extend(search_result["products"])
            print(f"  - '{kw}': {len(search_result['products'])} 个产品")

        # 去重（按 ASIN）
        seen_asins = set()
        unique_products = []
        for p in all_products:
            asin = p.get("asin", "")
            if asin and asin not in seen_asins:
                seen_asins.add(asin)
                unique_products.append(p)

        results["steps"]["scan"] = {
            "total_keywords": len(seed_keywords),
            "total_products_found": len(all_products),
            "unique_products": len(unique_products),
        }
        print(f"  扫描完成: {len(unique_products)} 个唯一产品")

        # Step 2: 初筛过滤
        print(f"\n[ProductScout] Step 2: 初筛过滤")
        filter_result = self._tool_filter_candidates(unique_products)
        passed_products = filter_result["passed_products"]
        results["steps"]["filter"] = {
            "input": filter_result["total_input"],
            "passed": filter_result["passed"],
            "filtered_out": filter_result["filtered_out"],
        }
        print(f"  通过初筛: {filter_result['passed']}/{filter_result['total_input']}")

        # Step 3: 利润计算 + 工厂匹配
        print(f"\n[ProductScout] Step 3: 利润计算 + 工厂匹配")
        scored_products = []
        for p in passed_products:
            # 利润计算
            price = p.get("price", 10.0)
            cost_rmb = self._estimate_product_cost(p)
            weight = p.get("weight_grams", 100)
            profit = self._tool_calculate_profit(price, cost_rmb, weight)

            # 工厂匹配
            keywords = [p.get("title", ""), p.get("category", "")]
            factory = self._tool_check_factory(keywords)

            # 综合评分
            score = self._calculate_score(p, profit, factory)

            scored_products.append({
                **p,
                "profit_analysis": profit,
                "factory_match": factory,
                "scores": score,
                "total_score": score["total"],
            })

        # 按总分排序
        scored_products.sort(key=lambda x: x["total_score"], reverse=True)
        results["steps"]["scoring"] = {
            "scored_count": len(scored_products),
            "top_score": scored_products[0]["total_score"] if scored_products else 0,
        }
        print(f"  评分完成: {len(scored_products)} 个产品已评分")

        # Step 4: 生成报告
        print(f"\n[ProductScout] Step 4: 生成选品报告")
        top_n = min(10, len(scored_products))
        report = self._generate_report(scored_products[:top_n], results)

        results["report"] = report
        results["top_candidates"] = scored_products[:top_n]
        results["completed_at"] = datetime.now().isoformat()

        print(f"\n[ProductScout] 选品分析完成！Top {top_n} 候选产品已生成。")
        return results

    def _calculate_score(self, product: dict, profit: dict,
                         factory: dict) -> dict:
        """多维度评分"""
        weights = SCORING_WEIGHTS

        # 需求评分
        monthly_sales = product.get("monthly_sales_est", 0)
        if monthly_sales >= 500:
            demand = 90
        elif monthly_sales >= 200:
            demand = 70
        elif monthly_sales >= 100:
            demand = 50
        else:
            demand = 20

        # 竞争评分（评论越少越好）
        reviews = product.get("review_count", 0)
        if reviews < 50:
            competition = 95
        elif reviews < 200:
            competition = 80
        elif reviews < 500:
            competition = 60
        elif reviews < 1000:
            competition = 40
        else:
            competition = 15

        # 利润评分
        margin = profit.get("profit_margin", 0)
        if margin >= 0.40:
            profit_score = 95
        elif margin >= 0.30:
            profit_score = 80
        elif margin >= 0.20:
            profit_score = 60
        elif margin >= 0.15:
            profit_score = 40
        else:
            profit_score = 15

        # 改进空间（评分越低机会越大）
        rating = product.get("rating", 5.0)
        if rating <= 3.5:
            improvement = 95
        elif rating <= 4.0:
            improvement = 75
        elif rating <= 4.3:
            improvement = 55
        elif rating <= 4.5:
            improvement = 35
        else:
            improvement = 15

        # 工厂匹配评分
        factory_score = factory.get("best_match", {}).get("match_score", 0)
        if factory_score >= 10:
            factory_s = 100
        elif factory_score >= 5:
            factory_s = 70
        elif factory_score > 0:
            factory_s = 40
        else:
            factory_s = 0

        # 趋势评分（MVP阶段简化为中性）
        trend = 50

        # 加权总分
        total = (
            demand * weights["demand_score"]
            + competition * weights["competition_score"]
            + profit_score * weights["profit_score"]
            + improvement * weights["improvement_score"]
            + factory_s * weights["factory_match_score"]
            + trend * weights["trend_score"]
        )

        return {
            "demand": demand,
            "competition": competition,
            "profit": profit_score,
            "improvement": improvement,
            "factory_match": factory_s,
            "trend": trend,
            "total": round(total, 1),
        }

    def _generate_report(self, top_products: list, run_results: dict) -> str:
        """生成 Markdown 选品报告"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        steps = run_results.get("steps", {})

        lines = [
            f"# 选品分析报告",
            f"",
            f"**生成时间**: {now}",
            f"**分析范围**: {run_results.get('task', '')}",
            f"**种子关键词**: {', '.join(run_results.get('seed_keywords', []))}",
            f"**扫描SKU数**: {steps.get('scan', {}).get('unique_products', 0)}",
            f"**通过初筛**: {steps.get('filter', {}).get('passed', 0)}",
            f"**评分产品数**: {steps.get('scoring', {}).get('scored_count', 0)}",
            f"",
            f"---",
            f"",
            f"## 推荐排名",
            f"",
            f"| # | 产品 | ASIN | 综合评分 | 售价 | 利润率 | 工厂 | 核心机会 |",
            f"|---|------|------|---------|------|--------|------|---------|",
        ]

        for i, p in enumerate(top_products, 1):
            title = (p.get("title", "")[:30] + "...") if len(p.get("title", "")) > 30 else p.get("title", "")
            asin = p.get("asin", "N/A")
            score = p.get("total_score", 0)
            price = p.get("price", 0)
            margin = p.get("profit_analysis", {}).get("profit_margin", 0)
            factory = "直产" if p.get("factory_match", {}).get("can_produce") else "需采购"
            # 根据评分判断核心机会
            if p.get("scores", {}).get("improvement", 0) >= 75:
                opportunity = "差评多，品质提升空间大"
            elif p.get("scores", {}).get("competition", 0) >= 80:
                opportunity = "竞争度低，蓝海机会"
            else:
                opportunity = "综合得分较高"

            lines.append(
                f"| {i} | {title} | {asin} | {score} | ${price:.2f} | "
                f"{margin:.1%} | {factory} | {opportunity} |"
            )

        lines.extend([
            f"",
            f"---",
            f"",
            f"## 详细分析",
            f"",
        ])

        # 前3名详细分析
        for i, p in enumerate(top_products[:3], 1):
            scores = p.get("scores", {})
            profit = p.get("profit_analysis", {})
            factory = p.get("factory_match", {})

            lines.extend([
                f"### #{i} {p.get('title', 'N/A')}",
                f"",
                f"**ASIN**: {p.get('asin', 'N/A')} | **品牌**: {p.get('brand', 'N/A')}",
                f"",
                f"**评分雷达**:",
                f"- 需求强度: {scores.get('demand', 0)}/100",
                f"- 竞争可行性: {scores.get('competition', 0)}/100",
                f"- 利润空间: {scores.get('profit', 0)}/100",
                f"- 改进空间: {scores.get('improvement', 0)}/100",
                f"- 工厂匹配: {scores.get('factory_match', 0)}/100",
                f"",
                f"**利润测算**:",
                f"- 售价: ${profit.get('selling_price', 0):.2f}",
                f"- FBA费: ${profit.get('fba_fulfillment_fee', 0):.2f}",
                f"- 佣金: ${profit.get('referral_fee', 0):.2f}",
                f"- 净利: ${profit.get('net_profit', 0):.2f} ({profit.get('profit_margin', 0):.1%})",
                f"",
                f"**工厂匹配**: {factory.get('recommendation', 'N/A')}",
                f"",
                f"---",
                f"",
            ])

        lines.extend([
            f"## 下一步建议",
            f"",
            f"1. 对 Top 3 产品进行差评深度分析（需爬取真实评论数据）",
            f"2. 与工厂确认生产规格和成本",
            f"3. 计算完整的利润模型（含广告费预估）",
            f"4. 选择 1-2 个产品启动小批量测试",
            f"",
            f"---",
            f"*报告由 ProductScout Agent 自动生成*",
        ])

        return "\n".join(lines)

    def _extract_keywords_from_task(self, task: str) -> List[str]:
        """从任务描述中提取关键词（简单实现）"""
        # MVP: 预设关键词映射
        keyword_map = {
            "弹簧": ["trash can spring replacement", "compression spring kit",
                     "torsion spring replacement", "recliner spring repair kit"],
            "spring": ["trash can spring replacement", "compression spring kit",
                       "torsion spring replacement"],
            "螺栓": ["stainless steel U bolts", "hex bolt assortment kit",
                     "marine U bolts boat trailer"],
            "bolt": ["stainless steel U bolts", "hex bolt assortment kit"],
            "挂钩": ["heavy duty S hooks", "hammock hardware kit",
                     "swing hook stainless steel"],
            "hook": ["heavy duty S hooks", "hammock hardware kit"],
            "卡簧": ["snap ring assortment", "retaining ring kit", "E-clip set"],
            "五金": ["hardware assortment kit", "stainless steel fastener kit"],
        }

        found_keywords = []
        task_lower = task.lower()
        for key, kws in keyword_map.items():
            if key in task_lower or key in task:
                found_keywords.extend(kws)

        if not found_keywords:
            # 默认返回工厂核心品类关键词
            found_keywords = [
                "trash can spring replacement",
                "compression spring assortment kit",
                "stainless steel U bolts",
            ]

        return list(set(found_keywords))

    def _estimate_product_cost(self, product: dict) -> float:
        """估算产品生产成本 (RMB)"""
        # 基于工厂目录的成本范围估算
        keywords = [product.get("title", ""), product.get("category", "")]
        matches = match_product_to_factory(keywords)
        if matches:
            cost_range = matches[0].get("unit_cost_range_rmb", (1.0, 3.0))
            return (cost_range[0] + cost_range[1]) / 2  # 取中间值
        return 3.0  # 默认

    def _get_cached_or_mock_data(self, keyword: str) -> dict:
        """获取缓存数据或生成模拟数据"""
        # 基于已有的市场调研数据
        mock_db = {
            "trash can spring replacement": {
                "total_results": 880,
                "from_cache": True,
                "products": [
                    {"asin": "B0C1SPRING1", "title": "5 Pcs Universal Adjustable 3-Coil Torsion Springs",
                     "price": 7.99, "rating": 4.4, "review_count": 11, "bsr_rank": 45632,
                     "monthly_sales_est": 150, "brand": "Cilky", "category": "Springs",
                     "weight_grams": 80},
                    {"asin": "B0C2SPRING2", "title": "10pcs Garbage Can Adjustable 3 Coils Torsion Spring",
                     "price": 4.59, "rating": 3.4, "review_count": 15, "bsr_rank": 52100,
                     "monthly_sales_est": 120, "brand": "FUNOMOCYA", "category": "Springs",
                     "weight_grams": 100},
                    {"asin": "B0C3SPRING3", "title": "5Pcs Adjustable 3-Coil Torsion Springs for Trash Can",
                     "price": 6.98, "rating": 3.6, "review_count": 4, "bsr_rank": 68000,
                     "monthly_sales_est": 80, "brand": "Generic", "category": "Springs",
                     "weight_grams": 75},
                    {"asin": "B0C4SPRING4", "title": "4 Pcs Garbage Can Adjustable Torsion Spring Replacement",
                     "price": 6.99, "rating": 5.0, "review_count": 2, "bsr_rank": 95000,
                     "monthly_sales_est": 40, "brand": "NewBrand", "category": "Springs",
                     "weight_grams": 60},
                    {"asin": "B0C5SPRING5", "title": "Mipcase Small Torsion Spring Set for Garbage Can Lid",
                     "price": 6.16, "rating": 3.5, "review_count": 6, "bsr_rank": 72000,
                     "monthly_sales_est": 65, "brand": "Mipcase", "category": "Springs",
                     "weight_grams": 90},
                ],
            },
            "compression spring kit": {
                "total_results": 5000,
                "from_cache": True,
                "products": [
                    {"asin": "B0BVTDP29W", "title": "Dianrui 300PCS Compression Springs Assortment Kit",
                     "price": 6.99, "rating": 4.6, "review_count": 702, "bsr_rank": 1236,
                     "monthly_sales_est": 2740, "brand": "Dianrui", "category": "Springs",
                     "weight_grams": 130},
                    {"asin": "B0COMPSP02", "title": "200PCS Spring Assortment Kit 20 Sizes Compression Springs",
                     "price": 8.99, "rating": 4.3, "review_count": 156, "bsr_rank": 5800,
                     "monthly_sales_est": 500, "brand": "Generic", "category": "Springs",
                     "weight_grams": 110},
                ],
            },
            "stainless steel U bolts": {
                "total_results": 4000,
                "from_cache": True,
                "products": [
                    {"asin": "B0UBOLT001", "title": "4 Sets M8 U-Bolts 1.5\" Wide 304 Stainless Steel",
                     "price": 14.99, "rating": 4.5, "review_count": 45, "bsr_rank": 12000,
                     "monthly_sales_est": 200, "brand": "SRZTXU", "category": "Bolts",
                     "weight_grams": 250},
                    {"asin": "B0CF8LB4PF", "title": "Foliv Grade 8 Bolt Assortment Kit 523PCS",
                     "price": 49.99, "rating": 4.7, "review_count": 540, "bsr_rank": 11320,
                     "monthly_sales_est": 561, "brand": "Foliv", "category": "Bolts",
                     "weight_grams": 3200},
                    {"asin": "B0UBOLT003", "title": "8 Sets Round U Bolts 3/4\" Wide 304 Stainless Steel",
                     "price": 9.99, "rating": 4.2, "review_count": 28, "bsr_rank": 18000,
                     "monthly_sales_est": 150, "brand": "Generic", "category": "Bolts",
                     "weight_grams": 300},
                ],
            },
        }

        # 尝试匹配
        keyword_lower = keyword.lower()
        for key, data in mock_db.items():
            if key in keyword_lower or keyword_lower in key:
                return data

        # 默认返回空
        return {
            "total_results": 0,
            "from_cache": False,
            "products": [],
        }

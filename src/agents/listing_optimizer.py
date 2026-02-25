"""
Listing 优化 Agent - 产品页面文案生成与优化引擎

功能：
1. 竞品 Listing 分析：拆解 Top10 竞品标题结构、关键词布局、卖点提炼
2. 标题生成：基于关键词+卖点生成多个候选标题，符合 Amazon 规范
3. 五点描述生成：基于差评痛点反向包装卖点，突出差异化
4. 产品描述/A+ 内容：品牌故事、场景化描述、技术参数展示
5. 关键词优化：提取高相关关键词，嵌入标题和后台搜索词
6. 多语言本地化：英/德/日 Listing 翻译，保持营销力
"""
import json
import re
from datetime import datetime
from typing import Dict, List, Optional

from src.agents.base_agent import BaseAgent, ToolResult
from src.config.prompts import (
    LISTING_OPTIMIZER_SYSTEM,
    COMPETITOR_LISTING_ANALYSIS_PROMPT,
    LISTING_GENERATION_PROMPT,
    LISTING_LOCALIZATION_PROMPT,
)
from src.config.settings import REPORTS_DIR


class ListingOptimizerAgent(BaseAgent):
    """Listing 优化 Agent"""

    def __init__(self):
        super().__init__(
            name="ListingOptimizer",
            system_prompt=LISTING_OPTIMIZER_SYSTEM,
        )

    def _register_tools(self):
        """注册 Listing 优化 Agent 的可用工具"""

        self.register_tool(
            name="fetch_competitor_listings",
            description="采集指定关键词下 Top N 竞品的 Listing 数据（标题、五点、描述、关键词）",
            input_schema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "品类关键词"},
                    "top_n": {"type": "integer", "default": 10, "description": "采集数量"},
                },
                "required": ["keyword"],
            },
            handler=self._tool_fetch_competitor_listings,
        )

        self.register_tool(
            name="extract_keywords",
            description="从竞品 Listing 中提取高频关键词，按频次排序",
            input_schema={
                "type": "object",
                "properties": {
                    "listings": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "竞品 Listing 列表",
                    },
                },
                "required": ["listings"],
            },
            handler=self._tool_extract_keywords,
        )

        self.register_tool(
            name="generate_listing",
            description="基于产品信息和竞品分析结果生成完整 Listing（标题x3 + 五点 + 描述 + 后台词）",
            input_schema={
                "type": "object",
                "properties": {
                    "product_info": {"type": "object", "description": "产品基本信息"},
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "目标关键词列表",
                    },
                    "pain_points": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "竞品差评痛点",
                    },
                },
                "required": ["product_info", "keywords"],
            },
            handler=self._tool_generate_listing,
        )

        self.register_tool(
            name="validate_listing",
            description="验证 Listing 是否符合 Amazon 规范（字符长度、禁用词、格式等）",
            input_schema={
                "type": "object",
                "properties": {
                    "listing": {"type": "object", "description": "待验证的 Listing 数据"},
                },
                "required": ["listing"],
            },
            handler=self._tool_validate_listing,
        )

        self.register_tool(
            name="localize_listing",
            description="将英文 Listing 本地化翻译为目标语言（保持营销力）",
            input_schema={
                "type": "object",
                "properties": {
                    "listing": {"type": "object", "description": "英文 Listing"},
                    "target_language": {"type": "string", "description": "目标语言: de/ja/fr/es"},
                },
                "required": ["listing", "target_language"],
            },
            handler=self._tool_localize_listing,
        )

    # ============================================================
    # 工具实现
    # ============================================================

    def _tool_fetch_competitor_listings(self, keyword: str, top_n: int = 10) -> dict:
        """
        采集竞品 Listing 数据

        MVP: 返回模拟数据
        正式: Playwright 爬取 Amazon 产品页 / SP-API
        """
        mock_listings = self._get_mock_competitor_listings(keyword)
        return {
            "keyword": keyword,
            "total_fetched": len(mock_listings[:top_n]),
            "listings": mock_listings[:top_n],
            "source": "mock",
        }

    def _tool_extract_keywords(self, listings: List[dict]) -> dict:
        """从竞品 Listing 提取高频关键词"""
        word_freq: Dict[str, int] = {}
        stop_words = {
            "the", "a", "an", "and", "or", "for", "with", "in", "on", "to",
            "of", "is", "are", "it", "its", "by", "from", "at", "as", "be",
            "this", "that", "pcs", "set", "kit", "pack", "-", "&", "/",
        }

        for listing in listings:
            # 从标题提取
            title = listing.get("title", "").lower()
            words = re.findall(r'[a-z]+(?:\s+[a-z]+)?', title)
            for word in words:
                word = word.strip()
                if word and word not in stop_words and len(word) > 2:
                    word_freq[word] = word_freq.get(word, 0) + 2  # 标题权重x2

            # 从五点提取
            for bp in listing.get("bullet_points", []):
                bp_words = re.findall(r'[a-z]+(?:\s+[a-z]+)?', bp.lower())
                for word in bp_words:
                    word = word.strip()
                    if word and word not in stop_words and len(word) > 2:
                        word_freq[word] = word_freq.get(word, 0) + 1

        # 按频次排序
        sorted_keywords = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)

        return {
            "total_unique_keywords": len(sorted_keywords),
            "top_keywords": [{"keyword": k, "frequency": v} for k, v in sorted_keywords[:30]],
            "title_keywords": [{"keyword": k, "frequency": v} for k, v in sorted_keywords[:10]],
            "longtail_keywords": [{"keyword": k, "frequency": v} for k, v in sorted_keywords[10:25]],
        }

    def _tool_generate_listing(self, product_info: dict,
                                keywords: List[str],
                                pain_points: Optional[List[str]] = None) -> dict:
        """
        生成完整 Listing

        MVP: 基于模板+规则生成
        正式: LLM 生成
        """
        brand = product_info.get("brand", "BrandName")
        product_name = product_info.get("name", "Product")
        material = product_info.get("material", "Stainless Steel")
        specs = product_info.get("specifications", "")
        quantity = product_info.get("quantity", "")
        use_case = product_info.get("use_case", "")

        top_kws = keywords[:5] if keywords else []
        kw_str = " ".join(top_kws)

        # 生成3个候选标题
        titles = [
            f"{brand} {top_kws[0].title() if top_kws else product_name} "
            f"{material} {specs} {quantity} - {use_case}".strip(),
            f"{brand} {quantity} {material} {top_kws[0].title() if top_kws else product_name} "
            f"{specs} for {use_case}".strip(),
            f"{brand} Premium {material} {top_kws[0].title() if top_kws else product_name} "
            f"{quantity} {specs} - Heavy Duty {use_case}".strip(),
        ]
        # 截断到150字符
        titles = [t[:150] for t in titles]

        # 生成五点描述
        pain_points = pain_points or []
        bullet_points = []

        # 第1条：核心差异化（基于痛点反向优化）
        if pain_points:
            bullet_points.append(
                f"SUPERIOR QUALITY DESIGN - Unlike competitors that {pain_points[0].lower()}, "
                f"our {product_name} is engineered with premium {material} for long-lasting "
                f"durability and reliable performance."
            )
        else:
            bullet_points.append(
                f"PREMIUM {material.upper()} CONSTRUCTION - Built with high-grade {material} "
                f"for exceptional durability, corrosion resistance, and long service life."
            )

        # 第2条：材质/品质
        bullet_points.append(
            f"PROFESSIONAL GRADE MATERIAL - Made from industrial-quality {material}, "
            f"resistant to rust, corrosion, and wear. Suitable for both indoor and outdoor use."
        )

        # 第3条：规格完整性
        bullet_points.append(
            f"COMPLETE {quantity.upper()} SET - Includes {specs}. "
            f"Multiple sizes to fit various applications. "
            f"Organized in a reusable storage case for easy access."
        )

        # 第4条：使用场景
        bullet_points.append(
            f"VERSATILE APPLICATIONS - Perfect for {use_case}, home repair, "
            f"automotive maintenance, industrial equipment, and DIY projects. "
            f"Works with standard tools and fixtures."
        )

        # 第5条：售后保障
        bullet_points.append(
            f"100% SATISFACTION GUARANTEE - We stand behind our product quality. "
            f"If you're not completely satisfied, contact us for a full refund or "
            f"replacement. Your satisfaction is our top priority."
        )

        # 截断每条到250字符
        bullet_points = [bp[:250] for bp in bullet_points]

        # 产品描述
        description = (
            f"Upgrade your toolkit with the {brand} {product_name}. "
            f"Crafted from premium {material}, this {quantity} set provides "
            f"everything you need for {use_case} and beyond.\n\n"
            f"Whether you're a professional contractor or a DIY enthusiast, "
            f"our {product_name} delivers the reliability and precision you demand. "
            f"Each piece is carefully manufactured to exact specifications, "
            f"ensuring a perfect fit every time.\n\n"
            f"Specifications:\n"
            f"- Material: {material}\n"
            f"- Package: {quantity}\n"
            f"- Sizes: {specs}\n"
            f"- Application: {use_case}\n\n"
            f"Order now and experience the {brand} difference!"
        )

        # 后台搜索词（不重复标题已有词）
        title_words = set()
        for t in titles:
            title_words.update(w.lower() for w in t.split())

        backend_keywords = []
        for kw in keywords:
            kw_words = kw.lower().split()
            if not all(w in title_words for w in kw_words):
                backend_keywords.append(kw)

        # 限制250字节
        backend_str = " ".join(backend_keywords)
        if len(backend_str.encode('utf-8')) > 250:
            while len(backend_str.encode('utf-8')) > 250 and backend_keywords:
                backend_keywords.pop()
                backend_str = " ".join(backend_keywords)

        return {
            "titles": titles,
            "bullet_points": bullet_points,
            "description": description,
            "backend_keywords": backend_str,
            "keyword_coverage": {
                "in_title": len([k for k in top_kws if k.lower() in titles[0].lower()]),
                "in_bullets": len(top_kws),
                "in_backend": len(backend_keywords),
            },
        }

    def _tool_validate_listing(self, listing: dict) -> dict:
        """验证 Listing 是否符合 Amazon 规范"""
        issues = []
        warnings = []

        # 标题验证
        titles = listing.get("titles", [])
        for i, title in enumerate(titles):
            if len(title) > 200:
                issues.append(f"标题{i+1}超过200字符限制 ({len(title)}字符)")
            elif len(title) > 150:
                warnings.append(f"标题{i+1}超过150字符建议长度 ({len(title)}字符)")

            if title.upper() == title:
                issues.append(f"标题{i+1}全部大写，违反规范")

            forbidden = ["sale", "best seller", "free shipping", "#1", "cheap", "discount"]
            for word in forbidden:
                if word.lower() in title.lower():
                    issues.append(f"标题{i+1}包含禁用词: '{word}'")

        # 五点验证
        bullets = listing.get("bullet_points", [])
        if len(bullets) != 5:
            warnings.append(f"五点描述数量为{len(bullets)}，建议为5条")

        for i, bp in enumerate(bullets):
            if len(bp) > 500:
                issues.append(f"五点第{i+1}条超过500字符 ({len(bp)}字符)")
            elif len(bp) < 50:
                warnings.append(f"五点第{i+1}条过短 ({len(bp)}字符)，建议150-250字符")

        # 后台搜索词验证
        backend = listing.get("backend_keywords", "")
        backend_bytes = len(backend.encode('utf-8'))
        if backend_bytes > 250:
            issues.append(f"后台搜索词超过250字节限制 ({backend_bytes}字节)")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "issue_count": len(issues),
            "warning_count": len(warnings),
        }

    def _tool_localize_listing(self, listing: dict, target_language: str) -> dict:
        """
        Listing 本地化翻译

        MVP: 返回模拟翻译结果
        正式: LLM 翻译
        """
        lang_names = {"de": "German", "ja": "Japanese", "fr": "French", "es": "Spanish"}
        lang_name = lang_names.get(target_language, target_language)

        # MVP: 模拟翻译（标注目标语言）
        localized = {
            "language": target_language,
            "language_name": lang_name,
            "titles": [f"[{lang_name}] {t}" for t in listing.get("titles", [])[:1]],
            "bullet_points": [f"[{lang_name}] {bp}" for bp in listing.get("bullet_points", [])],
            "description": f"[{lang_name}] {listing.get('description', '')[:200]}...",
            "note": f"MVP模式: 实际部署时通过LLM进行营销级{lang_name}翻译",
        }

        return localized

    # ============================================================
    # 核心业务逻辑
    # ============================================================

    def run(self, task: str, **kwargs) -> dict:
        """执行 Listing 优化任务"""
        mode = kwargs.get("mode", "pipeline")

        if mode == "agent_loop":
            return self.run_agent_loop(task, **kwargs)
        else:
            return self.run_pipeline(task, **kwargs)

    def run_pipeline(self, task: str, **kwargs) -> dict:
        """
        Pipeline 模式：固定 Listing 优化流程

        Step 1: 采集竞品 Listing
        Step 2: 提取关键词
        Step 3: 生成 Listing 文案
        Step 4: 验证规范
        Step 5: 多语言本地化（可选）
        Step 6: 生成报告
        """
        product_info = kwargs.get("product_info", {})
        keyword = kwargs.get("keyword", "compression spring kit")
        pain_points = kwargs.get("pain_points", [])
        localize_to = kwargs.get("localize_to", [])

        results = {
            "task": task,
            "started_at": datetime.now().isoformat(),
            "steps": {},
        }

        # Step 1: 采集竞品 Listing
        print(f"\n[ListingOptimizer] Step 1: 采集竞品 Listing ('{keyword}')")
        competitor_data = self._tool_fetch_competitor_listings(keyword)
        results["steps"]["competitor_fetch"] = {
            "keyword": keyword,
            "fetched_count": competitor_data["total_fetched"],
        }
        print(f"  采集到 {competitor_data['total_fetched']} 个竞品 Listing")

        # Step 2: 提取关键词
        print(f"\n[ListingOptimizer] Step 2: 提取高频关键词")
        keyword_data = self._tool_extract_keywords(competitor_data["listings"])
        top_keywords = [k["keyword"] for k in keyword_data["top_keywords"]]
        results["steps"]["keyword_extraction"] = {
            "unique_keywords": keyword_data["total_unique_keywords"],
            "top_10": keyword_data["title_keywords"],
        }
        print(f"  提取到 {keyword_data['total_unique_keywords']} 个唯一关键词")

        # Step 3: 生成 Listing
        print(f"\n[ListingOptimizer] Step 3: 生成 Listing 文案")
        listing = self._tool_generate_listing(product_info, top_keywords, pain_points)
        results["steps"]["generation"] = {
            "title_count": len(listing["titles"]),
            "bullet_count": len(listing["bullet_points"]),
            "keyword_coverage": listing["keyword_coverage"],
        }
        print(f"  生成 {len(listing['titles'])} 个候选标题 + 五点描述 + 产品描述")

        # Step 4: 验证规范
        print(f"\n[ListingOptimizer] Step 4: Amazon 规范验证")
        validation = self._tool_validate_listing(listing)
        results["steps"]["validation"] = validation
        status = "PASS" if validation["valid"] else "FAIL"
        print(f"  验证结果: {status} ({validation['issue_count']} 问题, "
              f"{validation['warning_count']} 警告)")

        # Step 5: 多语言本地化（可选）
        localizations = {}
        if localize_to:
            print(f"\n[ListingOptimizer] Step 5: 多语言本地化 ({', '.join(localize_to)})")
            for lang in localize_to:
                loc_result = self._tool_localize_listing(listing, lang)
                localizations[lang] = loc_result
                print(f"  {lang}: 本地化完成")
        results["steps"]["localization"] = {
            "languages": list(localizations.keys()),
        }

        # Step 6: 生成报告
        print(f"\n[ListingOptimizer] Step 6: 生成 Listing 优化报告")
        report = self._generate_report(
            product_info, listing, keyword_data, validation, localizations, results
        )
        results["listing"] = listing
        results["localizations"] = localizations
        results["report"] = report
        results["completed_at"] = datetime.now().isoformat()

        print(f"\n[ListingOptimizer] Listing 优化完成！")
        return results

    def _generate_report(self, product_info: dict, listing: dict,
                         keyword_data: dict, validation: dict,
                         localizations: dict, run_results: dict) -> str:
        """生成 Markdown Listing 优化报告"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        lines = [
            f"# Listing 优化报告",
            f"",
            f"**生成时间**: {now}",
            f"**产品**: {product_info.get('name', 'N/A')}",
            f"**品牌**: {product_info.get('brand', 'N/A')}",
            f"",
            f"---",
            f"",
            f"## 竞品关键词分析",
            f"",
            f"### Top 10 高频关键词",
            f"",
            f"| 排名 | 关键词 | 出现频次 |",
            f"|------|--------|---------|",
        ]

        for i, kw in enumerate(keyword_data.get("title_keywords", [])[:10], 1):
            lines.append(f"| {i} | {kw['keyword']} | {kw['frequency']} |")

        lines.extend([
            f"",
            f"---",
            f"",
            f"## 生成的 Listing",
            f"",
            f"### 候选标题",
            f"",
        ])

        for i, title in enumerate(listing.get("titles", []), 1):
            lines.append(f"**标题 {i}** ({len(title)}字符):")
            lines.append(f"> {title}")
            lines.append(f"")

        lines.extend([
            f"### 五点描述 (Bullet Points)",
            f"",
        ])

        for i, bp in enumerate(listing.get("bullet_points", []), 1):
            lines.append(f"**{i}.** {bp}")
            lines.append(f"")

        lines.extend([
            f"### 产品描述",
            f"",
            f"{listing.get('description', '')}",
            f"",
            f"### 后台搜索词",
            f"",
            f"```",
            f"{listing.get('backend_keywords', '')}",
            f"```",
            f"",
            f"---",
            f"",
            f"## 规范验证",
            f"",
            f"- 状态: {'通过' if validation.get('valid') else '未通过'}",
            f"- 问题: {validation.get('issue_count', 0)} 个",
            f"- 警告: {validation.get('warning_count', 0)} 个",
            f"",
        ])

        if validation.get("issues"):
            lines.append("**问题列表:**")
            for issue in validation["issues"]:
                lines.append(f"- {issue}")
            lines.append("")

        if validation.get("warnings"):
            lines.append("**警告列表:**")
            for warn in validation["warnings"]:
                lines.append(f"- {warn}")
            lines.append("")

        if localizations:
            lines.extend([
                f"---",
                f"",
                f"## 多语言本地化",
                f"",
            ])
            for lang, loc in localizations.items():
                lines.append(f"### {loc.get('language_name', lang)}")
                lines.append(f"")
                if loc.get("titles"):
                    lines.append(f"**标题**: {loc['titles'][0]}")
                lines.append(f"")

        lines.extend([
            f"---",
            f"*报告由 ListingOptimizer Agent 自动生成*",
        ])

        return "\n".join(lines)

    # ============================================================
    # 模拟数据
    # ============================================================

    def _get_mock_competitor_listings(self, keyword: str) -> List[dict]:
        """模拟竞品 Listing 数据"""
        mock_db = {
            "compression spring": [
                {
                    "asin": "B0BVTDP29W",
                    "title": "Dianrui 300PCS Compression Springs Assortment Kit 20 Different Sizes Small Springs Stainless Steel",
                    "brand": "Dianrui",
                    "price": 6.99,
                    "rating": 4.6,
                    "review_count": 715,
                    "bullet_points": [
                        "300PCS SPRING ASSORTMENT - Includes 20 different sizes of compression springs to meet various needs",
                        "PREMIUM STAINLESS STEEL - Made from high-quality stainless steel for durability and corrosion resistance",
                        "WIDE APPLICATION - Suitable for home repair, automotive, electronics, and industrial use",
                        "ORGANIZED STORAGE - Comes in a clear plastic case with labeled compartments for easy identification",
                        "SATISFACTION GUARANTEE - If not satisfied, contact us for a full refund",
                    ],
                    "description": "Dianrui 300PCS compression springs assortment kit provides a comprehensive selection of springs for all your needs.",
                },
                {
                    "asin": "B0COMPSP02",
                    "title": "200PCS Spring Assortment Kit 20 Sizes Compression Springs Stainless Steel for Home Repair",
                    "brand": "Generic",
                    "price": 8.99,
                    "rating": 4.3,
                    "review_count": 156,
                    "bullet_points": [
                        "200 PIECES VARIETY PACK - 20 different sizes compression springs for multiple applications",
                        "304 STAINLESS STEEL - Rust-proof and long-lasting material for extended use",
                        "PERFECT FOR DIY - Great for home repair, electronics repair, and hobby projects",
                        "ORGANIZED BOX - Labeled storage box keeps springs sorted and easy to find",
                        "MONEY BACK GUARANTEE - Full refund within 30 days if not satisfied",
                    ],
                    "description": "High quality 200PCS spring assortment kit made from 304 stainless steel.",
                },
                {
                    "asin": "B0FG2COMP3",
                    "title": "Fgruh 400PCS Compression Spring Kit 24 Sizes Heavy Duty Springs Stainless Steel Assortment",
                    "brand": "Fgruh",
                    "price": 12.99,
                    "rating": 4.5,
                    "review_count": 320,
                    "bullet_points": [
                        "400 PIECES 24 SIZES - Most comprehensive spring assortment kit on the market",
                        "HEAVY DUTY STAINLESS STEEL - Industrial grade 304 stainless steel construction",
                        "VERSATILE USE - Automotive, marine, HVAC, electronics, and general hardware",
                        "PREMIUM PACKAGING - Durable plastic organizer with snap-lock compartments",
                        "LIFETIME WARRANTY - We stand behind our products with lifetime replacement",
                    ],
                    "description": "Professional grade 400PCS spring assortment kit with 24 different sizes.",
                },
                {
                    "asin": "B0COMP0004",
                    "title": "Small Compression Springs Assortment 150PCS 15 Sizes Mini Springs Kit Stainless Steel",
                    "brand": "SpringPro",
                    "price": 5.99,
                    "rating": 4.1,
                    "review_count": 89,
                    "bullet_points": [
                        "150PCS MINI SPRINGS - 15 different sizes of small compression springs",
                        "STAINLESS STEEL MATERIAL - Corrosion resistant for long-lasting performance",
                        "COMPACT KIT - Small and portable for on-the-go repairs",
                        "MULTI-PURPOSE - Electronics, watches, toys, and small device repair",
                        "EASY RETURNS - Hassle-free return within 30 days",
                    ],
                    "description": "Compact 150PCS mini compression springs kit for small device repairs.",
                },
                {
                    "asin": "B0COMP0005",
                    "title": "Heavy Duty Compression Spring Set 100PCS Large Springs Kit Carbon Steel Industrial Grade",
                    "brand": "HeavySpring",
                    "price": 15.99,
                    "rating": 4.4,
                    "review_count": 67,
                    "bullet_points": [
                        "100PCS HEAVY DUTY - Large compression springs for industrial applications",
                        "CARBON STEEL - High tensile strength for demanding environments",
                        "INDUSTRIAL GRADE - Meets industrial specifications and standards",
                        "LABELED SIZES - Each spring clearly marked for quick identification",
                        "BULK VALUE - Professional quantity at competitive pricing",
                    ],
                    "description": "Industrial grade 100PCS heavy duty compression springs set.",
                },
            ],
        }

        # 模糊匹配
        keyword_lower = keyword.lower()
        for key, listings in mock_db.items():
            if key in keyword_lower or keyword_lower in key:
                return listings

        # 默认返回弹簧数据
        return mock_db.get("compression spring", [])

"""
工厂产品目录 - 用于选品 Agent 匹配工厂生产能力
基于实际工厂产品线建模
"""
from typing import List, Dict

FACTORY_CATALOG = {
    "弹簧系列": {
        "id": "spring",
        "name_cn": "弹簧系列",
        "name_en": "Spring Series",
        "sub_categories": ["压簧", "拉簧", "扭簧", "门簧", "塔簧", "扁簧", "电池弹簧"],
        "materials": ["304不锈钢", "316不锈钢", "65Mn弹簧钢", "碳钢", "磷铜"],
        "spec_range": {
            "wire_diameter_mm": (0.3, 6.0),
            "length_mm": (5, 1000),
        },
        "moq": 100,
        "lead_time_days": 7,
        "can_customize": True,
        "unit_cost_range_rmb": (0.1, 3.0),
        "amazon_keywords": [
            "compression spring", "extension spring", "torsion spring",
            "trash can spring replacement", "door spring", "recliner spring",
            "sofa spring", "screen door spring", "gate spring",
            "spring assortment kit", "small spring set",
        ],
        "amazon_categories": [
            "Industrial & Scientific > Fasteners > Springs",
            "Tools & Home Improvement > Hardware > Springs",
        ],
    },
    "304螺栓": {
        "id": "bolt",
        "name_cn": "304螺栓",
        "name_en": "304 SS Bolts",
        "sub_categories": [
            "杯头内六角", "全牙外六角", "沉头内六角",
            "圆头内六角", "蝶形螺栓", "U型螺栓", "倒边内六角",
        ],
        "materials": ["304不锈钢", "316不锈钢", "12.9级合金钢"],
        "spec_range": {
            "diameter": "M3-M20",
            "length_mm": (5, 200),
        },
        "moq": 500,
        "lead_time_days": 10,
        "can_customize": True,
        "unit_cost_range_rmb": (0.05, 2.0),
        "amazon_keywords": [
            "stainless steel U bolt", "hex bolt kit", "socket cap screw",
            "U bolt marine", "boat trailer U bolt", "hex bolt assortment",
            "butterfly bolt", "wing bolt", "allen bolt",
        ],
        "amazon_categories": [
            "Industrial & Scientific > Fasteners > Bolts",
            "Automotive > Replacement Parts > Body & Trim > U-Bolts",
        ],
    },
    "吊具锁具": {
        "id": "rigging",
        "name_cn": "吊具锁具",
        "name_en": "Rigging & Hooks",
        "sub_categories": [
            "万向旋转环", "S型挂钩", "吊环螺钉",
            "万向旋转钩", "D型扣", "三角环",
        ],
        "materials": ["304不锈钢", "316不锈钢"],
        "spec_range": {
            "load_capacity_kg": (50, 2000),
        },
        "moq": 200,
        "lead_time_days": 7,
        "can_customize": True,
        "unit_cost_range_rmb": (0.5, 10.0),
        "amazon_keywords": [
            "S hook heavy duty", "swivel hook", "hammock hardware kit",
            "swing hook stainless", "D ring shackle", "eye bolt",
            "snap hook", "carabiner stainless",
        ],
        "amazon_categories": [
            "Tools & Home Improvement > Hardware > Hooks",
            "Patio, Lawn & Garden > Hammock Accessories",
        ],
    },
    "螺母垫圈": {
        "id": "nut_washer",
        "name_cn": "螺母垫圈",
        "name_en": "Nuts & Washers",
        "sub_categories": [
            "六角螺母", "防松螺母", "蝶形螺母", "法兰螺母",
            "盖形螺母", "弹垫圈", "平垫圈",
        ],
        "materials": ["304不锈钢"],
        "spec_range": {
            "diameter": "M3-M20",
        },
        "moq": 1000,
        "lead_time_days": 5,
        "can_customize": False,
        "unit_cost_range_rmb": (0.01, 0.5),
        "amazon_keywords": [
            "hex nut assortment", "lock nut kit", "washer assortment",
            "wing nut", "flange nut", "nylon lock nut set",
        ],
        "amazon_categories": [
            "Industrial & Scientific > Fasteners > Nuts",
            "Industrial & Scientific > Fasteners > Washers",
        ],
    },
    "挡圈卡簧": {
        "id": "retaining_ring",
        "name_cn": "挡圈卡簧",
        "name_en": "Retaining Rings",
        "sub_categories": ["轴用卡簧", "孔用卡簧", "E型卡簧"],
        "materials": ["65Mn", "304不锈钢"],
        "spec_range": {
            "inner_diameter_mm": (3, 80),
        },
        "moq": 500,
        "lead_time_days": 7,
        "can_customize": True,
        "unit_cost_range_rmb": (0.02, 0.3),
        "amazon_keywords": [
            "snap ring assortment", "retaining ring kit", "E-clip set",
            "circlip assortment", "internal retaining ring",
        ],
        "amazon_categories": [
            "Industrial & Scientific > Fasteners > Retaining Rings",
        ],
    },
    "销轴铆钉": {
        "id": "pin_rivet",
        "name_cn": "销轴铆钉",
        "name_en": "Pins & Rivets",
        "sub_categories": ["捷花轴", "抽芯铆钉", "圆钉", "子母钉"],
        "materials": ["304不锈钢", "铝合金"],
        "spec_range": {
            "diameter_mm": (2, 6),
        },
        "moq": 1000,
        "lead_time_days": 5,
        "can_customize": False,
        "unit_cost_range_rmb": (0.01, 0.2),
        "amazon_keywords": [
            "blind rivet assortment", "pop rivet kit", "clevis pin set",
            "rivet gun refill", "aluminum rivet",
        ],
        "amazon_categories": [
            "Industrial & Scientific > Fasteners > Rivets",
        ],
    },
}


def get_all_amazon_keywords() -> List[str]:
    """获取所有工厂产品对应的 Amazon 关键词"""
    keywords = []
    for cat in FACTORY_CATALOG.values():
        keywords.extend(cat["amazon_keywords"])
    return keywords


def match_product_to_factory(product_keywords: List[str]) -> List[dict]:
    """
    根据产品关键词匹配工厂生产能力
    返回匹配的工厂品类列表，按匹配度排序
    """
    matches = []
    product_keywords_lower = [k.lower() for k in product_keywords]

    for cat_id, cat_info in FACTORY_CATALOG.items():
        score = 0
        matched_keywords = []

        for factory_kw in cat_info["amazon_keywords"]:
            factory_kw_lower = factory_kw.lower()
            for prod_kw in product_keywords_lower:
                # 完全匹配
                if factory_kw_lower == prod_kw:
                    score += 10
                    matched_keywords.append(factory_kw)
                # 部分匹配
                elif factory_kw_lower in prod_kw or prod_kw in factory_kw_lower:
                    score += 5
                    matched_keywords.append(factory_kw)
                # 单词级匹配
                else:
                    factory_words = set(factory_kw_lower.split())
                    prod_words = set(prod_kw.split())
                    overlap = factory_words & prod_words
                    if len(overlap) >= 2:
                        score += 3
                        matched_keywords.append(factory_kw)

        if score > 0:
            matches.append({
                "category_id": cat_info["id"],
                "category_name": cat_id,
                "match_score": score,
                "matched_keywords": list(set(matched_keywords)),
                "can_customize": cat_info["can_customize"],
                "moq": cat_info["moq"],
                "lead_time_days": cat_info["lead_time_days"],
                "unit_cost_range_rmb": cat_info["unit_cost_range_rmb"],
            })

    matches.sort(key=lambda x: x["match_score"], reverse=True)
    return matches

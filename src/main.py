"""
跨境电商 AI Agent 系统 - 主入口

使用方式:
    python -m src.main demo              # 运行完整 Demo (全部7个Agent)
    python -m src.main scout             # 选品分析
    python -m src.main monitor           # 竞品监控
    python -m src.main report            # 生成日报
    python -m src.main trend             # 趋势分析
    python -m src.main fba              # FBA利润计算
    python -m src.main listing           # Listing优化
    python -m src.main service           # 智能客服
    python -m src.main ads              # 广告优化
    python -m src.main inventory         # 库存预测
    python -m src.main pricing           # 动态定价
"""
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agents.product_scout import ProductScoutAgent
from src.agents.market_insight import MarketInsightAgent
from src.agents.listing_optimizer import ListingOptimizerAgent
from src.agents.customer_service import CustomerServiceAgent
from src.agents.ad_optimizer import AdOptimizerAgent
from src.agents.inventory_forecast import InventoryForecastAgent
from src.agents.dynamic_pricing import DynamicPricingAgent
from src.tools.fba_calculator import quick_estimate_hardware, batch_price_sensitivity
from src.utils.database import init_database
from src.config.settings import REPORTS_DIR


def run_product_scout_demo():
    """演示选品 Agent"""
    print("=" * 70)
    print("  智能选品 Agent - Demo")
    print("=" * 70)

    agent = ProductScoutAgent()

    # 执行选品分析
    result = agent.run(
        task="分析五金弹簧替换件在 Amazon US 的市场机会",
        seed_keywords=[
            "trash can spring replacement",
            "compression spring kit",
            "stainless steel U bolts",
        ],
        mode="pipeline",
    )

    # 保存报告
    if result.get("report"):
        report_path = REPORTS_DIR / f"选品报告_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        report_path.write_text(result["report"], encoding="utf-8")
        print(f"\n报告已保存: {report_path}")

    # 打印 Top 5
    print("\n" + "=" * 70)
    print("  Top 5 候选产品")
    print("=" * 70)
    for i, candidate in enumerate(result.get("top_candidates", [])[:5], 1):
        print(f"\n  #{i} {candidate.get('title', 'N/A')[:50]}")
        print(f"      ASIN: {candidate.get('asin', 'N/A')}")
        print(f"      售价: ${candidate.get('price', 0):.2f}")
        print(f"      评分: {candidate.get('rating', 0)}")
        print(f"      综合得分: {candidate.get('total_score', 0)}")
        scores = candidate.get("scores", {})
        print(f"      [需求:{scores.get('demand',0)} 竞争:{scores.get('competition',0)} "
              f"利润:{scores.get('profit',0)} 改进:{scores.get('improvement',0)} "
              f"工厂:{scores.get('factory_match',0)}]")

    return result


def run_market_monitor_demo():
    """演示市场洞察 Agent"""
    print("\n" + "=" * 70)
    print("  市场洞察 Agent - 竞品监控 Demo")
    print("=" * 70)

    agent = MarketInsightAgent()

    # 设置初始快照（模拟"上次"的数据）
    agent._latest_snapshots = {
        "B0BVTDP29W": {
            "price": 6.99, "rating": 4.6, "review_count": 702,
            "bsr_rank": 1236, "in_stock": True,
        },
        "B0FG2DQYY7": {
            "price": 12.99, "rating": 4.6, "review_count": 564,
            "bsr_rank": 89, "in_stock": True,
        },
        "B0CF8LB4PF": {
            "price": 49.99, "rating": 4.7, "review_count": 540,
            "bsr_rank": 11320, "in_stock": True,
        },
    }

    # 执行监控周期
    result = agent.run(
        task="执行竞品监控",
        task_type="monitor",
        asins=["B0BVTDP29W", "B0FG2DQYY7", "B0CF8LB4PF"],
    )

    print(f"\n监控结果: {result['monitored_count']} 个产品, {len(result['alerts'])} 个告警")
    return result


def run_daily_report_demo():
    """演示日报生成"""
    print("\n" + "=" * 70)
    print("  市场洞察 Agent - 日报生成 Demo")
    print("=" * 70)

    agent = MarketInsightAgent()

    # 设置初始快照
    agent._latest_snapshots = {
        "B0BVTDP29W": {
            "price": 6.99, "rating": 4.6, "review_count": 702,
            "bsr_rank": 1236, "in_stock": True,
        },
    }

    result = agent.run(task="生成日报", task_type="daily_report")

    # 保存日报
    report_path = REPORTS_DIR / f"市场日报_{datetime.now().strftime('%Y%m%d')}.md"
    report_path.write_text(result["report"], encoding="utf-8")
    print(f"\n日报已保存: {report_path}")
    print(f"\n{result['report']}")

    return result


def run_trend_analysis_demo():
    """演示趋势分析"""
    print("\n" + "=" * 70)
    print("  市场洞察 Agent - 趋势分析 Demo")
    print("=" * 70)

    agent = MarketInsightAgent()

    categories = ["弹簧", "螺栓", "挂钩"]
    results = {}

    for cat in categories:
        result = agent.analyze_trend(cat)
        results[cat] = result
        print(f"  {cat}: {result['trend_direction']} "
              f"(置信度: {result['confidence_score']})")
        print(f"    → {result['assessment']}")

    return results


def run_fba_calculator_demo():
    """演示 FBA 利润计算"""
    print("\n" + "=" * 70)
    print("  FBA 利润计算器 Demo")
    print("=" * 70)

    # 弹簧替换件
    print("\n--- 垃圾桶弹簧替换件 (5件套) ---")
    result = quick_estimate_hardware(
        selling_price=8.99,
        product_cost_rmb=4.5,
        weight_grams=80,
    )
    print(result.summary())

    # U型螺栓
    print("\n--- 304不锈钢U型螺栓 (4件套) ---")
    result = quick_estimate_hardware(
        selling_price=14.99,
        product_cost_rmb=12.0,
        weight_grams=250,
    )
    print(result.summary())

    # 弹簧套装
    print("\n--- 弹簧套装 300PCS ---")
    result = quick_estimate_hardware(
        selling_price=8.99,
        product_cost_rmb=8.0,
        weight_grams=130,
    )
    print(result.summary())

    # 价格敏感性
    print("\n--- 弹簧替换件价格敏感性分析 ---")
    sensitivity = batch_price_sensitivity(
        product_cost_usd=0.63,
        shipping_cost_usd=0.35,
        weight_oz=2.8,
        price_range=(5.99, 14.99),
        step=1.0,
    )
    print(f"{'售价':>8} {'利润':>8} {'利润率':>8}")
    print("-" * 28)
    for row in sensitivity:
        print(f"${row['price']:>6.2f} ${row['profit']:>6.2f} {row['margin']:>7.1%}")


def run_listing_optimizer_demo():
    """演示 Listing 优化 Agent"""
    print("\n" + "=" * 70)
    print("  Listing 优化 Agent - Demo")
    print("=" * 70)

    agent = ListingOptimizerAgent()

    result = agent.run(
        task="为弹簧套装产品生成高转化 Amazon Listing",
        product_info={
            "name": "Compression Spring Assortment Kit",
            "brand": "SpringMaster",
            "material": "304 Stainless Steel",
            "specifications": "20 different sizes, 0.3mm-1.2mm wire diameter",
            "quantity": "200PCS",
            "use_case": "home repair, automotive, electronics, industrial",
        },
        keyword="compression spring kit",
        pain_points=[
            "sizes don't match description",
            "springs rust after short use",
            "missing pieces in the kit",
        ],
        localize_to=["de", "ja"],
        mode="pipeline",
    )

    # 保存报告
    if result.get("report"):
        report_path = REPORTS_DIR / f"Listing优化报告_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        report_path.write_text(result["report"], encoding="utf-8")
        print(f"\n报告已保存: {report_path}")

    # 打印标题
    listing = result.get("listing", {})
    print("\n--- 候选标题 ---")
    for i, title in enumerate(listing.get("titles", []), 1):
        print(f"  {i}. {title}")

    return result


def run_customer_service_demo():
    """演示智能客服 Agent"""
    print("\n" + "=" * 70)
    print("  智能客服 Agent - Demo")
    print("=" * 70)

    agent = CustomerServiceAgent()

    # 处理买家消息
    print("\n--- 处理买家消息 ---")
    msg_result = agent.run(task="处理买家消息", task_type="process_messages")

    # 处理差评
    print("\n--- 处理差评回复 ---")
    review_result = agent.run(task="处理差评", task_type="handle_reviews")

    # 统计
    stats = agent.run(task="统计", task_type="stats")
    print(f"\n--- 客服统计 ---")
    print(f"  总工单: {stats.get('total_tickets', 0)}")
    print(f"  已升级: {stats.get('escalated_count', 0)}")

    return {"messages": msg_result, "reviews": review_result, "stats": stats}


def run_ad_optimizer_demo():
    """演示广告优化 Agent"""
    print("\n" + "=" * 70)
    print("  广告投放 Agent - Demo")
    print("=" * 70)

    agent = AdOptimizerAgent()

    result = agent.run(
        task="优化弹簧套装广告投放",
        task_type="full_optimization",
        asin="B0COMPSP02",
        product_name="200PCS Spring Assortment Kit",
        selling_price=8.99,
    )

    # 打印报告
    report = result.get("report", {})
    metrics = report.get("metrics", {})
    print(f"\n--- 广告表现 ---")
    print(f"  花费: ${metrics.get('total_spend', 0):.2f}")
    print(f"  销售: ${metrics.get('total_sales', 0):.2f}")
    print(f"  ACOS: {metrics.get('acos', 0):.1f}%")
    print(f"  ROAS: {metrics.get('roas', 0):.2f}")

    return result


def run_inventory_forecast_demo():
    """演示库存预测 Agent"""
    print("\n" + "=" * 70)
    print("  库存预测 Agent - Demo")
    print("=" * 70)

    agent = InventoryForecastAgent()

    result = agent.run(task="库存分析与补货建议", task_type="full_analysis")

    # 打印汇总
    print(f"\n--- 库存概况 ---")
    for sku in result.get("sku_details", []):
        emoji = {"red": "!!!", "yellow": "! ", "green": "OK"}
        print(f"  [{emoji.get(sku['urgency'], '??')}] {sku['asin']}: "
              f"库存{sku['current_stock']} | 日销{sku['forecast_daily']} | "
              f"可售{sku['days_of_stock']}天 | 补{sku['order_quantity']}件")

    return result


def run_dynamic_pricing_demo():
    """演示动态定价 Agent"""
    print("\n" + "=" * 70)
    print("  动态定价 Agent - Demo")
    print("=" * 70)

    agent = DynamicPricingAgent()

    result = agent.run(task="产品定价优化", task_type="full_analysis")

    # 打印汇总
    print(f"\n--- 定价建议 ---")
    for analysis in result.get("analyses", []):
        optimal = analysis.get("optimal_pricing", {})
        print(f"  {analysis['product_name']}:")
        print(f"    当前价: ${analysis['current_price']:.2f} → "
              f"建议价: ${optimal.get('optimal_price', 0):.2f} "
              f"({optimal.get('strategy', '')}, "
              f"利润率{optimal.get('expected_margin', 0):.1f}%)")

    return result


def run_full_demo():
    """运行完整 Demo（全部 7 个 Agent）"""
    print("\n" + "=" * 70)
    print("  跨境电商 AI Agent 系统 - 完整 Demo (7 Agents)")
    print("  " + "=" * 50)
    print(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 初始化数据库
    init_database()

    start = time.time()
    results = {}

    # 1. FBA 利润计算
    run_fba_calculator_demo()

    # 2. 选品分析
    results["scout"] = run_product_scout_demo()

    # 3. 竞品监控
    results["monitor"] = run_market_monitor_demo()

    # 4. 趋势分析
    results["trend"] = run_trend_analysis_demo()

    # 5. 日报生成
    results["report"] = run_daily_report_demo()

    # 6. Listing 优化
    results["listing"] = run_listing_optimizer_demo()

    # 7. 智能客服
    results["service"] = run_customer_service_demo()

    # 8. 广告优化
    results["ads"] = run_ad_optimizer_demo()

    # 9. 库存预测
    results["inventory"] = run_inventory_forecast_demo()

    # 10. 动态定价
    results["pricing"] = run_dynamic_pricing_demo()

    elapsed = time.time() - start

    print("\n" + "=" * 70)
    print("  Complete Demo Done!")
    print("=" * 70)
    print(f"  Total time: {elapsed:.1f}s")
    print(f"  Agents run: 7 (ProductScout, MarketInsight, ListingOptimizer,")
    print(f"               CustomerService, AdOptimizer, InventoryForecast,")
    print(f"               DynamicPricing)")
    print(f"  Selection candidates: {len(results['scout'].get('top_candidates', []))}")
    print(f"  Monitor alerts: {len(results['monitor'].get('alerts', []))}")
    print(f"  Reports saved to: {REPORTS_DIR}")
    print("=" * 70)


def main():
    """CLI 入口"""
    if len(sys.argv) < 2:
        print("Cross-Border E-commerce AI Agent System")
        print("=" * 50)
        print("\nUsage:")
        print("  python -m src.main demo         # Full demo (all 7 agents)")
        print("  python -m src.main scout        # Product selection")
        print("  python -m src.main monitor      # Competitor monitoring")
        print("  python -m src.main report       # Daily report")
        print("  python -m src.main trend        # Trend analysis")
        print("  python -m src.main fba          # FBA profit calculator")
        print("  python -m src.main listing      # Listing optimization")
        print("  python -m src.main service      # Customer service")
        print("  python -m src.main ads          # Ad optimization")
        print("  python -m src.main inventory    # Inventory forecast")
        print("  python -m src.main pricing      # Dynamic pricing")
        sys.exit(0)

    command = sys.argv[1]
    init_database()

    commands = {
        "demo": run_full_demo,
        "scout": run_product_scout_demo,
        "monitor": run_market_monitor_demo,
        "report": run_daily_report_demo,
        "trend": run_trend_analysis_demo,
        "fba": run_fba_calculator_demo,
        "listing": run_listing_optimizer_demo,
        "service": run_customer_service_demo,
        "ads": run_ad_optimizer_demo,
        "inventory": run_inventory_forecast_demo,
        "pricing": run_dynamic_pricing_demo,
    }

    handler = commands.get(command)
    if handler:
        handler()
    else:
        print(f"Unknown command: {command}")
        print(f"Available: {', '.join(commands.keys())}")
        sys.exit(1)


if __name__ == "__main__":
    main()

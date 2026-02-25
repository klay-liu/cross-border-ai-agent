"""
跨境电商 AI Agent 系统 - 主入口

使用方式:
    # 运行选品分析
    python -m src.main scout --keywords "弹簧"

    # 运行竞品监控
    python -m src.main monitor

    # 生成市场日报
    python -m src.main report --type daily

    # 分析品类趋势
    python -m src.main trend --category "弹簧"

    # 运行完整 Demo
    python -m src.main demo
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


def run_full_demo():
    """运行完整 Demo"""
    print("\n" + "=" * 70)
    print("  跨境电商 AI Agent 系统 - 完整 Demo")
    print("  " + "=" * 50)
    print(f"  运行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    # 初始化数据库
    init_database()

    start = time.time()

    # 1. FBA 利润计算
    run_fba_calculator_demo()

    # 2. 选品分析
    scout_result = run_product_scout_demo()

    # 3. 竞品监控
    monitor_result = run_market_monitor_demo()

    # 4. 趋势分析
    trend_result = run_trend_analysis_demo()

    # 5. 日报生成
    report_result = run_daily_report_demo()

    elapsed = time.time() - start

    print("\n" + "=" * 70)
    print("  Demo 完成！")
    print(f"  总耗时: {elapsed:.1f} 秒")
    print(f"  选品候选: {len(scout_result.get('top_candidates', []))} 个")
    print(f"  监控告警: {len(monitor_result.get('alerts', []))} 个")
    print(f"  报告已保存到: {REPORTS_DIR}")
    print("=" * 70)


def main():
    """CLI 入口"""
    if len(sys.argv) < 2:
        print("用法:")
        print("  python -m src.main demo           # 运行完整 Demo")
        print("  python -m src.main scout           # 选品分析")
        print("  python -m src.main monitor          # 竞品监控")
        print("  python -m src.main report           # 生成日报")
        print("  python -m src.main trend            # 趋势分析")
        print("  python -m src.main fba              # FBA利润计算")
        sys.exit(0)

    command = sys.argv[1]
    init_database()

    if command == "demo":
        run_full_demo()
    elif command == "scout":
        run_product_scout_demo()
    elif command == "monitor":
        run_market_monitor_demo()
    elif command == "report":
        run_daily_report_demo()
    elif command == "trend":
        run_trend_analysis_demo()
    elif command == "fba":
        run_fba_calculator_demo()
    else:
        print(f"未知命令: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
FBA 费用计算器 - 基于 Amazon FBA 2025-2026 费用标准
"""
from dataclasses import dataclass
from typing import List, Tuple
from src.config.settings import FBA_FEES_US, AMAZON_MARKETPLACE


@dataclass
class FBAEstimate:
    """FBA 费用估算结果"""
    selling_price: float
    referral_fee: float
    fba_fulfillment_fee: float
    monthly_storage_fee: float
    total_amazon_fees: float
    product_cost: float
    shipping_cost: float
    total_cost: float
    net_profit: float
    profit_margin: float
    size_tier: str

    def to_dict(self) -> dict:
        return {
            "selling_price": round(self.selling_price, 2),
            "referral_fee": round(self.referral_fee, 2),
            "fba_fulfillment_fee": round(self.fba_fulfillment_fee, 2),
            "monthly_storage_fee": round(self.monthly_storage_fee, 4),
            "total_amazon_fees": round(self.total_amazon_fees, 2),
            "product_cost": round(self.product_cost, 2),
            "shipping_cost": round(self.shipping_cost, 2),
            "total_cost": round(self.total_cost, 2),
            "net_profit": round(self.net_profit, 2),
            "profit_margin": round(self.profit_margin, 4),
            "size_tier": self.size_tier,
        }

    def summary(self) -> str:
        return (
            f"售价: ${self.selling_price:.2f}\n"
            f"├── Amazon佣金(15%): ${self.referral_fee:.2f}\n"
            f"├── FBA配送费: ${self.fba_fulfillment_fee:.2f}\n"
            f"├── 月仓储费: ${self.monthly_storage_fee:.4f}\n"
            f"├── 产品成本: ${self.product_cost:.2f}\n"
            f"├── 头程物流: ${self.shipping_cost:.2f}\n"
            f"└── 净利润: ${self.net_profit:.2f} ({self.profit_margin:.1%})\n"
            f"尺寸类型: {self.size_tier}"
        )


def determine_size_tier(length_in: float, width_in: float,
                         height_in: float, weight_oz: float) -> str:
    """
    判断 FBA 尺寸层级
    Small Standard: 最长边≤15", 次长边≤12", 最短边≤0.75", 重量≤16oz
    Large Standard: 最长边≤18", 次长边≤14", 最短边≤8", 重量≤20lb
    """
    dims = sorted([length_in, width_in, height_in], reverse=True)
    longest, median, shortest = dims

    if (longest <= 15 and median <= 12 and shortest <= 0.75
            and weight_oz <= 16):
        return "small_standard"
    elif (longest <= 18 and median <= 14 and shortest <= 8
          and weight_oz <= 320):  # 20lb = 320oz
        return "large_standard"
    else:
        return "oversize"


def get_fba_fulfillment_fee(size_tier: str, weight_oz: float) -> float:
    """根据尺寸层级和重量获取 FBA 配送费"""
    if size_tier == "small_standard":
        fees = FBA_FEES_US["small_standard"]
        if weight_oz <= 2:
            return fees["2oz_or_less"]
        elif weight_oz <= 4:
            return fees["2_to_4oz"]
        elif weight_oz <= 6:
            return fees["4_to_6oz"]
        elif weight_oz <= 8:
            return fees["6_to_8oz"]
        elif weight_oz <= 10:
            return fees["8_to_10oz"]
        elif weight_oz <= 12:
            return fees["10_to_12oz"]
        elif weight_oz <= 14:
            return fees["12_to_14oz"]
        else:
            return fees["14_to_16oz"]
    elif size_tier == "large_standard":
        fees = FBA_FEES_US["large_standard"]
        if weight_oz <= 4:
            return fees["4oz_or_less"]
        elif weight_oz <= 8:
            return fees["4_to_8oz"]
        elif weight_oz <= 12:
            return fees["8_to_12oz"]
        elif weight_oz <= 16:
            return fees["12_to_16oz"]
        elif weight_oz <= 24:
            return fees["1_to_1.5lb"]
        elif weight_oz <= 32:
            return fees["1.5_to_2lb"]
        elif weight_oz <= 40:
            return fees["2_to_2.5lb"]
        else:
            return fees["2.5_to_3lb"]
    else:
        return 10.0  # oversize 的简化处理


def calculate_monthly_storage(length_in: float, width_in: float,
                               height_in: float, month: int = 6) -> float:
    """计算月度仓储费"""
    volume_cuft = (length_in * width_in * height_in) / 1728  # 转为立方英尺
    if month >= 10:  # Q4 旺季费率
        rate = FBA_FEES_US["monthly_storage_per_cuft"]["oct_dec"]
    else:
        rate = FBA_FEES_US["monthly_storage_per_cuft"]["jan_sep"]
    return volume_cuft * rate


def calculate_fba_profit(
    selling_price: float,
    product_cost_usd: float,
    shipping_cost_usd: float = 0.40,
    weight_oz: float = 4.0,
    length_in: float = 7.0,
    width_in: float = 5.0,
    height_in: float = 1.0,
    referral_fee_pct: float = 0.15,
    marketplace: str = "US",
) -> FBAEstimate:
    """
    计算 FBA 利润

    Args:
        selling_price: 售价 (USD)
        product_cost_usd: 产品成本 (USD)
        shipping_cost_usd: 头程物流均摊成本 (USD)
        weight_oz: 包装后重量 (盎司)
        length_in: 包装后长度 (英寸)
        width_in: 包装后宽度 (英寸)
        height_in: 包装后高度 (英寸)
        referral_fee_pct: 佣金比例 (默认 15%)
        marketplace: 站点

    Returns:
        FBAEstimate 对象
    """
    # 1. 销售佣金
    referral_fee = selling_price * referral_fee_pct

    # 2. FBA 配送费
    size_tier = determine_size_tier(length_in, width_in, height_in, weight_oz)
    fba_fee = get_fba_fulfillment_fee(size_tier, weight_oz)

    # 3. 月度仓储费（均摊到单件）
    storage_fee = calculate_monthly_storage(length_in, width_in, height_in)

    # 4. 汇总
    total_amazon_fees = referral_fee + fba_fee + storage_fee
    total_cost = total_amazon_fees + product_cost_usd + shipping_cost_usd
    net_profit = selling_price - total_cost
    profit_margin = net_profit / selling_price if selling_price > 0 else 0

    return FBAEstimate(
        selling_price=selling_price,
        referral_fee=referral_fee,
        fba_fulfillment_fee=fba_fee,
        monthly_storage_fee=storage_fee,
        total_amazon_fees=total_amazon_fees,
        product_cost=product_cost_usd,
        shipping_cost=shipping_cost_usd,
        total_cost=total_cost,
        net_profit=net_profit,
        profit_margin=profit_margin,
        size_tier=size_tier,
    )


def batch_price_sensitivity(
    product_cost_usd: float,
    shipping_cost_usd: float,
    weight_oz: float,
    price_range: Tuple[float, float] = (5.99, 19.99),
    step: float = 1.0,
    **kwargs,
) -> List[dict]:
    """
    批量计算不同售价下的利润率，用于定价决策

    Returns:
        [{price, profit, margin, fba_fee}, ...]
    """
    results = []
    price = price_range[0]
    while price <= price_range[1]:
        est = calculate_fba_profit(
            selling_price=price,
            product_cost_usd=product_cost_usd,
            shipping_cost_usd=shipping_cost_usd,
            weight_oz=weight_oz,
            **kwargs,
        )
        results.append({
            "price": round(price, 2),
            "profit": round(est.net_profit, 2),
            "margin": round(est.profit_margin, 4),
            "fba_fee": round(est.fba_fulfillment_fee, 2),
        })
        price += step
    return results


# ============================================================
# 快捷函数
# ============================================================

def quick_estimate_hardware(selling_price: float, product_cost_rmb: float,
                             weight_grams: float = 100) -> FBAEstimate:
    """
    五金产品快速估算（简化参数）

    Args:
        selling_price: 售价 USD
        product_cost_rmb: 产品成本 RMB
        weight_grams: 重量 克
    """
    product_cost_usd = product_cost_rmb / 7.2  # 汇率
    weight_oz = weight_grams / 28.35
    shipping_cost_usd = weight_grams * 0.06 / 7.2  # 约60元/kg头程

    return calculate_fba_profit(
        selling_price=selling_price,
        product_cost_usd=product_cost_usd,
        shipping_cost_usd=shipping_cost_usd,
        weight_oz=weight_oz,
    )


if __name__ == "__main__":
    # 示例：垃圾桶弹簧替换件 (5件套)
    print("=" * 60)
    print("垃圾桶弹簧替换件 (5件套) 利润计算")
    print("=" * 60)
    result = quick_estimate_hardware(
        selling_price=8.99,
        product_cost_rmb=4.5,
        weight_grams=80,
    )
    print(result.summary())

    print("\n" + "=" * 60)
    print("价格敏感性分析")
    print("=" * 60)
    sensitivity = batch_price_sensitivity(
        product_cost_usd=0.63,
        shipping_cost_usd=0.35,
        weight_oz=2.8,
        price_range=(5.99, 14.99),
        step=1.0,
    )
    print(f"{'售价':>8} {'利润':>8} {'利润率':>8} {'FBA费':>8}")
    print("-" * 36)
    for row in sensitivity:
        print(f"${row['price']:>6.2f} ${row['profit']:>6.2f} "
              f"{row['margin']:>7.1%} ${row['fba_fee']:>6.2f}")

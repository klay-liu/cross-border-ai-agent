"""
全局配置 - 跨境电商 AI Agent 系统
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 路径配置
# ============================================================
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_DIR = DATA_DIR / "db"
REPORTS_DIR = DATA_DIR / "reports"
CACHE_DIR = DATA_DIR / "cache"

# 自动创建目录
for d in [DATA_DIR, DB_DIR, REPORTS_DIR, CACHE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ============================================================
# API 密钥
# ============================================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
KEEPA_API_KEY = os.getenv("KEEPA_API_KEY", "")
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "")

# ============================================================
# LLM 配置
# ============================================================
LLM_CONFIG = {
    "default_model": "claude-sonnet-4-20250514",
    "fast_model": "claude-haiku-4-20250414",
    "max_tokens": 4096,
    "temperature": 0.3,  # 分析任务用低温度，保证一致性
}

# ============================================================
# 数据库配置
# ============================================================
DATABASE_URL = f"sqlite:///{DB_DIR / 'agent.db'}"

# ============================================================
# Amazon 市场配置
# ============================================================
AMAZON_MARKETPLACE = {
    "US": {
        "domain": "amazon.com",
        "currency": "USD",
        "referral_fee_pct": 0.15,  # 大部分品类 15%
    },
    "DE": {
        "domain": "amazon.de",
        "currency": "EUR",
        "referral_fee_pct": 0.15,
    },
}

DEFAULT_MARKETPLACE = "US"

# ============================================================
# FBA 费用表 (2025-2026, US, Small Standard)
# ============================================================
FBA_FEES_US = {
    "small_standard": {
        "2oz_or_less": 3.06,
        "2_to_4oz": 3.15,
        "4_to_6oz": 3.24,
        "6_to_8oz": 3.32,
        "8_to_10oz": 3.43,
        "10_to_12oz": 3.53,
        "12_to_14oz": 3.60,
        "14_to_16oz": 3.65,
    },
    "large_standard": {
        "4oz_or_less": 3.68,
        "4_to_8oz": 3.98,
        "8_to_12oz": 4.28,
        "12_to_16oz": 4.78,
        "1_to_1.5lb": 5.19,
        "1.5_to_2lb": 5.44,
        "2_to_2.5lb": 5.77,
        "2.5_to_3lb": 6.15,
    },
    "monthly_storage_per_cuft": {
        "jan_sep": 0.87,
        "oct_dec": 2.40,
    },
}

# ============================================================
# 选品过滤规则
# ============================================================
PRODUCT_FILTER_RULES = {
    "min_monthly_sales": 100,
    "min_search_results": 200,
    "max_search_results": 50000,
    "max_top1_review_count": 2000,
    "max_avg_rating": 4.5,
    "min_price": 6.0,
    "max_price": 50.0,
    "min_estimated_margin": 0.15,
    "exclude_categories": ["Electronics", "Toys & Games", "Grocery"],
}

# ============================================================
# 竞品监控告警阈值
# ============================================================
ALERT_THRESHOLDS = {
    "price_change_pct": 10,       # 价格变动 >10%
    "bsr_surge_pct": 30,          # BSR 大幅变动
    "review_surge_count": 10,     # 单周新增评论
    "rating_drop": 0.2,           # 评分下降
    "new_competitor_bsr": 10000,  # 新竞品 BSR 阈值
}

# ============================================================
# 选品评分权重
# ============================================================
SCORING_WEIGHTS = {
    "demand_score": 0.20,
    "competition_score": 0.25,
    "profit_score": 0.20,
    "improvement_score": 0.15,
    "factory_match_score": 0.10,
    "trend_score": 0.10,
}

# ============================================================
# 调度配置
# ============================================================
SCHEDULE_CONFIG = {
    "price_monitor": {"interval_hours": 6},
    "review_monitor": {"interval_hours": 24},
    "trend_scan": {"interval_days": 7},
    "weekly_report": {"day_of_week": "mon", "hour": 9},
}

"""
数据库管理 - SQLite 存储层
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from src.config.settings import DB_DIR


DB_PATH = DB_DIR / "agent.db"


def get_connection() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_database():
    """初始化数据库表结构"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.executescript("""
    -- 产品表
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asin TEXT UNIQUE NOT NULL,
        title TEXT,
        brand TEXT,
        category TEXT,
        price REAL,
        rating REAL,
        review_count INTEGER,
        bsr_rank INTEGER,
        monthly_sales_est INTEGER,
        monthly_revenue_est REAL,
        fba_fee REAL,
        referral_fee_pct REAL,
        image_url TEXT,
        first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- 价格历史表
    CREATE TABLE IF NOT EXISTS price_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asin TEXT NOT NULL,
        price REAL,
        bsr_rank INTEGER,
        review_count INTEGER,
        rating REAL,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (asin) REFERENCES products(asin)
    );

    -- 评论分析表
    CREATE TABLE IF NOT EXISTS review_analysis (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asin TEXT NOT NULL,
        review_id TEXT,
        rating INTEGER,
        review_text TEXT,
        pain_point TEXT,
        pain_category TEXT,
        improvement_suggestion TEXT,
        analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (asin) REFERENCES products(asin)
    );

    -- 选品候选表
    CREATE TABLE IF NOT EXISTS product_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT NOT NULL,
        asin TEXT,
        opportunity_score REAL,
        competition_score REAL,
        demand_score REAL,
        profit_potential REAL,
        factory_match_score REAL,
        recommendation TEXT,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- 竞品事件表
    CREATE TABLE IF NOT EXISTS competitor_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asin TEXT NOT NULL,
        event_type TEXT,
        old_value TEXT,
        new_value TEXT,
        severity TEXT,
        notified INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (asin) REFERENCES products(asin)
    );

    -- 市场趋势表
    CREATE TABLE IF NOT EXISTS market_trends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT,
        keyword TEXT,
        trend_direction TEXT,
        search_volume_est INTEGER,
        growth_rate REAL,
        insight TEXT,
        data_source TEXT,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Agent 执行日志
    CREATE TABLE IF NOT EXISTS agent_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_name TEXT NOT NULL,
        task_type TEXT,
        input_params TEXT,
        output_summary TEXT,
        tokens_used INTEGER DEFAULT 0,
        cost_usd REAL DEFAULT 0,
        duration_seconds REAL,
        status TEXT DEFAULT 'running',
        started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    );

    -- 索引
    CREATE INDEX IF NOT EXISTS idx_products_asin ON products(asin);
    CREATE INDEX IF NOT EXISTS idx_price_history_asin ON price_history(asin);
    CREATE INDEX IF NOT EXISTS idx_price_history_date ON price_history(recorded_at);
    CREATE INDEX IF NOT EXISTS idx_competitor_events_asin ON competitor_events(asin);
    CREATE INDEX IF NOT EXISTS idx_competitor_events_date ON competitor_events(created_at);
    CREATE INDEX IF NOT EXISTS idx_agent_runs_name ON agent_runs(agent_name);
    """)

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")


def upsert_product(product_data: dict):
    """插入或更新产品数据"""
    conn = get_connection()
    conn.execute("""
        INSERT INTO products (asin, title, brand, category, price, rating,
                            review_count, bsr_rank, monthly_sales_est,
                            monthly_revenue_est, image_url, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(asin) DO UPDATE SET
            title=excluded.title, brand=excluded.brand,
            price=excluded.price, rating=excluded.rating,
            review_count=excluded.review_count, bsr_rank=excluded.bsr_rank,
            monthly_sales_est=excluded.monthly_sales_est,
            monthly_revenue_est=excluded.monthly_revenue_est,
            updated_at=excluded.updated_at
    """, (
        product_data["asin"], product_data.get("title"),
        product_data.get("brand"), product_data.get("category"),
        product_data.get("price"), product_data.get("rating"),
        product_data.get("review_count"), product_data.get("bsr_rank"),
        product_data.get("monthly_sales_est"),
        product_data.get("monthly_revenue_est"),
        product_data.get("image_url"),
        datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()


def record_price_snapshot(asin: str, price: float, bsr_rank: int = None,
                          review_count: int = None, rating: float = None):
    """记录价格快照"""
    conn = get_connection()
    conn.execute("""
        INSERT INTO price_history (asin, price, bsr_rank, review_count, rating)
        VALUES (?, ?, ?, ?, ?)
    """, (asin, price, bsr_rank, review_count, rating))
    conn.commit()
    conn.close()


def get_price_history(asin: str, days: int = 30) -> list:
    """获取价格历史"""
    conn = get_connection()
    rows = conn.execute("""
        SELECT price, bsr_rank, review_count, rating, recorded_at
        FROM price_history
        WHERE asin = ?
        AND recorded_at >= datetime('now', ?)
        ORDER BY recorded_at ASC
    """, (asin, f"-{days} days")).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def save_candidate(candidate: dict):
    """保存选品候选"""
    conn = get_connection()
    conn.execute("""
        INSERT INTO product_candidates
        (keyword, asin, opportunity_score, competition_score,
         demand_score, profit_potential, factory_match_score, recommendation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        candidate["keyword"], candidate.get("asin"),
        candidate.get("opportunity_score"), candidate.get("competition_score"),
        candidate.get("demand_score"), candidate.get("profit_potential"),
        candidate.get("factory_match_score"), candidate.get("recommendation"),
    ))
    conn.commit()
    conn.close()


def log_agent_run(agent_name: str, task_type: str, input_params: dict) -> int:
    """记录 Agent 运行开始"""
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO agent_runs (agent_name, task_type, input_params, status)
        VALUES (?, ?, ?, 'running')
    """, (agent_name, task_type, json.dumps(input_params, ensure_ascii=False)))
    run_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return run_id


def complete_agent_run(run_id: int, output_summary: str,
                       tokens_used: int = 0, cost_usd: float = 0,
                       duration_seconds: float = 0, status: str = "completed"):
    """记录 Agent 运行完成"""
    conn = get_connection()
    conn.execute("""
        UPDATE agent_runs
        SET output_summary=?, tokens_used=?, cost_usd=?,
            duration_seconds=?, status=?, completed_at=?
        WHERE id=?
    """, (output_summary, tokens_used, cost_usd,
          duration_seconds, status, datetime.now().isoformat(), run_id))
    conn.commit()
    conn.close()


def save_competitor_event(asin: str, event_type: str,
                          old_value: str, new_value: str, severity: str):
    """保存竞品事件"""
    conn = get_connection()
    conn.execute("""
        INSERT INTO competitor_events (asin, event_type, old_value, new_value, severity)
        VALUES (?, ?, ?, ?, ?)
    """, (asin, event_type, old_value, new_value, severity))
    conn.commit()
    conn.close()


# 初始化
if not DB_PATH.exists():
    init_database()

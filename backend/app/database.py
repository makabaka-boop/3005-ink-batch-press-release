import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
URL = os.getenv("DATABASE_URL", "sqlite:///./ink.db")
engine = create_engine(URL, connect_args={"check_same_thread": False} if URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False)
class Base(DeclarativeBase): pass
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
def default_received_weight() -> float:
    """历史批次回填用的默认入库重量（kg），可用环境变量 DEFAULT_RECEIVED_WEIGHT 配置。"""
    return float(os.getenv("DEFAULT_RECEIVED_WEIGHT", "100"))
def migrate(eng=engine, default_weight: float | None = None):
    """为既有 SQLite 数据库补齐预占流程所需字段。

    历史批次按可配置默认入库重量回填（可用重量同步置满，历史工单不反向扣减）；
    历史工单计划用量记 0、状态记 planned，保持原展示口径。
    """
    if eng.url.get_backend_name() != "sqlite": return
    w = default_weight if default_weight is not None else default_received_weight()
    with eng.begin() as conn:
        tables = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}
        def cols(table): return {r[1] for r in conn.execute(text(f"PRAGMA table_info({table})"))}
        if "ink_batches" in tables:
            c = cols("ink_batches")
            if "received_weight" not in c: conn.execute(text("ALTER TABLE ink_batches ADD COLUMN received_weight FLOAT"))
            if "available_weight" not in c: conn.execute(text("ALTER TABLE ink_batches ADD COLUMN available_weight FLOAT"))
            conn.execute(text("UPDATE ink_batches SET received_weight=:w WHERE received_weight IS NULL"), {"w": w})
            conn.execute(text("UPDATE ink_batches SET available_weight=:w WHERE available_weight IS NULL"), {"w": w})
        if "press_jobs" in tables:
            c = cols("press_jobs")
            if "planned_usage" not in c: conn.execute(text("ALTER TABLE press_jobs ADD COLUMN planned_usage FLOAT"))
            if "status" not in c: conn.execute(text("ALTER TABLE press_jobs ADD COLUMN status VARCHAR(20)"))
            if "cancelled_at" not in c: conn.execute(text("ALTER TABLE press_jobs ADD COLUMN cancelled_at DATETIME"))
            conn.execute(text("UPDATE press_jobs SET planned_usage=0 WHERE planned_usage IS NULL"))
            conn.execute(text("UPDATE press_jobs SET status='planned' WHERE status IS NULL"))

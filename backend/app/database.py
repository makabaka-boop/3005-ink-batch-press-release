import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
URL = os.getenv("DATABASE_URL", "sqlite:///./ink.db")
engine = create_engine(URL, connect_args={"check_same_thread": False, "timeout": 15} if URL.startswith("sqlite") else {})
if URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_autocommit(dbapi_conn, _):
        dbapi_conn.isolation_level = None  # 关闭 pysqlite 隐式 BEGIN，交由 begin 事件统一控制
    @event.listens_for(engine, "begin")
    def _sqlite_begin_immediate(conn):
        conn.exec_driver_sql("BEGIN IMMEDIATE")  # 事务开始即取写锁，并发写事务串行化，避免先读后写导致的锁升级死锁
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
            if "actual_usage" not in c: conn.execute(text("ALTER TABLE press_jobs ADD COLUMN actual_usage FLOAT"))
            if "completed_at" not in c: conn.execute(text("ALTER TABLE press_jobs ADD COLUMN completed_at DATETIME"))
            if "previous_batch_id" not in c: conn.execute(text("ALTER TABLE press_jobs ADD COLUMN previous_batch_id INTEGER"))
            if "previous_batch_code" not in c: conn.execute(text("ALTER TABLE press_jobs ADD COLUMN previous_batch_code VARCHAR(64)"))
            if "switched_at" not in c: conn.execute(text("ALTER TABLE press_jobs ADD COLUMN switched_at DATETIME"))
            # 既有换料记录按当前编号尽力回填快照；新换料在换料时写入快照，之后批次改编号不影响历史记录
            if "ink_batches" in tables: conn.execute(text("UPDATE press_jobs SET previous_batch_code=(SELECT code FROM ink_batches WHERE ink_batches.id=press_jobs.previous_batch_id) WHERE previous_batch_id IS NOT NULL AND previous_batch_code IS NULL"))
            conn.execute(text("UPDATE press_jobs SET planned_usage=0 WHERE planned_usage IS NULL"))
            conn.execute(text("UPDATE press_jobs SET status='planned' WHERE status IS NULL"))
            # 历史工单实际用量与完成时间保持 NULL，继续呈现「计划中」的未完成语义，可再次登记完成
        if "issues" in tables:
            # 巡检问题不关联工单：旧库 issues.job_id 为 NOT NULL，重建表放宽为可空，既有问题数据原样保留
            info = conn.execute(text("PRAGMA table_info(issues)")).all()
            if any(r[1] == "job_id" and r[3] for r in info):
                conn.execute(text("CREATE TABLE issues_nullable_job(id INTEGER PRIMARY KEY, job_id INTEGER REFERENCES press_jobs(id), batch_id INTEGER, issue_type VARCHAR(40), created_at DATETIME, reason TEXT, status VARCHAR(20), resolution_note TEXT)"))
                conn.execute(text("INSERT INTO issues_nullable_job SELECT id, job_id, batch_id, issue_type, created_at, reason, status, resolution_note FROM issues"))
                conn.execute(text("DROP TABLE issues"))
                conn.execute(text("ALTER TABLE issues_nullable_job RENAME TO issues"))

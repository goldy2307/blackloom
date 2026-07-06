"""
Production API layer.

Adds on top of the base dashboard API:
  - API key auth on write/trigger endpoints (POST /api/run-pipeline)
  - Rate limiting (slowapi) — protects against abuse/accidental hammering
  - Prometheus /metrics endpoint — real production monitoring, scrapeable by Grafana
  - /api/analytics and /api/quality — expose the data-science layer
  - Structured error responses

Run: uvicorn app:app --port 8000   (from inside api/ folder)
"""
import json
import os
import sqlite3
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.security.api_key import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

import exports as export_engine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "src"
FRONTEND_DIR = ROOT / "frontend"
DB_PATH = ROOT / "data" / "processed" / "onchain.db"
STATUS_PATH = ROOT / "data" / "processed" / "status.json"
ANALYTICS_PATH = ROOT / "data" / "processed" / "analytics.json"
QUALITY_PATH = ROOT / "data" / "processed" / "quality_report.json"

sys.path.insert(0, str(SRC_DIR))
import main as pipeline  # noqa: E402

load_dotenv(ROOT / ".env")
INTERVAL_MIN = int(os.getenv("PIPELINE_INTERVAL_MINUTES", "60"))
API_KEY = os.getenv("API_KEY", "")  # empty = auth disabled (local dev default)

scheduler = BackgroundScheduler()
limiter = Limiter(key_func=get_remote_address)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(key: str = Security(api_key_header)):
    """Guards write endpoints. If API_KEY is unset in .env, auth is skipped (dev mode)."""
    if API_KEY and key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")
    return True


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(pipeline.run_pipeline, "date")  # immediate first run on boot
    scheduler.add_job(
        pipeline.run_pipeline, "interval", minutes=INTERVAL_MIN, id="etl_job",
        replace_existing=True,
    )
    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="On-Chain ETL Dashboard API", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics at /metrics — production monitoring, scrape with Grafana/Prometheus server
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


def get_conn():
    if not DB_PATH.exists():
        raise HTTPException(status_code=404, detail="No data yet. First automated run is in progress.")
    return sqlite3.connect(DB_PATH)


def read_json_or_404(path: Path, label: str):
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"{label} not generated yet.")
    return json.loads(path.read_text())


@app.get("/api/health")
def health():
    return {"status": "ok", "scheduler_running": scheduler.running}


@app.get("/api/status")
def status():
    job = scheduler.get_job("etl_job")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
    last_run = json.loads(STATUS_PATH.read_text()) if STATUS_PATH.exists() else None
    return {"last_run": last_run, "next_run_at": next_run, "interval_minutes": INTERVAL_MIN}


@app.get("/api/summary")
def daily_summary():
    conn = get_conn()
    rows = conn.execute(
        "SELECT day, tx_count, total_eth_volume, avg_gas_price_gwei, failed_tx_count "
        "FROM daily_summary ORDER BY day ASC"
    ).fetchall()
    conn.close()
    return [
        {"day": r[0], "tx_count": r[1], "total_eth_volume": round(r[2], 4),
         "avg_gas_price_gwei": round(r[3], 2), "failed_tx_count": r[4]}
        for r in rows
    ]


@app.get("/api/transactions")
def recent_transactions(limit: int = 25):
    conn = get_conn()
    rows = conn.execute(
        "SELECT hash, from_address, to_address, value_eth, gas_price_gwei, tx_time, is_error "
        "FROM transactions ORDER BY tx_time DESC LIMIT ?", (limit,),
    ).fetchall()
    conn.close()
    return [
        {"hash": r[0], "from": r[1], "to": r[2], "value_eth": round(r[3], 6),
         "gas_price_gwei": round(r[4], 2), "tx_time": r[5], "is_error": bool(r[6])}
        for r in rows
    ]


@app.get("/api/stats")
def stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    volume = conn.execute("SELECT SUM(value_eth) FROM transactions").fetchone()[0] or 0
    failed = conn.execute("SELECT SUM(is_error) FROM transactions").fetchone()[0] or 0
    conn.close()
    return {
        "total_transactions": total,
        "total_eth_volume": round(volume, 4),
        "failed_transactions": failed,
        "failure_rate_pct": round((failed / total * 100), 2) if total else 0,
    }


@app.get("/api/analytics")
def analytics():
    """Anomalies, trend, forecast, top wallets — the data-science layer."""
    return read_json_or_404(ANALYTICS_PATH, "Analytics")


@app.get("/api/quality")
def quality():
    """Multi-dimension data quality report."""
    return read_json_or_404(QUALITY_PATH, "Quality report")


@app.post("/api/run-pipeline")
@limiter.limit("5/minute")  # protects against accidental/malicious hammering of a real workload
def run_pipeline_now(request: Request, _auth: bool = Security(require_api_key)):
    result = pipeline.run_pipeline()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result


@app.get("/api/export/csv")
def export_csv():
    try:
        data = export_engine.build_csv()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Nothing to export yet: {e}")
    filename = f"blackloom-transactions-{datetime_stamp()}.csv"
    return Response(content=data, media_type="text/csv",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/export/xlsx")
def export_xlsx():
    try:
        data = export_engine.build_xlsx()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Nothing to export yet: {e}")
    filename = f"blackloom-report-{datetime_stamp()}.xlsx"
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@app.get("/api/export/pdf")
def export_pdf():
    try:
        data = export_engine.build_pdf()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Nothing to export yet: {e}")
    filename = f"blackloom-report-{datetime_stamp()}.pdf"
    return Response(content=data, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def datetime_stamp() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d-%H%M")


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
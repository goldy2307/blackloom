"""
Orchestrator + status tracker.
run_pipeline() is importable (used by the scheduler in api/app.py) and also
runnable standalone: python main.py

Every run writes data/processed/status.json — this is what makes the product
"automated" and observable: anyone (a script, a dashboard, a monitoring tool)
can check pipeline health without reading logs.
"""
import json
import logging
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import extract
import transform
import load
import analytics
import quality
from tenant import tenant_paths

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"

handlers = [logging.StreamHandler()]
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handlers.append(logging.FileHandler(LOG_DIR / "pipeline.log"))
except (PermissionError, OSError) as e:
    # Don't let an unwritable log directory take the whole app down —
    # console logging (visible in `docker logs` / Render's log stream) still works.
    print(f"[WARN] Could not open log file, falling back to console-only logging: {e}")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=handlers,
)
log = logging.getLogger("etl")


def run_pipeline(client_id: str | None = None, config: dict | None = None) -> dict:
    """
    Runs extract -> transform -> load -> quality -> analytics. Always writes
    status.json, never raises out of this function.

    client_id: if given, runs entirely inside that tenant's isolated data
    folder instead of the shared default one (see src/tenant.py).
    config: per-tenant overrides (etherscan_api_key, wallet_address, chain_id,
    data_source) — only meaningful together with a client_id.
    """
    t0 = time.time()
    status = {"started_at": datetime.now(timezone.utc).isoformat()}
    status_path = tenant_paths(client_id)["status"]
    log_prefix = f"[{client_id or 'default'}] "

    try:
        log.info(log_prefix + "Pipeline run starting")
        extract.run(client_id, config)
        clean_df, integrity_pct = transform.run(client_id)
        load.run(client_id)
        quality_report = quality.run(client_id)
        analytics_result = analytics.run(client_id)

        status.update({
            "success": True,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_sec": round(time.time() - t0, 2),
            "rows_loaded": int(len(clean_df)),
            "integrity_pct": integrity_pct,
            "quality_overall_score": quality_report["overall_score"],
            "anomaly_count": len(analytics_result["anomalies"]),
            "error": None,
        })
        log.info(
            log_prefix + f"Pipeline run OK | rows={len(clean_df)} integrity={integrity_pct}% "
            f"quality={quality_report['overall_score']}% anomalies={len(analytics_result['anomalies'])}"
        )

    except Exception as e:
        status.update({
            "success": False,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_sec": round(time.time() - t0, 2),
            "error": str(e),
        })
        log.error(log_prefix + f"Pipeline run FAILED: {e}\n{traceback.format_exc()}")

    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(status, indent=2))
    return status


if __name__ == "__main__":
    result = run_pipeline()
    print(json.dumps(result, indent=2))
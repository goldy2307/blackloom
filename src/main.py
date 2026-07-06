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

ROOT = Path(__file__).resolve().parent.parent
STATUS_PATH = ROOT / "data" / "processed" / "status.json"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "pipeline.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("etl")


def run_pipeline() -> dict:
    """Runs extract -> transform -> load. Always writes status.json, never raises."""
    t0 = time.time()
    status = {"started_at": datetime.now(timezone.utc).isoformat()}

    try:
        log.info("Pipeline run starting")
        extract.run()
        clean_df, integrity_pct = transform.run()
        load.run()
        quality_report = quality.run()
        analytics_result = analytics.run()

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
            f"Pipeline run OK | rows={len(clean_df)} integrity={integrity_pct}% "
            f"quality={quality_report['overall_score']}% anomalies={len(analytics_result['anomalies'])}"
        )

    except Exception as e:
        status.update({
            "success": False,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "duration_sec": round(time.time() - t0, 2),
            "error": str(e),
        })
        log.error(f"Pipeline run FAILED: {e}\n{traceback.format_exc()}")

    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, indent=2))
    return status


if __name__ == "__main__":
    result = run_pipeline()
    print(json.dumps(result, indent=2))
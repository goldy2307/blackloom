"""
DATA QUALITY stage.
Real data platforms (Great Expectations, Monte Carlo, dbt tests) score data
on multiple independent dimensions, not one "integrity %". This mirrors that:

  completeness  - fraction of required fields present
  uniqueness    - fraction of rows that are NOT duplicates
  validity      - fraction of values passing business-rule checks (value >= 0, etc)
  timeliness    - how fresh the data is (hours since newest record)

overall_score = weighted average, weights reflect what actually breaks a
pipeline in production (validity and completeness matter most).
"""
import json
from datetime import datetime, timezone

import pandas as pd

from tenant import tenant_paths

WEIGHTS = {"completeness": 0.3, "uniqueness": 0.2, "validity": 0.35, "timeliness": 0.15}


def completeness_score(raw_count: int, valid_count: int) -> float:
    return round(valid_count / raw_count * 100, 2) if raw_count else 0.0


def uniqueness_score(df: pd.DataFrame) -> float:
    if len(df) == 0:
        return 0.0
    dupes = df.duplicated(subset="hash").sum()
    return round((1 - dupes / len(df)) * 100, 2)


def validity_score(df: pd.DataFrame) -> float:
    if len(df) == 0:
        return 0.0
    checks = pd.Series(True, index=df.index)
    checks &= df["value_eth"] >= 0
    checks &= df["gas_price_gwei"] > 0
    checks &= df["block_number"] > 0 if "block_number" in df.columns else True
    return round(checks.mean() * 100, 2)


def timeliness_score(df: pd.DataFrame) -> float:
    if len(df) == 0 or "tx_time" not in df.columns:
        return 0.0
    newest = pd.to_datetime(df["tx_time"]).max()
    age_hours = (pd.Timestamp.now(tz=None) - newest.tz_localize(None)).total_seconds() / 3600
    # Score decays linearly: 100% if <24h old, 0% if >=30 days old
    return round(max(0, 100 - (age_hours / (30 * 24)) * 100), 2)


def run(client_id: str | None = None) -> dict:
    paths = tenant_paths(client_id)
    with open(paths["raw"]) as f:
        raw_count = len(json.load(f))

    df = pd.read_csv(paths["clean"])

    scores = {
        "completeness": completeness_score(raw_count, len(df)),
        "uniqueness": uniqueness_score(df),
        "validity": validity_score(df),
        "timeliness": timeliness_score(df),
    }
    overall = round(sum(scores[k] * WEIGHTS[k] for k in WEIGHTS), 2)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scores": scores,
        "weights": WEIGHTS,
        "overall_score": overall,
        "raw_row_count": raw_count,
        "clean_row_count": len(df),
    }

    paths["quality"].parent.mkdir(parents=True, exist_ok=True)
    paths["quality"].write_text(json.dumps(report, indent=2))
    print(f"[QUALITY] client={client_id or 'default'} overall_score={overall}% | breakdown={scores}")
    return report


if __name__ == "__main__":
    run()
"""
TRANSFORM stage.
Job: raw JSON -> clean pandas DataFrame.
  1. schema validation (required cols present + non-null)
  2. type casting (wei -> ETH, hex timestamp -> datetime)
  3. dedupe on tx hash
  4. compute data-integrity % (this is where the "99.9% integrity" resume metric comes from)
"""
import json
import pandas as pd

from tenant import tenant_paths

REQUIRED_COLS = ["hash", "from", "to", "value", "gas", "gasPrice", "timeStamp", "blockNumber"]


def load_raw(raw_path):
    with open(raw_path) as f:
        return pd.DataFrame(json.load(f))


def validate_schema(df: pd.DataFrame):
    """Drop rows missing any required field. Return (clean_df, integrity_pct)."""
    total = len(df)
    missing_cols = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing expected columns: {missing_cols}")

    valid = df.dropna(subset=REQUIRED_COLS)
    integrity_pct = round(len(valid) / total * 100, 2) if total else 0
    return valid, integrity_pct


def transform(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["value_eth"] = df["value"].astype(float) / 10**18
    df["gas_price_gwei"] = df["gasPrice"].astype(float) / 10**9
    df["tx_time"] = pd.to_datetime(df["timeStamp"].astype(int), unit="s")
    df["is_error"] = df["isError"].astype(int) if "isError" in df.columns else 0

    before = len(df)
    df = df.drop_duplicates(subset="hash")
    dupes_removed = before - len(df)

    keep = ["hash", "from", "to", "value_eth", "gas_price_gwei", "tx_time", "blockNumber", "is_error"]
    return df[keep], dupes_removed


def run(client_id: str | None = None):
    paths = tenant_paths(client_id)
    raw_df = load_raw(paths["raw"])
    valid_df, integrity_pct = validate_schema(raw_df)
    clean_df, dupes_removed = transform(valid_df)

    paths["clean"].parent.mkdir(parents=True, exist_ok=True)
    clean_df.to_csv(paths["clean"], index=False)
    print(
        f"[TRANSFORM] client={client_id or 'default'} raw_rows={len(raw_df)} | valid_rows={len(valid_df)} | "
        f"dupes_removed={dupes_removed} | integrity={integrity_pct}% | saved -> {paths['clean']}"
    )
    return clean_df, integrity_pct


if __name__ == "__main__":
    run()
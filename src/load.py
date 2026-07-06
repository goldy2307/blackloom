"""
LOAD stage.
Job: push clean CSV -> SQLite DB using schema.sql (creates indexed table),
then export the daily_summary view -> CSV that Power BI reads directly.
"""
import sqlite3
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CLEAN_PATH = ROOT / "data" / "processed" / "transactions_clean.csv"
DB_PATH = ROOT / "data" / "processed" / "onchain.db"
SCHEMA_PATH = ROOT / "sql" / "schema.sql"
POWERBI_EXPORT = ROOT / "data" / "processed" / "daily_summary_for_powerbi.csv"


def run():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    with open(SCHEMA_PATH) as f:
        cur.executescript(f.read())

    df = pd.read_csv(CLEAN_PATH)
    df = df.rename(columns={"from": "from_address", "to": "to_address", "blockNumber": "block_number"})

    # INSERT OR IGNORE = idempotent load, re-running pipeline won't create duplicate rows
    rows = df.to_dict("records")
    cur.executemany(
        """INSERT OR IGNORE INTO transactions
           (hash, from_address, to_address, value_eth, gas_price_gwei, tx_time, block_number, is_error)
           VALUES (:hash, :from_address, :to_address, :value_eth, :gas_price_gwei, :tx_time, :block_number, :is_error)""",
        rows,
    )
    conn.commit()

    row_count = cur.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

    summary_df = pd.read_sql("SELECT * FROM daily_summary", conn)
    summary_df.to_csv(POWERBI_EXPORT, index=False)

    conn.close()
    print(f"[LOAD] rows_in_db={row_count} | powerbi_export -> {POWERBI_EXPORT}")


if __name__ == "__main__":
    run()

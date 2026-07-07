"""
LOAD stage.
Job: push clean CSV -> SQLite DB using schema.sql (creates indexed table),
then export the daily_summary view -> CSV that Power BI reads directly.
"""
import sqlite3
from pathlib import Path
import pandas as pd

from tenant import tenant_paths

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "sql" / "schema.sql"


def run(client_id: str | None = None):
    paths = tenant_paths(client_id)
    paths["db"].parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(paths["db"])
    cur = conn.cursor()

    with open(SCHEMA_PATH) as f:
        cur.executescript(f.read())

    df = pd.read_csv(paths["clean"])
    df = df.rename(columns={"from": "from_address", "to": "to_address", "blockNumber": "block_number"})

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
    summary_df.to_csv(paths["powerbi"], index=False)

    conn.close()
    print(f"[LOAD] client={client_id or 'default'} rows_in_db={row_count} | powerbi_export -> {paths['powerbi']}")


if __name__ == "__main__":
    run()
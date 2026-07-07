"""
Config store for tenant-provided data sources.

No login system: a client_id is a random token the browser holds in
localStorage. This table just remembers what wallet/API key that token
should use. It's a convenience store, not an access-control boundary —
anyone holding a given client_id can read/change that config.
"""
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTROL_DB = ROOT / "data" / "control.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenant_configs (
    client_id TEXT PRIMARY KEY,
    data_source TEXT NOT NULL DEFAULT 'mock',
    etherscan_api_key TEXT,
    wallet_address TEXT,
    chain_id TEXT DEFAULT '1',
    updated_at TEXT NOT NULL
);
"""


def _conn():
    CONTROL_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CONTROL_DB)
    conn.execute(SCHEMA)
    return conn


def save_config(client_id: str, data_source: str, etherscan_api_key: str | None,
                 wallet_address: str | None, chain_id: str = "1") -> None:
    from datetime import datetime, timezone
    conn = _conn()
    conn.execute(
        """INSERT INTO tenant_configs (client_id, data_source, etherscan_api_key, wallet_address, chain_id, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(client_id) DO UPDATE SET
             data_source=excluded.data_source,
             etherscan_api_key=excluded.etherscan_api_key,
             wallet_address=excluded.wallet_address,
             chain_id=excluded.chain_id,
             updated_at=excluded.updated_at""",
        (client_id, data_source, etherscan_api_key, wallet_address, chain_id,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def get_config(client_id: str) -> dict | None:
    conn = _conn()
    row = conn.execute(
        "SELECT data_source, etherscan_api_key, wallet_address, chain_id, updated_at "
        "FROM tenant_configs WHERE client_id = ?", (client_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "data_source": row[0],
        "etherscan_api_key": row[1],
        "wallet_address": row[2],
        "chain_id": row[3],
        "updated_at": row[4],
    }


def mask_key(key: str | None) -> str | None:
    """Never send the full API key back to the browser once saved."""
    if not key or len(key) < 6:
        return None
    return key[:4] + "…" + key[-2:]
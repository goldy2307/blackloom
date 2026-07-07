"""
Tenant isolation layer.

No login system here — a "tenant" is just a random ID the browser generates
and stores in localStorage. This gives each visitor their own private data
folder without an account, session, or password. It is NOT real multi-user
security: anyone who learns someone else's client_id could read their config.
Good enough for "bring your own wallet," not for anything sensitive.

client_id becomes a directory name on disk, so it MUST be strictly validated —
an unsanitized client_id is a path-traversal vulnerability (e.g. "../../etc").
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")


class InvalidClientId(ValueError):
    pass


def validate_client_id(client_id: str) -> str:
    if not client_id or not CLIENT_ID_PATTERN.match(client_id):
        raise InvalidClientId(
            "client_id must be 8-64 characters, letters/numbers/hyphens/underscores only"
        )
    return client_id


def tenant_dir(client_id: str | None) -> Path:
    """
    Returns the data directory for a given tenant, or the shared default
    directory (existing scheduled demo data) if client_id is None.
    """
    if client_id is None:
        return ROOT / "data"
    validate_client_id(client_id)
    d = ROOT / "data" / "tenants" / client_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "raw").mkdir(exist_ok=True)
    (d / "processed").mkdir(exist_ok=True)
    return d


def tenant_paths(client_id: str | None) -> dict:
    base = tenant_dir(client_id)
    return {
        "raw": base / "raw" / "transactions.json",
        "clean": base / "processed" / "transactions_clean.csv",
        "db": base / "processed" / "onchain.db",
        "analytics": base / "processed" / "analytics.json",
        "quality": base / "processed" / "quality_report.json",
        "status": base / "processed" / "status.json",
        "powerbi": base / "processed" / "daily_summary_for_powerbi.csv",
    }
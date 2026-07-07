"""
EXTRACT stage.
Job: pull raw on-chain data, save untouched to data/raw/ as JSON.
Two modes:
  - mock  : generates realistic synthetic tx data (no API key needed, run this first)
  - real  : calls Etherscan API for a real wallet's tx history

Supports per-tenant overrides (own API key / wallet / chain / source) so a
visitor can plug in their own data without touching the server's .env.
"""
import os
import json
import random
import time
from pathlib import Path
import requests
from dotenv import load_dotenv

from tenant import tenant_paths

load_dotenv()


def generate_mock_data(n=1000):
    """Simulate blockchain transactions. Mimics real Etherscan tx shape."""
    txs = []
    for i in range(n):
        tx = {
            "hash": f"0x{random.getrandbits(256):064x}",
            "from": f"0x{random.getrandbits(160):040x}",
            "to": f"0x{random.getrandbits(160):040x}",
            "value": str(random.randint(0, 5 * 10**18)),  # wei
            "gas": str(random.choice([21000, 45000, 60000])),
            "gasPrice": str(random.randint(10, 100) * 10**9),
            "timeStamp": str(int(time.time()) - random.randint(0, 30 * 86400)),
            "blockNumber": str(18000000 + i),
            "isError": random.choices(["0", "1"], weights=[97, 3])[0],
        }
        txs.append(tx)

    txs += random.sample(txs, 20)          # duplicates
    txs.append({"hash": "0xbad", "from": None, "to": None})  # malformed record

    for _ in range(3):
        outlier = txs[random.randint(0, len(txs) - 1)].copy()
        outlier["hash"] = f"0x{random.getrandbits(256):064x}"
        outlier["value"] = str(random.randint(50, 100) * 10**18)
        txs.append(outlier)

    return txs


def fetch_real_data(api_key: str, wallet: str, chain_id: str = "1"):
    url = (
        "https://api.etherscan.io/v2/api"
        f"?chainid={chain_id}&module=account&action=txlist&address={wallet}"
        f"&startblock=0&endblock=99999999&sort=desc&apikey={api_key}"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    payload = resp.json()

    if payload.get("status") != "1":
        raise RuntimeError(f"Etherscan API error: {payload.get('message')} — {payload.get('result')}")

    result = payload.get("result", [])
    if not isinstance(result, list):
        raise RuntimeError(f"Unexpected Etherscan response shape: {result}")

    return result


def run(client_id: str | None = None, config: dict | None = None):
    """
    config, if given, overrides the server's .env for this run:
      {"data_source": "real"|"mock", "etherscan_api_key": "...", "wallet_address": "...", "chain_id": "1"}
    Falls back to .env values when a key is missing — lets a tenant override
    just the wallet address while still using their own key, etc.
    """
    config = config or {}
    source = config.get("data_source") or os.getenv("DATA_SOURCE", "mock")

    if source == "real":
        api_key = config.get("etherscan_api_key") or os.getenv("ETHERSCAN_API_KEY")
        wallet = config.get("wallet_address") or os.getenv("WALLET_ADDRESS")
        chain_id = config.get("chain_id") or os.getenv("CHAIN_ID", "1")
        if not api_key or not wallet:
            raise RuntimeError("real data source requires an Etherscan API key and wallet address")
        data = fetch_real_data(api_key, wallet, chain_id)
    else:
        data = generate_mock_data()

    raw_path = tenant_paths(client_id)["raw"]
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with open(raw_path, "w") as f:
        json.dump(data, f)

    print(f"[EXTRACT] client={client_id or 'default'} source={source} | rows_pulled={len(data)} | saved -> {raw_path}")
    return data


if __name__ == "__main__":
    run()
"""
EXTRACT stage.
Job: pull raw on-chain data, save untouched to data/raw/ as JSON.
Two modes:
  - mock  : generates realistic synthetic tx data (no API key needed, run this first)
  - real  : calls Etherscan API for a real wallet's tx history
"""
import os
import json
import random
import time
from pathlib import Path
import requests
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent   # project root, regardless of cwd
RAW_PATH = ROOT / "data" / "raw" / "transactions.json"


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

    # inject intentional duplicates + one bad record, to make transform stage do real work
    txs += random.sample(txs, 20)          # duplicates
    txs.append({"hash": "0xbad", "from": None, "to": None})  # malformed record

    # inject genuine statistical outliers, so anomaly detection has real signal to catch
    for _ in range(3):
        outlier = txs[random.randint(0, len(txs) - 1)].copy()
        outlier["hash"] = f"0x{random.getrandbits(256):064x}"
        outlier["value"] = str(random.randint(50, 100) * 10**18)  # 50-100 ETH, way above normal 0-5
        txs.append(outlier)

    return txs


def fetch_real_data():
    api_key = os.getenv("ETHERSCAN_API_KEY")
    wallet = os.getenv("WALLET_ADDRESS")
    chain_id = os.getenv("CHAIN_ID", "1")  # 1 = Ethereum mainnet

    # Etherscan retired the old v1 API in Aug 2025 — v2 requires chainid and a new base URL.
    url = (
        "https://api.etherscan.io/v2/api"
        f"?chainid={chain_id}&module=account&action=txlist&address={wallet}"
        f"&startblock=0&endblock=99999999&sort=desc&apikey={api_key}"
    )
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    payload = resp.json()

    # Etherscan returns {"status":"0","message":"NOTOK","result":"<error text>"} on failure —
    # "result" is a STRING then, not a list. Trusting it blindly corrupts every downstream stage.
    if payload.get("status") != "1":
        raise RuntimeError(f"Etherscan API error: {payload.get('message')} — {payload.get('result')}")

    result = payload.get("result", [])
    if not isinstance(result, list):
        raise RuntimeError(f"Unexpected Etherscan response shape: {result}")

    return result


def run():
    source = os.getenv("DATA_SOURCE", "mock")
    data = fetch_real_data() if source == "real" else generate_mock_data()

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW_PATH, "w") as f:
        json.dump(data, f)

    print(f"[EXTRACT] source={source} | rows_pulled={len(data)} | saved -> {RAW_PATH}")
    return data


if __name__ == "__main__":
    run()
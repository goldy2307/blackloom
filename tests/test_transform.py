"""
Unit tests for the transform stage. Run: pytest tests/ -v

These test the pure logic (no file I/O, no network) so they run in
milliseconds and can gate every CI build.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from transform import validate_schema, transform as transform_fn  # noqa: E402


def make_df(rows):
    return pd.DataFrame(rows)


def test_validate_schema_drops_incomplete_rows():
    df = make_df([
        {"hash": "0x1", "from": "a", "to": "b", "value": "1", "gas": "21000",
         "gasPrice": "10", "timeStamp": "1700000000", "blockNumber": "100"},
        {"hash": "0x2", "from": None, "to": "b", "value": "1", "gas": "21000",
         "gasPrice": "10", "timeStamp": "1700000000", "blockNumber": "100"},  # bad row
    ])
    valid, integrity_pct = validate_schema(df)
    assert len(valid) == 1
    assert integrity_pct == 50.0


def test_validate_schema_missing_column_raises():
    df = make_df([{"hash": "0x1"}])  # missing required cols
    with pytest.raises(ValueError):
        validate_schema(df)


def test_transform_dedupes_by_hash():
    df = make_df([
        {"hash": "0x1", "from": "a", "to": "b", "value": "1000000000000000000",
         "gas": "21000", "gasPrice": "10000000000", "timeStamp": "1700000000",
         "blockNumber": "100", "isError": "0"},
        {"hash": "0x1", "from": "a", "to": "b", "value": "1000000000000000000",
         "gas": "21000", "gasPrice": "10000000000", "timeStamp": "1700000000",
         "blockNumber": "100", "isError": "0"},  # exact duplicate hash
    ])
    clean, dupes_removed = transform_fn(df)
    assert len(clean) == 1
    assert dupes_removed == 1


def test_transform_converts_wei_to_eth():
    df = make_df([{
        "hash": "0x1", "from": "a", "to": "b", "value": str(2 * 10**18),
        "gas": "21000", "gasPrice": str(5 * 10**9), "timeStamp": "1700000000",
        "blockNumber": "100", "isError": "0",
    }])
    clean, _ = transform_fn(df)
    assert clean.iloc[0]["value_eth"] == 2.0
    assert clean.iloc[0]["gas_price_gwei"] == 5.0
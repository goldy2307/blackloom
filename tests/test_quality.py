import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from quality import completeness_score, uniqueness_score, validity_score  # noqa: E402


def test_completeness_score():
    assert completeness_score(raw_count=100, valid_count=99) == 99.0
    assert completeness_score(raw_count=0, valid_count=0) == 0.0


def test_uniqueness_score_no_dupes():
    df = pd.DataFrame({"hash": ["0x1", "0x2", "0x3"]})
    assert uniqueness_score(df) == 100.0


def test_uniqueness_score_with_dupes():
    df = pd.DataFrame({"hash": ["0x1", "0x1", "0x2"]})
    assert uniqueness_score(df) == pytest_approx(66.67)


def pytest_approx(val, tol=0.1):
    class Approx:
        def __eq__(self, other):
            return abs(other - val) < tol
    return Approx()


def test_validity_score_flags_negative_values():
    df = pd.DataFrame({
        "value_eth": [1.0, -1.0],
        "gas_price_gwei": [10.0, 10.0],
        "block_number": [100, 100],
    })
    assert validity_score(df) == 50.0
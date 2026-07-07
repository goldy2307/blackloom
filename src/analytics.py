"""
ANALYTICS stage — the actual data-science layer.
Runs after load.py. Reads clean transaction data and produces:
  1. Anomaly detection (z-score) on transaction value and gas price
  2. 7-day rolling trend (moving average + moving std) on daily volume
  3. Next-3-day volume forecast via least-squares linear regression
  4. Top wallets by volume (basic entity analysis)

Why z-score and not something fancier: it's the standard first-pass method
for univariate outlier detection, explainable to any stakeholder, and cheap
to compute — the right tool before reaching for anything heavier.

Output: data/processed/analytics.json — the API and dashboard both read this.
"""
import json

import numpy as np
import pandas as pd

from tenant import tenant_paths

Z_THRESHOLD = 3.0  # standard cutoff: |z| > 3 = statistically unusual (~0.3% under normality)


def detect_anomalies(df: pd.DataFrame) -> list:
    """Flags transactions whose value or gas price is a statistical outlier."""
    out = []
    for col, label in [("value_eth", "value"), ("gas_price_gwei", "gas_price")]:
        mu, sigma = df[col].mean(), df[col].std()
        if sigma == 0 or np.isnan(sigma):
            continue
        z = (df[col] - mu) / sigma
        flagged = df.loc[z.abs() > Z_THRESHOLD, ["hash", col, "tx_time"]].copy()
        flagged["z_score"] = round(z.loc[flagged.index], 2)
        flagged["metric"] = label
        for _, r in flagged.iterrows():
            out.append({
                "hash": r["hash"], "metric": label, "value": round(float(r[col]), 6),
                "z_score": float(r["z_score"]), "tx_time": r["tx_time"],
            })
    return sorted(out, key=lambda x: abs(x["z_score"]), reverse=True)[:20]


def daily_trend(df: pd.DataFrame) -> pd.DataFrame:
    """Rolling 7-day mean/std of daily ETH volume — smooths noise, shows real trend direction."""
    daily = df.groupby(df["tx_time"].str[:10])["value_eth"].sum().reset_index()
    daily.columns = ["day", "volume"]
    daily = daily.sort_values("day")
    daily["rolling_avg_7d"] = daily["volume"].rolling(7, min_periods=1).mean().round(4)
    daily["rolling_std_7d"] = daily["volume"].rolling(7, min_periods=1).std().fillna(0).round(4)
    return daily


def forecast_next_days(daily: pd.DataFrame, days_ahead: int = 3) -> list:
    """
    Least-squares linear regression on the trailing 14 days of volume.
    Simple on purpose — a transparent baseline forecast, not a black box.
    Returns predicted volume for the next N days with the fitted trend slope.
    """
    recent = daily.tail(14).reset_index(drop=True)
    if len(recent) < 3:
        return []

    x = np.arange(len(recent))
    y = recent["volume"].values
    slope, intercept = np.polyfit(x, y, 1)  # y = slope*x + intercept

    forecasts = []
    last_day = pd.to_datetime(recent["day"].iloc[-1])
    for i in range(1, days_ahead + 1):
        pred = slope * (len(recent) - 1 + i) + intercept
        forecasts.append({
            "day": (last_day + pd.Timedelta(days=i)).strftime("%Y-%m-%d"),
            "predicted_volume": round(max(pred, 0), 4),
        })
    return forecasts


def top_wallets(df: pd.DataFrame, n: int = 10) -> list:
    """Basic entity analysis — which wallets move the most volume."""
    vol = df.groupby("from")["value_eth"].sum().sort_values(ascending=False).head(n)
    return [{"wallet": w, "total_eth_sent": round(v, 4)} for w, v in vol.items()]


def run(client_id: str | None = None) -> dict:
    paths = tenant_paths(client_id)
    df = pd.read_csv(paths["clean"])

    daily = daily_trend(df)
    result = {
        "anomalies": detect_anomalies(df),
        "daily_trend": daily.to_dict(orient="records"),
        "forecast": forecast_next_days(daily),
        "top_wallets": top_wallets(df),
        "trend_direction": "up" if len(daily) >= 2 and daily["volume"].iloc[-1] >= daily["volume"].iloc[0] else "down",
    }

    paths["analytics"].parent.mkdir(parents=True, exist_ok=True)
    paths["analytics"].write_text(json.dumps(result, indent=2))
    print(f"[ANALYTICS] client={client_id or 'default'} anomalies={len(result['anomalies'])} | forecast_days={len(result['forecast'])} | saved -> {paths['analytics']}")
    return result


if __name__ == "__main__":
    run()
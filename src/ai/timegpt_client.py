import pandas as pd
from typing import Optional
from loguru import logger


def get_timegpt_forecast(
    df: pd.DataFrame,
    ticker: str,
    api_key: str,
    horizon: int = 5,
) -> Optional[dict]:
    """
    Request a short-horizon price forecast from TimeGPT (Nixtla).
    Returns a summary dict, or None on failure or missing dependency.
    """
    try:
        from nixtla import NixtlaClient
    except ImportError:
        logger.debug("nixtla not installed — TimeGPT unavailable. pip install nixtla")
        return None

    try:
        client = NixtlaClient(api_key=api_key)
        ts_df = pd.DataFrame({
            "unique_id": ticker,
            "ds": df.index.astype(str),
            "y": df["close"].values,
        })
        forecast = client.forecast(
            df=ts_df,
            h=horizon,
            time_col="ds",
            target_col="y",
            model="timegpt-1",
        )
        fvals = forecast["TimeGPT"].tolist()
        last = float(df["close"].iloc[-1])
        avg = sum(fvals) / len(fvals)
        change_pct = (avg - last) / last * 100

        return {
            "horizon_days": horizon,
            "forecasted_values": [round(v, 4) for v in fvals],
            "avg_forecast": round(avg, 4),
            "direction": "UP" if avg > last else "DOWN",
            "expected_change_pct": round(change_pct, 2),
        }
    except Exception as e:
        logger.warning(f"TimeGPT forecast failed for {ticker}: {e}")
        return None

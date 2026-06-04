"""
Daily watchlist scanner.

Usage:
    python -m src.jobs.scan_watchlist --market IDX --watchlist watchlists/idx_sample.csv
    python -m src.jobs.scan_watchlist --market US  --watchlist watchlists/us_sample.csv --no-alert
"""
import argparse
import sys
from pathlib import Path

from loguru import logger

from ..config import get_settings
from ..data.provider_factory import get_provider
from ..indicators.technicals import compute_indicators
from ..signals.engine import generate_signal
from ..signals.schemas import Signal
from ..ai.explanation import generate_explanation
from ..notifications.formatter import format_whatsapp_message
from ..notifications import get_notifier


def load_watchlist(path: str) -> list[str]:
    p = Path(path)
    if not p.exists():
        logger.error(f"Watchlist not found: {path}")
        sys.exit(1)
    tickers = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            tickers.append(line)
    return tickers


def scan_watchlist(
    market: str,
    watchlist_path: str,
    send_alerts: bool = True,
) -> list[Signal]:
    settings = get_settings()
    provider = get_provider(settings)
    notifier = get_notifier(settings)

    tickers = load_watchlist(watchlist_path)
    logger.info(f"Scanning {len(tickers)} tickers | market={market} | alert_threshold={settings.signal_alert_threshold}")

    results: list[Signal] = []
    alert_count = 0

    for ticker in tickers:
        logger.info(f"  → {ticker}")
        try:
            df = provider.get_ohlcv(ticker)
            if df.empty:
                logger.warning(f"    No data — skipping {ticker}")
                continue

            indicators = compute_indicators(df)
            signal = generate_signal(ticker, indicators, market=market)

            # Optional AI explanation
            if settings.has_anthropic or settings.has_openai:
                signal.ai_explanation = generate_explanation(signal, settings)

            results.append(signal)

            should_alert = (
                send_alerts
                and signal.is_actionable
                and signal.confidence >= settings.signal_alert_threshold
            )

            if should_alert:
                message = format_whatsapp_message(signal)
                sent = notifier.send(message)
                alert_count += 1
                status = "SENT" if sent else "FAILED"
                logger.info(f"    {signal.signal_type.value} ({signal.confidence}) — alert {status}")
            else:
                logger.info(f"    {signal.signal_type.value} ({signal.confidence}) — below threshold or not actionable")

        except Exception as e:
            logger.error(f"    Error processing {ticker}: {e}")

    logger.info(f"Scan complete: {len(results)}/{len(tickers)} processed, {alert_count} alerts sent")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock watchlist scanner")
    parser.add_argument("--market", default="IDX", help="Market code: IDX or US")
    parser.add_argument("--watchlist", default="watchlists/idx_sample.csv", help="CSV file of tickers")
    parser.add_argument("--no-alert", action="store_true", help="Scan only — do not send WhatsApp alerts")
    args = parser.parse_args()

    results = scan_watchlist(
        market=args.market,
        watchlist_path=args.watchlist,
        send_alerts=not args.no_alert,
    )

    # Summary table
    sep = "=" * 65
    print(f"\n{sep}")
    print(f"  SCAN RESULTS — {args.market}  ({args.watchlist})")
    print(sep)
    print(f"  {'TICKER':<15} {'SIGNAL':<22} {'CONF':>4}  REASONS")
    print(sep)
    for s in sorted(results, key=lambda x: x.confidence, reverse=True):
        first_reason = s.reasons[0][:30] if s.reasons else ""
        print(f"  {s.ticker:<15} {s.signal_type.value:<22} {s.confidence:>4}  {first_reason}")
    print(sep)


if __name__ == "__main__":
    main()

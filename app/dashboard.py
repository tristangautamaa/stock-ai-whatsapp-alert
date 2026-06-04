"""Streamlit monitoring dashboard for Stock AI WhatsApp Alert."""
import sys
from pathlib import Path

# Ensure src/ is importable when run from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.config import get_settings
from src.data.provider_factory import get_provider
from src.indicators.technicals import compute_indicators
from src.signals.engine import generate_signal
from src.signals.schemas import SignalType
from src.notifications.formatter import format_whatsapp_message
from src.notifications import get_notifier
from src.backtesting.backtest_rules import run_backtest

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock AI Alert Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

settings = get_settings()
provider = get_provider(settings)

SIGNAL_COLOR = {
    SignalType.BUY_WATCHLIST: "#22c55e",
    SignalType.SELL_WARNING: "#ef4444",
    SignalType.HOLD: "#f59e0b",
    SignalType.AVOID: "#6b7280",
}

# ── Header ────────────────────────────────────────────────────────────────────
st.title("📊 Stock AI WhatsApp Alert")
st.caption(
    f"Provider: `{settings.market_data_provider}` | "
    f"Env: `{settings.app_env}` | "
    f"DRY_RUN: `{settings.dry_run}` | "
    f"Alert threshold: `{settings.signal_alert_threshold}/100`"
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Watchlist")
    wl_file = st.selectbox("Load watchlist", [
        "watchlists/idx_sample.csv",
        "watchlists/us_sample.csv",
    ])

    default_tickers = ""
    wl_path = Path(wl_file)
    if wl_path.exists():
        default_tickers = wl_path.read_text()

    custom = st.text_area("Tickers (one per line)", value=default_tickers, height=200)
    tickers = [t.strip() for t in custom.splitlines() if t.strip() and not t.startswith("#")]

    selected = st.selectbox("Analyze ticker", tickers if tickers else ["AAPL"])
    period = st.selectbox("Lookback period", ["3mo", "6mo", "1y", "2y"], index=1)

    st.divider()
    run_scan = st.button("🔍 Scan All Tickers", use_container_width=True, type="primary")

# ── Main tabs ─────────────────────────────────────────────────────────────────
tab_analysis, tab_scan, tab_backtest, tab_whatsapp = st.tabs([
    "🔍 Ticker Analysis",
    "📋 Watchlist Scan",
    "📈 Backtest",
    "📱 WhatsApp Preview",
])

# ─────────────────── Tab 1: Ticker Analysis ───────────────────────────────────
with tab_analysis:
    st.subheader(f"Analysis: {selected}")
    with st.spinner(f"Fetching {selected}..."):
        df = provider.get_ohlcv(selected, period=period)

    if df.empty:
        st.error(f"No data returned for **{selected}**. Check the ticker symbol.")
        st.stop()

    indicators = compute_indicators(df)
    if not indicators:
        st.warning("Insufficient data to compute indicators (need ≥ 50 bars).")
        st.stop()

    signal = generate_signal(selected, indicators)

    # Signal summary row
    c1, c2, c3, c4, c5 = st.columns(5)
    sig_color = SIGNAL_COLOR.get(signal.signal_type, "#6b7280")
    c1.metric("Signal", signal.signal_type.value)
    c2.metric("Confidence", f"{signal.confidence}/100")
    c3.metric("RSI", f"{indicators.get('rsi', 0):.1f}" if indicators.get("rsi") else "N/A")
    c4.metric("Vol Ratio", f"{indicators.get('volume_ratio', 0):.2f}×" if indicators.get("volume_ratio") else "N/A")
    c5.metric("Regime", indicators.get("regime", "N/A"))

    # Price chart with MAs
    st.subheader("Price Chart")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name="OHLC",
    ))
    if indicators.get("ma20"):
        fig.add_trace(go.Scatter(
            x=df.index, y=df["close"].rolling(20).mean(),
            name="MA20", line=dict(color="#3b82f6", width=1.5),
        ))
    if indicators.get("ma50"):
        fig.add_trace(go.Scatter(
            x=df.index, y=df["close"].rolling(50).mean(),
            name="MA50", line=dict(color="#f97316", width=1.5),
        ))
    if indicators.get("ma200"):
        fig.add_trace(go.Scatter(
            x=df.index, y=df["close"].rolling(200).mean(),
            name="MA200", line=dict(color="#a855f7", width=1.5, dash="dot"),
        ))
    fig.update_layout(height=420, xaxis_rangeslider_visible=False, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    # Indicators table + signal detail
    col_l, col_r = st.columns(2)
    with col_l:
        st.subheader("Indicator Values")
        ind_display = {
            k: round(v, 4) if isinstance(v, float) else v
            for k, v in indicators.items()
            if v is not None and not isinstance(v, bool) and k not in ("regime",)
        }
        st.dataframe(
            pd.DataFrame.from_dict(ind_display, orient="index", columns=["Value"]),
            use_container_width=True,
        )

    with col_r:
        st.subheader("Signal Detail")
        if signal.reasons:
            st.markdown("**Reasons:**")
            for r in signal.reasons:
                st.write(f"• {r}")
        if signal.invalidation_conditions:
            st.markdown("**Invalidation:**")
            for c in signal.invalidation_conditions:
                st.write(f"• {c}")

    if signal.risk_control:
        rc = signal.risk_control
        st.subheader("Risk Controls")
        rc1, rc2, rc3, rc4 = st.columns(4)
        rc1.metric("Entry", f"{rc.entry_low:,.2f} – {rc.entry_high:,.2f}")
        rc2.metric("Stop Loss", f"{rc.stop_loss:,.2f}")
        rc3.metric("Target", f"{rc.target:,.2f}")
        rc4.metric("Risk/Reward", f"1:{rc.risk_reward:.1f}")

    st.caption("⚠️ For private decision support only. Not financial advice.")

# ─────────────────── Tab 2: Watchlist Scan ────────────────────────────────────
with tab_scan:
    st.subheader("Watchlist Scan Results")
    if run_scan and tickers:
        scan_results = []
        progress_bar = st.progress(0, text="Scanning...")
        for i, t in enumerate(tickers):
            progress_bar.progress((i + 1) / len(tickers), text=f"Scanning {t}...")
            try:
                df_t = provider.get_ohlcv(t, period="3mo")
                if not df_t.empty:
                    ind_t = compute_indicators(df_t)
                    sig_t = generate_signal(t, ind_t)
                    scan_results.append({
                        "Ticker": t,
                        "Signal": sig_t.signal_type.value,
                        "Confidence": sig_t.confidence,
                        "RSI": round(ind_t.get("rsi") or 0, 1),
                        "Vol×": round(ind_t.get("volume_ratio") or 0, 2),
                        "Regime": ind_t.get("regime", "N/A"),
                        "Reasons": (sig_t.reasons[0][:40] if sig_t.reasons else ""),
                    })
            except Exception as e:
                st.warning(f"{t}: {e}")

        progress_bar.empty()
        if scan_results:
            df_scan = pd.DataFrame(scan_results).sort_values("Confidence", ascending=False)
            st.dataframe(df_scan, use_container_width=True, hide_index=True)
        else:
            st.warning("No results returned.")
    elif run_scan:
        st.info("Add tickers in the sidebar first.")
    else:
        st.info("Click **Scan All Tickers** in the sidebar to run a bulk scan.")

# ─────────────────── Tab 3: Backtest ──────────────────────────────────────────
with tab_backtest:
    st.subheader(f"Backtest — {selected}")
    bt_period = st.selectbox("Backtest period", ["1y", "2y", "3y"], index=1)
    if st.button("▶ Run Backtest", type="primary"):
        with st.spinner("Running backtest (may take 30–60s for long periods)..."):
            metrics = run_backtest(selected, period=bt_period)
        if metrics:
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Total Return", f"{metrics['total_return_pct']:+.1f}%")
            m2.metric("Win Rate", f"{metrics['win_rate_pct']:.1f}%")
            m3.metric("Max Drawdown", f"{metrics['max_drawdown_pct']:.1f}%")
            m4.metric("Sharpe", f"{metrics['sharpe_ratio']:.2f}")
            m5.metric("Trades", metrics["num_trades"])
            st.caption(f"Engine: `{metrics.get('engine', 'pandas')}` | Fees included: {metrics.get('fees_paid', 0):.4f}")
        else:
            st.error("Backtest failed — check logs / data availability")

# ─────────────────── Tab 4: WhatsApp Preview ──────────────────────────────────
with tab_whatsapp:
    st.subheader("WhatsApp Message Preview")
    if "signal" in dir():
        preview_msg = format_whatsapp_message(signal)
        st.code(preview_msg, language=None)

        col_send, col_info = st.columns([1, 2])
        with col_send:
            if st.button("📤 Send Alert (respects DRY_RUN)", type="primary"):
                notifier = get_notifier(settings)
                sent = notifier.send(preview_msg)
                if sent:
                    st.success("✅ Sent! (or printed if DRY_RUN=true)")
                else:
                    st.error("❌ Send failed — check credentials in .env")
        with col_info:
            st.info(
                f"Provider: **{settings.whatsapp_provider.upper()}** | "
                f"DRY_RUN: **{settings.dry_run}**\n\n"
                "Set `DRY_RUN=false` in `.env` to send real messages."
            )
    else:
        st.info("Analyze a ticker in the **Ticker Analysis** tab first.")

st.divider()
st.caption(
    "📌 Stock AI WhatsApp Alert v0.1.0 · Private use only · "
    "Not financial advice · No trade execution · Manual confirmation required"
)

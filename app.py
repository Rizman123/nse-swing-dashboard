from __future__ import annotations

import os
import random
import statistics
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template

app = Flask(__name__, static_folder="static", template_folder="templates")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ---------------------------------------------------------------------------
# Sample NSE universe. Swap this block for real Zerodha data once the
# ZERODHA_API_KEY / ZERODHA_ACCESS_TOKEN secrets are set - see USE_SAMPLE_DATA.
# ---------------------------------------------------------------------------

USE_SAMPLE_DATA = os.environ.get("USE_SAMPLE_DATA", "true").lower() != "false"

UNIVERSE = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "HINDUNILVR",
    "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT", "AXISBANK",
    "BAJFINANCE", "ASIANPAINT", "MARUTI", "TITAN", "SUNPHARMA", "WIPRO",
    "TATAMOTORS", "TATASTEEL", "POWERGRID", "NTPC", "HCLTECH", "JSWSTEEL",
    "TECHM", "DIVISLAB", "HDFCLIFE", "SBILIFE", "DRREDDY", "EICHERMOT",
    "CIPLA", "BPCL", "BRITANNIA", "HEROMOTOCO", "APOLLOHOSP", "INDUSINDBK",
]

SECTORS = ["IT", "Banking", "FMCG", "Auto", "Pharma", "Energy", "Metals"]


def _seeded_random():
    seed = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rng = random.Random(seed)
    return rng


def generate_universe_metrics():
    rng = _seeded_random()
    stocks = []
    for symbol in UNIVERSE:
        price = round(rng.uniform(250, 4200), 2)
        stocks.append({
            "symbol": symbol,
            "close": price,
            "open": round(price * rng.uniform(0.98, 1.0), 2),
            "prev_close": round(price * rng.uniform(0.97, 1.0), 2),
            "volume": rng.randint(400_000, 9_000_000),
            "avg_volume_20d": rng.randint(350_000, 7_000_000),
            "delivery_pct": round(rng.uniform(15, 78), 2),
            "delivery_pct_60d_avg": round(rng.uniform(20, 60), 2),
            "delivery_pct_60d_std": round(rng.uniform(5, 15), 2),
            "sma_50": round(price * rng.uniform(0.90, 1.05), 2),
            "sma_200": round(price * rng.uniform(0.85, 1.08), 2),
            "high_52w": round(price * rng.uniform(1.0, 1.28), 2),
            "low_recent": round(price * rng.uniform(0.94, 0.99), 2),
            "atr_20": round(price * rng.uniform(0.01, 0.04), 2),
            "atr_60d_avg": round(price * rng.uniform(0.015, 0.035), 2),
            "return_20d": round(rng.uniform(-0.10, 0.15), 4),
            "return_90d": round(rng.uniform(-0.15, 0.25), 4),
            "volatility_20d": round(rng.uniform(0.01, 0.04), 4),
            "sector": rng.choice(SECTORS),
            "sector_return_20d": round(rng.uniform(-0.08, 0.12), 4),
            "in_fo_ban": rng.random() < 0.05,
            "is_t2t": rng.random() < 0.02,
            "upcoming_results_5d": rng.random() < 0.10,
            "bulk_deals_5d": rng.randint(0, 2),
            "promoter_buys_30d": rng.randint(0, 1),
        })
    return stocks


def generate_market_context():
    rng = _seeded_random()
    vix = round(rng.uniform(11, 21), 2)
    nifty_price = round(rng.uniform(24000, 25600), 2)
    nifty_change = round(rng.uniform(-1.4, 1.6), 2)
    nifty_above_200sma = rng.random() < 0.7
    breadth = round(rng.uniform(35, 72), 1)

    if vix > 22 or not nifty_above_200sma or breadth < 40:
        regime = "RISK-OFF"
    elif vix < 18 and nifty_above_200sma and breadth > 50:
        regime = "RISK-ON"
    else:
        regime = "NEUTRAL"

    advances = rng.randint(900, 1900)
    declines = rng.randint(700, 1600)

    return {
        "vix": vix,
        "nifty_price": nifty_price,
        "nifty_change": nifty_change,
        "regime": regime,
        "breadth_pct": breadth,
        "advances": advances,
        "declines": declines,
        "pcr_oi_60d_percentile": round(rng.uniform(10, 90), 1),
        "fii_net_long_ratio": round(rng.uniform(0.35, 0.65), 3),
    }


PILLAR_WEIGHTS = {
    "volume_delivery": 0.25,
    "price_action": 0.20,
    "momentum": 0.20,
    "option_chain": 0.20,
    "institutional": 0.15,
}


def passes_prefilter(s):
    if s["close"] < 20:
        return False
    if s["avg_volume_20d"] * s["close"] < 5_000_000:
        return False
    if s["close"] < s["sma_200"]:
        return False
    if s["in_fo_ban"] or s["is_t2t"]:
        return False
    return True


def _check(name, threshold, actual, passed):
    return {"signal": name, "threshold": threshold, "actual": actual, "status": "pass" if passed else "fail"}


def score_volume_delivery(s):
    checks = []
    delivery_z = (s["delivery_pct"] - s["delivery_pct_60d_avg"]) / max(s["delivery_pct_60d_std"], 1)
    checks.append(_check("Delivery momentum (vs own 60-day baseline)", "z-score >= +0.5",
                          f"{delivery_z:+.2f}", delivery_z >= 0.5))

    vol_z = (s["volume"] - s["avg_volume_20d"]) / max(s["avg_volume_20d"] * 0.3, 1)
    price_move = (s["close"] - s["open"]) / max(s["open"], 1) * 100
    checks.append(_check("Volume confirms up-move", "up day + volume z-score > +0.5",
                          f"price {price_move:+.1f}%, vol z {vol_z:+.2f}", price_move > 0 and vol_z > 0.5))

    checks.append(_check("Volume shock present (drift signal)", "volume z-score > +1.5",
                          f"{vol_z:+.2f}", vol_z > 1.5))

    fired = sum(1 for c in checks if c["status"] == "pass")
    return fired / len(checks), checks


def score_price_action(s):
    checks = []
    dist_to_high = (s["high_52w"] - s["close"]) / max(s["high_52w"], 1)
    checks.append(_check("Breakout / near 52-week high with volume", "within 3% of 52w high",
                          f"{dist_to_high*100:.1f}% below high", dist_to_high < 0.03))

    uptrend = s["close"] > s["sma_50"] > s["sma_200"]
    checks.append(_check("Healthy uptrend structure (Close > SMA50 > SMA200)", "yes",
                          "yes" if uptrend else "no", uptrend))

    atr_z = (s["atr_20"] - s["atr_60d_avg"]) / max(s["atr_60d_avg"] * 0.3, 0.01)
    checks.append(_check("Volatility contraction (coiled base)", "ATR z-score < -0.7",
                          f"{atr_z:+.2f}", atr_z < -0.7))

    checks.append(_check("52-week high proximity (George-Hwang effect)", "within 5% of 52w high",
                          f"{dist_to_high*100:.1f}% below high", dist_to_high < 0.05))

    fired = sum(1 for c in checks if c["status"] == "pass")
    return fired / len(checks), checks


def score_momentum(s, market):
    checks = []
    nifty_baseline_90d = 0.05
    rel_return = s["return_90d"] - nifty_baseline_90d
    checks.append(_check("Relative strength vs Nifty (3-month)", "outperforming index",
                          f"{rel_return*100:+.1f}% relative", rel_return > 0.03))

    risk_adj = s["return_20d"] / max(s["volatility_20d"], 0.001)
    checks.append(_check("Volatility-adjusted momentum positive", "risk-adjusted return > 2.0",
                          f"{risk_adj:.2f}", risk_adj > 2.0))

    sector_rs = s["return_20d"] - s["sector_return_20d"]
    checks.append(_check("Outperforming own sector", "stock return > sector return",
                          f"{sector_rs*100:+.1f}% vs sector", sector_rs > 0.01))

    fired = sum(1 for c in checks if c["status"] == "pass")
    return fired / len(checks), checks


def score_option_chain(s, market):
    checks = []
    checks.append(_check("NIFTY PCR positioning (bullish zone)", "PCR percentile < 30",
                          f"{market['pcr_oi_60d_percentile']:.0f}th percentile",
                          market["pcr_oi_60d_percentile"] < 30))
    checks.append(_check("FII net long bias (index futures)", "FII long ratio > 0.55",
                          f"{market['fii_net_long_ratio']:.2f}", market["fii_net_long_ratio"] > 0.55))
    fired = sum(1 for c in checks if c["status"] == "pass")
    return fired / len(checks), checks


def score_institutional(s):
    checks = []
    checks.append(_check("Recent bulk/block buy deal", ">= 1 buy deal in last 5 days",
                          f"{s['bulk_deals_5d']} deals", s["bulk_deals_5d"] >= 1))
    checks.append(_check("Promoter open-market purchase", ">= 1 in last 30 days",
                          f"{s['promoter_buys_30d']} purchases", s["promoter_buys_30d"] >= 1))
    checks.append(_check("No earnings/event risk in next 5 days", "no results scheduled",
                          "results due soon" if s["upcoming_results_5d"] else "clear",
                          not s["upcoming_results_5d"]))
    fired = sum(1 for c in checks if c["status"] == "pass")
    return fired / len(checks), checks


PILLAR_CATEGORY_NAMES = {
    "volume_delivery": "Volume & Delivery",
    "price_action": "Price Action",
    "momentum": "Momentum & Relative Strength",
    "option_chain": "Option Chain / Market Positioning",
    "institutional": "Institutional & Corporate",
}


def score_stock(s, market):
    pillars = {
        "volume_delivery": score_volume_delivery(s),
        "price_action": score_price_action(s),
        "momentum": score_momentum(s, market),
        "option_chain": score_option_chain(s, market),
        "institutional": score_institutional(s),
    }

    composite = sum(pillars[k][0] * PILLAR_WEIGHTS[k] for k in PILLAR_WEIGHTS) * 100

    if market["regime"] == "RISK-OFF":
        composite = max(0, composite - 20)

    checklist = []
    fired_names = []
    for key, (frac, checks) in pillars.items():
        category = PILLAR_CATEGORY_NAMES[key]
        for c in checks:
            checklist.append({
                "category": category,
                "signal": c["signal"],
                "threshold": c["threshold"],
                "actual": c["actual"],
                "status": c["status"],
            })
            if c["status"] == "pass":
                fired_names.append(c["signal"])

    return round(composite, 1), checklist, fired_names


def build_summary(symbol, score, fired_names, checklist):
    if not fired_names:
        return f"Limited signal confirmation right now ({score}/100). Most checklist criteria did not fire - treat as a watch, not a setup."
    not_fired = [c["signal"] for c in checklist if c["status"] == "fail"]
    lead = fired_names[0]
    risk = f" Watch for: {not_fired[0].lower()} has not confirmed yet." if not_fired else ""
    return f"Score {score}/100. Primary signal: {lead}.{risk}"


def generate_gemini_summary(symbol, score, fired_names, checklist, regime):
    if not GEMINI_API_KEY:
        return build_summary(symbol, score, fired_names, checklist)
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        not_fired = [c["signal"] for c in checklist if c["status"] == "fail"]
        prompt = (
            "You are a swing-trading analyst for NSE stocks. Using ONLY the data below, "
            "write 3-4 sentences: (1) the primary bullish reason, (2) one supporting signal, "
            "(3) a counter-argument/risk, using ONLY the listed non-fired signals. "
            "Never invent numbers. Never recommend a trade directly, describe the setup.\n\n"
            f"Stock: {symbol}\nScore: {score}/100\nMarket regime: {regime}\n"
            f"Signals fired: {fired_names}\nSignals not fired: {not_fired}\n"
        )
        resp = model.generate_content(prompt, generation_config=genai.types.GenerationConfig(
            temperature=0.3, max_output_tokens=220))
        return resp.text.strip()
    except Exception as exc:
        print(f"[WARNING] Gemini call failed for {symbol}: {exc}")
        return build_summary(symbol, score, fired_names, checklist)


def dashboard_payload():
    market = generate_market_context()
    universe = generate_universe_metrics()
    candidates = [s for s in universe if passes_prefilter(s)]

    scored = []
    for s in candidates:
        score, checklist, fired_names = score_stock(s, market)
        scored.append((s, score, checklist, fired_names))

    scored.sort(key=lambda x: x[1], reverse=True)
    top5 = scored[:5]

    top_5_stocks = []
    for s, score, checklist, fired_names in top5:
        target = round(min(s["high_52w"], s["close"] * 1.04), 2)
        stop = round(max(s["low_recent"], s["close"] * 0.97), 2)
        change_pct = round((s["close"] - s["prev_close"]) / max(s["prev_close"], 1) * 100, 2)
        summary = generate_gemini_summary(s["symbol"], score, fired_names, checklist, market["regime"])
        top_5_stocks.append({
            "symbol": s["symbol"],
            "current_price": s["close"],
            "score": score,
            "gemini_summary": summary,
            "target_price": target,
            "stop_price": stop,
            "change_percent": change_pct,
            "checklist": checklist,
        })

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "market_regime": market["regime"],
        "india_vix": market["vix"],
        "nifty_price": market["nifty_price"],
        "nifty_change": market["nifty_change"],
        "breadth_advances": market["advances"],
        "breadth_declines": market["declines"],
        "breadth_pct": market["breadth_pct"],
        "top_5_stocks": top_5_stocks,
        "data_source": "SAMPLE_DATA (Zerodha API not yet connected)" if USE_SAMPLE_DATA else "ZERODHA_LIVE",
    }


@app.get("/")
def index():
    return render_template("index.html", data=dashboard_payload())


@app.get("/api/dashboard")
def dashboard():
    return jsonify(dashboard_payload())


@app.get("/api/healthz")
def healthz():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)

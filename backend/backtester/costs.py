"""Transaction-cost models and market helpers. Rates are fractions of traded value, charged per fill.

India delivery (NSE cash equity held overnight). Statutory charges as published by NSE/SEBI; they change from time
to time, so check the latest exchange circulars before relying on them:
- STT (securities transaction tax): 0.1% on both buy and sell
- Exchange transaction charge (NSE): 0.00297% on both sides
- SEBI turnover fee: Rs 10 per crore = 0.0001% on both sides
- Stamp duty: 0.015% on the buy side only
- GST: 18% on brokerage + exchange transaction charge + SEBI fee (not on STT or stamp duty)
Flat per-order charges (DP charge on sells, minimum brokerage) are not modelled: the engine charges percentages.
"""
from decimal import Decimal as D

FLAT, INDIA_DELIVERY = "flat", "india_delivery"
COST_MODELS = {FLAT: "Flat % per fill", INDIA_DELIVERY: "India delivery (NSE/BSE): brokerage + statutory charges"}

INDIA_RATES = {"stt": D("0.001"), "exchange_txn": D("0.0000297"), "sebi_fee": D("0.000001"),
               "stamp_duty_buy": D("0.00015"), "gst": D("0.18")}


def india_delivery(brokerage_pct=D(0)):
    """Returns (buy_rate, sell_rate, breakdown). brokerage_pct is the broker's own charge per side."""
    r, b = INDIA_RATES, D(brokerage_pct)
    gst = (b + r["exchange_txn"] + r["sebi_fee"]) * r["gst"]
    common = b + r["stt"] + r["exchange_txn"] + r["sebi_fee"] + gst
    buy, sell = common + r["stamp_duty_buy"], common
    breakdown = {"brokerage": b, "stt": r["stt"], "exchange_txn": r["exchange_txn"], "sebi_fee": r["sebi_fee"],
                 "gst": gst, "stamp_duty_buy": r["stamp_duty_buy"], "buy_total": buy, "sell_total": sell}
    return buy, sell, breakdown


def rates(cost_model, commission_pct):
    """(buy_rate, sell_rate) for a run. For India, commission_pct is the brokerage."""
    if cost_model == INDIA_DELIVERY:
        buy, sell, _ = india_delivery(commission_pct)
        return buy, sell
    return D(commission_pct), D(commission_pct)


# ---------------------------------------------------------------- markets

INDIAN_INDICES = {"^NSEI", "^NSEBANK", "^BSESN", "^CNXIT", "^CNXAUTO", "^CNXPHARMA", "^CNXFMCG", "^CNXMETAL",
                  "^CNXREALTY", "^CNXENERGY", "^NSMIDCP", "^CNXSMALLCAP", "^INDIAVIX"}

SUGGESTED_SYMBOLS = [
    {"symbol": "^NSEI", "name": "NIFTY 50"}, {"symbol": "^NSEBANK", "name": "NIFTY Bank"},
    {"symbol": "^BSESN", "name": "BSE Sensex"}, {"symbol": "RELIANCE.NS", "name": "Reliance Industries"},
    {"symbol": "TCS.NS", "name": "Tata Consultancy Services"}, {"symbol": "HDFCBANK.NS", "name": "HDFC Bank"},
    {"symbol": "INFY.NS", "name": "Infosys"}, {"symbol": "ICICIBANK.NS", "name": "ICICI Bank"},
    {"symbol": "SBIN.NS", "name": "State Bank of India"}, {"symbol": "ITC.NS", "name": "ITC"},
    {"symbol": "LT.NS", "name": "Larsen & Toubro"}, {"symbol": "BHARTIARTL.NS", "name": "Bharti Airtel"},
    {"symbol": "SPY", "name": "S&P 500 ETF"}, {"symbol": "QQQ", "name": "Nasdaq-100 ETF"},
    {"symbol": "AAPL", "name": "Apple"}, {"symbol": "MSFT", "name": "Microsoft"}, {"symbol": "NVDA", "name": "NVIDIA"},
]


def currency(symbol):
    """Currency inferred from the Yahoo symbol: INR for NSE/BSE, USD for plain US tickers, None when unknown
    (another exchange suffix such as .L or .T). Shown to the user as a label, never used in calculations."""
    s = (symbol or "").upper()
    if s.endswith((".NS", ".BO")) or s in INDIAN_INDICES:
        return "INR"
    if "." in s or s.startswith("^") or "=" in s:
        return "USD" if s in {"^GSPC", "^DJI", "^IXIC", "^RUT", "^VIX"} else None
    return "USD"

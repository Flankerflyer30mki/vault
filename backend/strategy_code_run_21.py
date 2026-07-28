def on_bar(bar, indicators, state):
    sma_10 = indicators.get('sma_10')
    sma_50 = indicators.get('sma_50')

    if sma_10 is None or sma_50 is None:
        return "HOLD"

    if sma_10 > sma_50:
        return "BUY"
    elif sma_10 < sma_50:
        return "SELL"
    else:
        return "HOLD"

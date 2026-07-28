def on_bar(bar, state):
    if 'prices' not in state:
        state['prices'] = []

    state['prices'].append(bar['close'])

    if len(state['prices']) < 10:
        return "HOLD"

    short_avg = sum(state['prices'][-5:]) / 5
    long_avg = sum(state['prices'][-10:]) / 10

    if short_avg > long_avg:
        return "BUY"
    elif short_avg < long_avg:
        return "SELL"
    else:
        return "HOLD"
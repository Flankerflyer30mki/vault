import math
from decimal import Decimal
from backtester.models import Bar, Trade


def calculate_metrics(run):
    trades = list(Trade.objects.filter(run=run).order_by('ts'))
    bars = list(Bar.objects.filter(
        symbol=run.symbol,
        ts__date__gte=run.start_date,
        ts__date__lte=run.end_date
    ).order_by('ts'))

    if not trades or not bars:
        return

    # Step 1: Rebuild the equity curve — portfolio value at every bar
    equity_curve = []
    cash = float(run.starting_cash)
    shares_held = 0.0
    trade_idx = 0

    for bar in bars:
        # Apply any trade that happened on this exact bar
        while trade_idx < len(trades) and trades[trade_idx].ts == bar.ts:
            trade = trades[trade_idx]
            if trade.side == 'BUY':
                cash -= float(trade.price) * float(trade.quantity)
                shares_held += float(trade.quantity)
            else:  # SELL
                cash += float(trade.price) * float(trade.quantity)
                shares_held -= float(trade.quantity)
            trade_idx += 1

        portfolio_value = cash + shares_held * float(bar.close)
        equity_curve.append(portfolio_value)

    # Step 2: CAGR
    starting_value = float(run.starting_cash)
    final_value = equity_curve[-1]
    days = (run.end_date - run.start_date).days
    years = days / 365.25

    if years > 0 and starting_value > 0:
        cagr = (final_value / starting_value) ** (1 / years) - 1
    else:
        cagr = 0.0

    # Step 3: Max Drawdown
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        drawdown = (peak - value) / peak
        if drawdown > max_dd:
            max_dd = drawdown

    # Step 4: Sharpe Ratio (using daily returns of the equity curve)
    daily_returns = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1]
        curr = equity_curve[i]
        if prev > 0:
            daily_returns.append((curr - prev) / prev)

    if len(daily_returns) > 1:
        mean_return = sum(daily_returns) / len(daily_returns)
        variance = sum((r - mean_return) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
        std_dev = math.sqrt(variance)
        sharpe = (mean_return / std_dev) * math.sqrt(252) if std_dev > 0 else 0.0
    else:
        sharpe = 0.0

    # Step 5: Win Rate (match BUY -> SELL pairs)
    wins = 0
    completed_pairs = 0
    open_buy = None
    for trade in trades:
        if trade.side == 'BUY':
            open_buy = trade
        elif trade.side == 'SELL' and open_buy:
            completed_pairs += 1
            if trade.price > open_buy.price:
                wins += 1
            open_buy = None

    win_rate = (wins / completed_pairs) if completed_pairs > 0 else 0.0

    # Save everything back to the run
    run.cagr = cagr
    run.max_drawdown = max_dd
    run.sharpe_ratio = sharpe
    run.win_rate = win_rate
    run.equity_curve = equity_curve
    run.save()

    return {
        'cagr': cagr,
        'max_drawdown': max_dd,
        'sharpe_ratio': sharpe,
        'win_rate': win_rate,
        'equity_curve': equity_curve
    }
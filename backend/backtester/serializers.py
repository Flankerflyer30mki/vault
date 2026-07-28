from rest_framework import serializers
from backtester.models import Strategy, BacktestRun, Trade


class StrategySerializer(serializers.ModelSerializer):
    class Meta:
        model = Strategy
        fields = ['id', 'name', 'code', 'created_at']


class TradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trade
        fields = ['id', 'side', 'ts', 'price', 'quantity']


class BacktestRunSerializer(serializers.ModelSerializer):
    strategy_name = serializers.CharField(source='strategy.name', read_only=True)

    class Meta:
        model = BacktestRun
        fields = [
            'id', 'strategy', 'strategy_name', 'symbol', 'start_date', 'end_date',
            'starting_cash', 'status', 'error_message', 'created_at', 'completed_at',
            'final_value', 'cagr', 'sharpe_ratio', 'max_drawdown', 'win_rate',
            'execution_time_ms', 'bars_processed',
            'max_position_pct', 'commission_pct', 'slippage_pct',
            'stop_loss_pct', 'take_profit_pct'
        ]
        read_only_fields = [
            'status', 'error_message', 'completed_at', 'final_value', 'cagr',
            'sharpe_ratio', 'max_drawdown', 'win_rate', 'execution_time_ms', 'bars_processed'
        ]
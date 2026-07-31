from rest_framework import serializers
from backtester.models import Strategy, BacktestRun, Trade
from backtester.models import Strategy, BacktestRun, Trade, OptimizationJob

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
            'stop_loss_pct', 'take_profit_pct','equity_curve'
        ]
        read_only_fields = [
            'status', 'error_message', 'completed_at', 'final_value', 'cagr',
            'sharpe_ratio', 'max_drawdown', 'win_rate', 'execution_time_ms', 'bars_processed','equity_curve'
        ]
    def validate(self, data):
        if data['end_date'] <= data['start_date']:
            raise serializers.ValidationError("end_date must be after start_date")

        from backtester.data_fetch import ensure_symbol_data
        success = ensure_symbol_data(data['symbol'], data['start_date'], data['end_date'])
        if not success:
            raise serializers.ValidationError(
                f"Could not find market data for symbol '{data['symbol']}'. Check the ticker is correct."
            )

        return data

class OptimizationJobSerializer(serializers.ModelSerializer):
    strategy_name = serializers.CharField(source='strategy.name', read_only=True)
    run_ids = serializers.PrimaryKeyRelatedField(source='runs', many=True, read_only=True)

    class Meta:
        model = OptimizationJob
        fields = [
            'id', 'strategy', 'strategy_name', 'symbol', 'start_date', 'end_date',
            'starting_cash', 'stop_loss_options', 'take_profit_options',
            'status', 'created_at', 'completed_at', 'run_ids'
        ]
        read_only_fields = ['status', 'completed_at', 'run_ids']
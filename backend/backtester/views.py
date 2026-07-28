import threading
from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from backtester.models import Strategy, BacktestRun, Trade, OptimizationJob
from backtester.serializers import StrategySerializer, BacktestRunSerializer, TradeSerializer, OptimizationJobSerializer
from backtester.optimizer import run_optimization
from backtester.engine import run_backtest
from backtester.progress import get_progress
from backtester.metrics import calculate_metrics


class StrategyListCreateView(generics.ListCreateAPIView):
    queryset = Strategy.objects.all().order_by('-created_at')
    serializer_class = StrategySerializer


class BacktestRunListCreateView(generics.ListCreateAPIView):
    queryset = BacktestRun.objects.all().order_by('-created_at')
    serializer_class = BacktestRunSerializer

    def perform_create(self, serializer):
        run = serializer.save()
        # Save the strategy's code to a temp file for the sandbox subprocess to read
        code_file_path = f"strategy_code_run_{run.id}.py"
        with open(code_file_path, 'w') as f:
            f.write(run.strategy.code)

        # Run the backtest in a background thread so this request returns immediately
        thread = threading.Thread(target=run_backtest, args=(run.id, code_file_path))
        thread.start()


class BacktestRunDetailView(generics.RetrieveAPIView):
    queryset = BacktestRun.objects.all()
    serializer_class = BacktestRunSerializer


class TradeListView(generics.ListAPIView):
    serializer_class = TradeSerializer

    def get_queryset(self):
        run_id = self.kwargs['run_id']
        return Trade.objects.filter(run_id=run_id).order_by('ts')


class ProgressView(APIView):
    def get(self, request, run_id):
        progress = get_progress(run_id)
        if progress is None:
            run = BacktestRun.objects.filter(id=run_id).first()
            if run and run.status == 'completed':
                return Response({"processed": run.bars_processed, "total": run.bars_processed, "done": True})
            if run and run.status == 'failed':
                return Response({"processed": 0, "total": 0, "done": True, "error": run.error_message})
            return Response({"processed": 0, "total": 0, "done": False})
        return Response({**progress, "done": False})


class EquityCurveView(APIView):
    def get(self, request, run_id):
        run = BacktestRun.objects.filter(id=run_id).first()
        if not run:
            return Response({"error": "Run not found"}, status=status.HTTP_404_NOT_FOUND)

        return Response({"equity_curve": run.equity_curve or []})

class OptimizationJobListCreateView(generics.ListCreateAPIView):
    queryset = OptimizationJob.objects.all().order_by('-created_at')
    serializer_class = OptimizationJobSerializer

    def perform_create(self, serializer):
        job = serializer.save()
        code_file_path = f"strategy_code_opt_{job.id}.py"
        with open(code_file_path, 'w') as f:
            f.write(job.strategy.code)

        thread = threading.Thread(target=run_optimization, args=(job.id, code_file_path))
        thread.start()


class OptimizationJobDetailView(generics.RetrieveAPIView):
    queryset = OptimizationJob.objects.all()
    serializer_class = OptimizationJobSerializer
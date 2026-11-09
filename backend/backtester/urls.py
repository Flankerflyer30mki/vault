from django.urls import path

from backtester import views

urlpatterns = [
    path("strategies/", views.StrategyListCreateView.as_view()),
    path("runs/", views.BacktestRunListCreateView.as_view()),
    path("runs/<int:pk>/", views.BacktestRunDetailView.as_view()),
    path("runs/<int:run_id>/trades/", views.TradeListView.as_view()),
    path("optimizations/", views.OptimizationJobListCreateView.as_view()),
    path("optimizations/<int:pk>/", views.OptimizationJobDetailView.as_view()),
]

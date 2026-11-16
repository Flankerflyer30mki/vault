from django.urls import path

from backtester import views

urlpatterns = [
    path("dashboard/", views.DashboardView.as_view()),
    path("strategies/", views.StrategyListCreateView.as_view()),
    path("strategies/catalog/", views.StrategyCatalogView.as_view()),
    path("strategies/preview/", views.SpecPreviewView.as_view()),
    path("strategies/<int:pk>/", views.StrategyDetailView.as_view()),
    path("runs/", views.BacktestRunListCreateView.as_view()),
    path("runs/<int:pk>/", views.BacktestRunDetailView.as_view()),
    path("runs/<int:run_id>/trades/", views.TradeListView.as_view()),
    path("optimizations/", views.OptimizationJobListCreateView.as_view()),
    path("optimizations/<int:pk>/", views.OptimizationJobDetailView.as_view()),
]

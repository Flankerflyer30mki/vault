from django.urls import path
from backtester import views

urlpatterns = [
    path('strategies/', views.StrategyListCreateView.as_view()),
    path('runs/', views.BacktestRunListCreateView.as_view()),
    path('runs/<int:pk>/', views.BacktestRunDetailView.as_view()),
    path('runs/<int:run_id>/trades/', views.TradeListView.as_view()),
    path('runs/<int:run_id>/progress/', views.ProgressView.as_view()),
    path('runs/<int:run_id>/equity-curve/', views.EquityCurveView.as_view()),
]
from django.urls import path

from assist import views

urlpatterns = [
    path("strategy/", views.AssistStrategyView.as_view()),
    path("<int:pk>/", views.AssistDetailView.as_view()),
]

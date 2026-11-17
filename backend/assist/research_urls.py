from django.urls import path

from assist import views

urlpatterns = [
    path("", views.ResearchListCreateView.as_view()),
    path("<int:pk>/", views.ResearchDetailView.as_view()),
]

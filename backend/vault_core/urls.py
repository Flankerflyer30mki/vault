from django.db import connection
from django.http import JsonResponse
from django.urls import include, path


def live(request):
    return JsonResponse({"status": "ok"})


def ready(request):
    """Ready = the database answers. The market-data provider is optional: existing data stays usable."""
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "unavailable", "database": "down"}, status=503)
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("health/live", live),
    path("health/ready", ready),
    path("api/", include("backtester.urls")),
]

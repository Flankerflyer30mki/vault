import hmac
import os

from django.conf import settings
from django.db import connection
from django.http import Http404, HttpResponse, JsonResponse
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


def metrics(request):
    """Prometheus text format (D-069). Off (404) unless METRICS_TOKEN is set; then `Authorization: Bearer <token>`."""
    token = settings.METRICS_TOKEN
    if not token:
        raise Http404
    sent = request.headers.get("Authorization", "")
    if not hmac.compare_digest(sent.encode(), f"Bearer {token}".encode()):
        return HttpResponse("unauthorized\n", status=401, content_type="text/plain",
                            headers={"WWW-Authenticate": "Bearer"})
    from assist.ops import ai_snapshot, render_ai_metrics
    from backtester.engine import ENGINE_VERSION
    from backtester.ops import queue_snapshot, render_queue_metrics
    from vault_core.observability import REGISTRY
    lines = ["# HELP vault_build_info Engine version of this process.", "# TYPE vault_build_info gauge",
             f'vault_build_info{{engine_version="{ENGINE_VERSION}"}} 1']
    lines += REGISTRY.render(pid=os.getpid())
    lines += render_queue_metrics(queue_snapshot())
    lines += render_ai_metrics(ai_snapshot())
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; version=0.0.4")


urlpatterns = [
    path("health/live", live),
    path("health/ready", ready),
    path("metrics", metrics),
    path("api/auth/", include("accounts.urls")),
    path("api/assist/", include("assist.urls")),
    path("api/", include("backtester.urls")),
]

if settings.API_DOCS:
    # OpenAPI schema and Swagger UI (D-072). Assets come from drf-spectacular-sidecar, not a CDN.
    # Django serves the page's few static assets itself (insecure=True lets it do so with DEBUG off): fine for an
    # occasionally used docs page, and it avoids a CDN and a separate static-file service.
    from django.contrib.staticfiles.views import serve
    from django.urls import re_path
    from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

    urlpatterns += [
        path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
        path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
        re_path(r"^static/(?P<path>drf_spectacular_sidecar/.*)$", serve, {"insecure": True}),
    ]

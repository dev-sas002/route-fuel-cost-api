from django.urls import path

from .views import HealthAPIView, RouteAPIView

app_name = "api"

urlpatterns = [
    path("route/", RouteAPIView.as_view(), name="route"),
    path("health/", HealthAPIView.as_view(), name="health"),
]

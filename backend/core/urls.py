from django.http import JsonResponse
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("tenants", views.TenantViewSet)
router.register("users", views.UserViewSet)
router.register("data-sources", views.DataSourceViewSet)
router.register("ingestion-batches", views.IngestionBatchViewSet)
router.register("raw-emission-data", views.RawEmissionDataViewSet)
router.register("emission-factors", views.EmissionFactorViewSet)
router.register("emission-records", views.NormalizedEmissionRecordViewSet)
router.register("emission-edits", views.EmissionRecordEditViewSet)
router.register("quality-issues", views.DataQualityIssueViewSet)


def placeholder(request, **kwargs):
    return JsonResponse({"message": "Not implemented yet"}, status=501)


urlpatterns = [
    path("", include(router.urls)),
    path("ingestion/upload/", views.UploadCSVView.as_view(), name="ingestion-upload"),
    path("auth/login/", placeholder, name="auth-login"),
    path("auth/logout/", placeholder, name="auth-logout"),
    path("auth/me/", placeholder, name="auth-me"),
]

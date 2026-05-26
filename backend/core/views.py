import logging

from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .services.ingestion import IngestionService
from .services.normalization import NormalizationService
from .services.quality import QualityService

logger = logging.getLogger(__name__)

from .models import (
    DataQualityIssue,
    DataSource,
    EmissionFactor,
    EmissionRecordEdit,
    IngestionBatch,
    NormalizedEmissionRecord,
    RawEmissionData,
    Tenant,
    User,
)
from .serializers import (
    DataQualityIssueSerializer,
    DataSourceSerializer,
    EmissionFactorSerializer,
    EmissionRecordEditSerializer,
    IngestionBatchSerializer,
    NormalizedEmissionRecordSerializer,
    RawEmissionDataSerializer,
    TenantSerializer,
    UserSerializer,
)


class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["name", "slug"]
    search_fields = ["name", "slug"]


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related("tenant").all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["tenant", "role"]
    search_fields = ["username", "email", "first_name", "last_name"]

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


class DataSourceViewSet(viewsets.ModelViewSet):
    queryset = DataSource.objects.select_related("tenant").all()
    serializer_class = DataSourceSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["tenant", "source_type", "is_active"]
    search_fields = ["name"]


class IngestionBatchViewSet(viewsets.ModelViewSet):
    queryset = IngestionBatch.objects.select_related("data_source", "uploaded_by").all()
    serializer_class = IngestionBatchSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "data_source", "uploaded_by"]
    search_fields = ["file_name"]
    ordering_fields = ["uploaded_at", "status"]
    ordering = ["-uploaded_at"]


class RawEmissionDataViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = RawEmissionData.objects.select_related("ingestion_batch").all()
    serializer_class = RawEmissionDataSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["ingestion_batch", "parsing_status"]


class EmissionFactorViewSet(viewsets.ModelViewSet):
    queryset = EmissionFactor.objects.all()
    serializer_class = EmissionFactorSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["region", "source", "factor_type"]
    search_fields = ["factor_type", "region", "source"]
    ordering_fields = ["valid_from", "valid_until", "factor_value_kg_co2e"]
    ordering = ["-valid_from"]

    def get_queryset(self):
        qs = super().get_queryset()
        valid_on = self.request.query_params.get("valid_on")
        if valid_on:
            qs = qs.filter(valid_from__lte=valid_on).filter(
                valid_until__isnull=True
            ) | qs.filter(valid_from__lte=valid_on, valid_until__gte=valid_on)
        return qs


class NormalizedEmissionRecordViewSet(viewsets.ModelViewSet):
    queryset = NormalizedEmissionRecord.objects.select_related(
        "tenant", "ingestion_batch", "emission_factor", "reviewed_by", "locked_by"
    ).all()
    serializer_class = NormalizedEmissionRecordSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["tenant", "review_status", "ghg_scope", "activity_type", "is_audit_locked"]
    search_fields = ["location_name", "activity_type"]
    ordering_fields = ["activity_date", "co2e_kg", "created_at"]
    ordering = ["-activity_date"]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        date_from = params.get("activity_date_from")
        date_to = params.get("activity_date_to")
        if date_from:
            qs = qs.filter(activity_date__gte=date_from)
        if date_to:
            qs = qs.filter(activity_date__lte=date_to)
        return qs

    @action(detail=False, methods=["post"], url_path="bulk-approve")
    def bulk_approve(self, request):
        ids = request.data.get("ids", [])
        if not ids:
            return Response({"detail": "No record IDs provided."}, status=status.HTTP_400_BAD_REQUEST)

        records = NormalizedEmissionRecord.objects.filter(
            id__in=ids, is_audit_locked=False
        ).exclude(review_status=NormalizedEmissionRecord.ReviewStatus.APPROVED)

        # For AllowAny, we need to check if user exists
        user = request.user if request.user.is_authenticated else None
        
        updated = records.update(
            review_status=NormalizedEmissionRecord.ReviewStatus.APPROVED,
            reviewed_by=user,
            reviewed_at=timezone.now(),
        )
        return Response({"approved": updated}, status=status.HTTP_200_OK)


class EmissionRecordEditViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = EmissionRecordEdit.objects.select_related("record", "edited_by").all()
    serializer_class = EmissionRecordEditSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["record", "edited_by"]


class DataQualityIssueViewSet(viewsets.ModelViewSet):
    queryset = DataQualityIssue.objects.select_related("tenant", "record", "resolved_by").all()
    serializer_class = DataQualityIssueSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["severity", "issue_type", "resolved"]
    search_fields = ["description", "issue_type"]

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, pk=None):
        issue = self.get_object()
        if issue.resolved:
            return Response({"detail": "Issue is already resolved."}, status=status.HTTP_400_BAD_REQUEST)
        issue.resolved = True
        # For AllowAny, check if user is authenticated
        issue.resolved_by = request.user if request.user.is_authenticated else None
        issue.resolved_at = timezone.now()
        issue.save(update_fields=["resolved", "resolved_by", "resolved_at"])
        serializer = self.get_serializer(issue)
        return Response(serializer.data, status=status.HTTP_200_OK)


class UploadCSVView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        file = request.FILES.get("file")
        if file is None:
            return Response({"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

        if not file.name.lower().endswith(".csv"):
            return Response({"error": "File must be a CSV."}, status=status.HTTP_400_BAD_REQUEST)

        data_source_id = request.data.get("data_source_id")
        if not data_source_id:
            return Response({"error": "data_source_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            data_source = DataSource.objects.get(id=data_source_id, is_active=True)
        except DataSource.DoesNotExist:
            return Response({"error": "Data source not found or inactive."}, status=status.HTTP_404_NOT_FOUND)

        # For AllowAny, handle unauthenticated users
        user = request.user if request.user.is_authenticated else None
        
        batch = IngestionBatch.objects.create(
            tenant=data_source.tenant,
            data_source=data_source,
            file_name=file.name,
            uploaded_by=user,
            status=IngestionBatch.Status.PENDING,
        )

        try:
            success_count, error_count, parse_errors = IngestionService.parse_csv_file(
                file, data_source, batch, user
            )
        except Exception as exc:
            logger.exception("Unhandled error during CSV parsing for batch %s", batch.id)
            batch.status = IngestionBatch.Status.FAILED
            batch.error_log = [{"row": None, "errors": [str(exc)]}]
            batch.save(update_fields=["status", "error_log"])
            return Response(
                {"error": f"CSV parsing failed: {exc}", "batch_id": str(batch.id)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        normalization_errors: list[str] = []
        normalized_count = 0

        for raw_record in batch.raw_rows.filter(parsing_status="parsed").iterator(chunk_size=200):
            try:
                normalized_record, norm_errs = NormalizationService.normalize_raw_record(raw_record)
                if normalized_record:
                    QualityService.check_record_quality(normalized_record)
                    normalized_count += 1
                if norm_errs:
                    normalization_errors.append(f"Row {raw_record.row_number}: {'; '.join(norm_errs)}")
            except Exception as exc:
                logger.exception("Normalization failed for raw record %s", raw_record.id)
                normalization_errors.append(f"Row {raw_record.row_number}: normalization error — {exc}")

        batch.refresh_from_db()

        all_errors = (parse_errors + normalization_errors)[:20]

        return Response(
            {
                "batch_id": str(batch.id),
                "status": batch.status,
                "total_rows": batch.total_rows,
                "successful_rows": batch.successful_rows,
                "failed_rows": batch.failed_rows,
                "normalized_records": normalized_count,
                "errors": all_errors,
                "message": (
                    f"Successfully processed {success_count} of {batch.total_rows} rows; "
                    f"{normalized_count} emission records created."
                ),
            },
            status=status.HTTP_201_CREATED,
        )
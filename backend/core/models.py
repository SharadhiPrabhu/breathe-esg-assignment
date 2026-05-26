import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"

    def __str__(self):
        return self.name


class User(AbstractUser):
    class Role(models.TextChoices):
        ANALYST = "analyst", "Analyst"
        MANAGER = "manager", "Manager"
        AUDITOR = "auditor", "Auditor"
        ADMIN = "admin", "Admin"

    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, related_name="users", null=True, blank=True
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.ANALYST)

    class Meta(AbstractUser.Meta):
        ordering = ["username"]
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class DataSource(models.Model):
    class SourceType(models.TextChoices):
        SAP_PROCUREMENT = "sap_procurement", "SAP Procurement"
        UTILITY_ELECTRICITY = "utility_electricity", "Utility Electricity"
        CORPORATE_TRAVEL = "corporate_travel", "Corporate Travel"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="data_sources")
    source_type = models.CharField(max_length=50, choices=SourceType.choices)
    name = models.CharField(max_length=255)
    configuration = models.JSONField(default=dict, help_text="Column mappings and source-specific config")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["tenant", "name"]
        verbose_name = "Data Source"
        verbose_name_plural = "Data Sources"

    def __str__(self):
        return f"{self.name} ({self.get_source_type_display()})"


class IngestionBatch(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        PARTIAL = "partial", "Partial"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="ingestion_batches")
    data_source = models.ForeignKey(DataSource, on_delete=models.CASCADE, related_name="ingestion_batches")
    file_name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total_rows = models.IntegerField(default=0)
    processed_rows = models.IntegerField(default=0)
    successful_rows = models.IntegerField(default=0)
    failed_rows = models.IntegerField(default=0)
    error_log = models.JSONField(default=list)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="uploaded_batches"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "Ingestion Batch"
        verbose_name_plural = "Ingestion Batches"

    def __str__(self):
        return f"{self.file_name} — {self.get_status_display()}"


class RawEmissionData(models.Model):
    class ParsingStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PARSED = "parsed", "Parsed"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="raw_emission_data")
    ingestion_batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="raw_rows")
    row_number = models.IntegerField()
    raw_data = models.JSONField()
    parsing_status = models.CharField(max_length=20, choices=ParsingStatus.choices, default=ParsingStatus.PENDING)
    parsing_errors = models.JSONField(default=list)
    parsed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["ingestion_batch", "row_number"]
        verbose_name = "Raw Emission Data"
        verbose_name_plural = "Raw Emission Data"

    def __str__(self):
        return f"Batch {self.ingestion_batch_id} / Row {self.row_number}"


class EmissionFactor(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    factor_type = models.CharField(max_length=100)
    factor_value_kg_co2e = models.DecimalField(max_digits=15, decimal_places=6)
    unit = models.CharField(max_length=50)
    region = models.CharField(max_length=10)
    source = models.CharField(max_length=50)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["factor_type", "region", "-valid_from"]
        verbose_name = "Emission Factor"
        verbose_name_plural = "Emission Factors"

    def __str__(self):
        return f"{self.factor_type} / {self.region} / {self.source}"


class NormalizedEmissionRecord(models.Model):
    class GHGScope(models.IntegerChoices):
        SCOPE_1 = 1, "Scope 1"
        SCOPE_2 = 2, "Scope 2"
        SCOPE_3 = 3, "Scope 3"

    class DataQuality(models.TextChoices):
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"

    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        NEEDS_INFO = "needs_info", "Needs Info"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="emission_records")
    raw_data = models.ForeignKey(
        RawEmissionData, on_delete=models.SET_NULL, null=True, blank=True, related_name="normalized_records"
    )
    ingestion_batch = models.ForeignKey(IngestionBatch, on_delete=models.CASCADE, related_name="emission_records")

    # Activity
    activity_date = models.DateField()
    activity_end_date = models.DateField(null=True, blank=True)
    activity_type = models.CharField(max_length=100)

    # GHG classification
    ghg_scope = models.IntegerField(choices=GHGScope.choices)
    scope3_category = models.IntegerField(null=True, blank=True)

    # Quantity
    quantity_original = models.DecimalField(max_digits=15, decimal_places=4)
    unit_original = models.CharField(max_length=50)
    quantity_normalized = models.DecimalField(max_digits=15, decimal_places=4)
    unit_normalized = models.CharField(max_length=50)

    # Location
    location_name = models.CharField(max_length=255, null=True, blank=True)
    location_code = models.CharField(max_length=50, null=True, blank=True)
    country_code = models.CharField(max_length=3, null=True, blank=True)

    # Emission factor
    emission_factor = models.ForeignKey(
        EmissionFactor, on_delete=models.SET_NULL, null=True, blank=True, related_name="emission_records"
    )
    emission_factor_value = models.DecimalField(max_digits=15, decimal_places=6)
    co2e_kg = models.DecimalField(max_digits=15, decimal_places=4)

    # Metadata & quality
    metadata = models.JSONField(default=dict)
    data_quality_score = models.CharField(max_length=10, choices=DataQuality.choices, default=DataQuality.MEDIUM)
    quality_flags = models.JSONField(default=list)

    # Review workflow
    review_status = models.CharField(max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reviewed_records"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)

    # Audit lock
    is_audit_locked = models.BooleanField(default=False)
    locked_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="locked_records"
    )
    locked_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activity_date", "tenant"]
        verbose_name = "Normalized Emission Record"
        verbose_name_plural = "Normalized Emission Records"

    def __str__(self):
        return f"{self.activity_type} / {self.activity_date} / {self.co2e_kg} kg CO2e"


class EmissionRecordEdit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    record = models.ForeignKey(NormalizedEmissionRecord, on_delete=models.CASCADE, related_name="edits")
    field_name = models.CharField(max_length=100)
    old_value = models.TextField()
    new_value = models.TextField()
    edited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="emission_edits")
    edited_at = models.DateTimeField(auto_now_add=True)
    justification = models.TextField()

    class Meta:
        ordering = ["-edited_at"]
        verbose_name = "Emission Record Edit"
        verbose_name_plural = "Emission Record Edits"

    def __str__(self):
        return f"{self.record_id} / {self.field_name} @ {self.edited_at:%Y-%m-%d %H:%M}"


class DataQualityIssue(models.Model):
    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"
        CRITICAL = "critical", "Critical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="quality_issues")
    record = models.ForeignKey(
        NormalizedEmissionRecord, on_delete=models.CASCADE, null=True, blank=True, related_name="quality_issues"
    )
    issue_type = models.CharField(max_length=100)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    description = models.TextField()
    auto_detected = models.BooleanField(default=True)
    resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="resolved_issues"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "severity"]
        verbose_name = "Data Quality Issue"
        verbose_name_plural = "Data Quality Issues"

    def __str__(self):
        return f"{self.get_severity_display()} / {self.issue_type}"

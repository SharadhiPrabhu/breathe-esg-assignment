from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

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


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = BaseUserAdmin.list_display + ("tenant", "role")
    list_filter = BaseUserAdmin.list_filter + ("role", "tenant")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Organisation", {"fields": ("tenant", "role")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Organisation", {"fields": ("tenant", "role")}),
    )


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "source_type", "tenant", "is_active", "created_at")
    list_filter = ("source_type", "is_active")
    search_fields = ("name",)


@admin.register(IngestionBatch)
class IngestionBatchAdmin(admin.ModelAdmin):
    list_display = ("file_name", "data_source", "status", "total_rows", "successful_rows", "failed_rows", "uploaded_at")
    list_filter = ("status", "data_source")
    search_fields = ("file_name",)


@admin.register(RawEmissionData)
class RawEmissionDataAdmin(admin.ModelAdmin):
    list_display = ("ingestion_batch", "row_number", "parsing_status", "parsed_at")
    list_filter = ("parsing_status",)


@admin.register(EmissionFactor)
class EmissionFactorAdmin(admin.ModelAdmin):
    list_display = ("factor_type", "factor_value_kg_co2e", "unit", "region", "source", "valid_from", "valid_until")
    list_filter = ("region", "source")
    search_fields = ("factor_type",)


@admin.register(NormalizedEmissionRecord)
class NormalizedEmissionRecordAdmin(admin.ModelAdmin):
    list_display = (
        "activity_date",
        "activity_type",
        "ghg_scope",
        "quantity_normalized",
        "unit_normalized",
        "co2e_kg",
        "review_status",
        "is_audit_locked",
    )
    list_filter = ("review_status", "ghg_scope", "data_quality_score", "is_audit_locked")
    search_fields = ("location_name", "activity_type")
    readonly_fields = ("is_audit_locked", "locked_at", "locked_by")


@admin.register(EmissionRecordEdit)
class EmissionRecordEditAdmin(admin.ModelAdmin):
    list_display = ("record", "field_name", "old_value", "new_value", "edited_by", "edited_at")
    list_filter = ("field_name", "edited_by")
    readonly_fields = ("record", "field_name", "old_value", "new_value", "edited_by", "edited_at", "justification")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(DataQualityIssue)
class DataQualityIssueAdmin(admin.ModelAdmin):
    list_display = ("issue_type", "severity", "record", "resolved", "created_at")
    list_filter = ("severity", "issue_type", "resolved")
    search_fields = ("description",)

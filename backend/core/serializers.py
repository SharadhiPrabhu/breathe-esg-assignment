from rest_framework import serializers

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


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = "__all__"


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "tenant", "role", "date_joined", "password")
        read_only_fields = ("id", "date_joined")

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = super().create(validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)
        if password:
            user.set_password(password)
            user.save()
        return user


class DataSourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSource
        fields = "__all__"


class IngestionBatchSerializer(serializers.ModelSerializer):
    data_source_name = serializers.CharField(source="data_source.name", read_only=True)
    uploaded_by_username = serializers.CharField(source="uploaded_by.username", read_only=True)

    class Meta:
        model = IngestionBatch
        fields = "__all__"


class RawEmissionDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = RawEmissionData
        fields = "__all__"


class EmissionFactorSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmissionFactor
        fields = "__all__"


class NormalizedEmissionRecordSerializer(serializers.ModelSerializer):
    ingestion_batch_file_name = serializers.CharField(source="ingestion_batch.file_name", read_only=True)
    emission_factor_details = EmissionFactorSerializer(source="emission_factor", read_only=True)
    reviewed_by_username = serializers.CharField(source="reviewed_by.username", read_only=True)
    locked_by_username = serializers.CharField(source="locked_by.username", read_only=True)

    class Meta:
        model = NormalizedEmissionRecord
        fields = "__all__"

    def validate(self, attrs):
        scope = attrs.get("ghg_scope", getattr(self.instance, "ghg_scope", None))
        scope3_category = attrs.get("scope3_category", getattr(self.instance, "scope3_category", None))
        if scope == 3 and scope3_category is not None and not (1 <= scope3_category <= 15):
            raise serializers.ValidationError({"scope3_category": "Must be between 1 and 15 for Scope 3 records."})
        if scope != 3 and scope3_category is not None:
            raise serializers.ValidationError({"scope3_category": "Only valid for Scope 3 records."})
        return attrs

    def validate_is_audit_locked(self, value):
        if self.instance and self.instance.is_audit_locked and not value:
            raise serializers.ValidationError("Audit-locked records cannot be unlocked via the API.")
        return value


class EmissionRecordEditSerializer(serializers.ModelSerializer):
    edited_by_username = serializers.CharField(source="edited_by.username", read_only=True)

    class Meta:
        model = EmissionRecordEdit
        fields = "__all__"
        read_only_fields = ("id", "record", "field_name", "old_value", "new_value", "edited_by", "edited_at", "justification")


class DataQualityIssueSerializer(serializers.ModelSerializer):
    record_details = serializers.SerializerMethodField(read_only=True)
    resolved_by_username = serializers.CharField(source="resolved_by.username", read_only=True)

    class Meta:
        model = DataQualityIssue
        fields = "__all__"

    def get_record_details(self, obj):
        if obj.record is None:
            return None
        return {
            "id": obj.record.id,
            "activity_type": obj.record.activity_type,
            "activity_date": obj.record.activity_date,
            "co2e_kg": obj.record.co2e_kg,
            "review_status": obj.record.review_status,
        }

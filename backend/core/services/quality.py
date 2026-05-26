import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import Avg, Q
from django.utils import timezone

from ..models import DataQualityIssue, NormalizedEmissionRecord, Tenant

logger = logging.getLogger(__name__)


class QualityService:
    # Issue type constants
    QUANTITY_ANOMALY = "quantity_anomaly"
    QUANTITY_ZERO = "quantity_zero"
    DATE_FUTURE = "date_future"
    DATE_TOO_OLD = "date_too_old"
    DATE_END_BEFORE_START = "date_end_before_start"
    MISSING_FACTOR = "missing_emission_factor"
    STALE_FACTOR = "stale_emission_factor"
    MISSING_LOCATION = "missing_location"
    MISSING_COUNTRY = "missing_country"
    DUPLICATE_SUSPECTED = "duplicate_suspected"

    # Thresholds
    ANOMALY_HIGH_MULTIPLIER = Decimal("3.0")
    ANOMALY_LOW_MULTIPLIER = Decimal("0.3")
    ANOMALY_MIN_SAMPLE = 5          # don't flag anomalies without enough history
    DATE_MAX_AGE_YEARS = 5
    FACTOR_MAX_AGE_YEARS = 3
    DUPLICATE_QUANTITY_TOLERANCE = Decimal("0.05")   # 5%
    DUPLICATE_DATE_WINDOW_DAYS = 1

    @staticmethod
    def check_record_quality(emission_record: NormalizedEmissionRecord) -> list[DataQualityIssue]:
        """Run all quality checks and persist DataQualityIssue records. Returns the full list."""
        all_issues: list[DataQualityIssue] = []
        tenant = emission_record.tenant

        checkers = [
            lambda: QualityService.check_date_issues(emission_record),
            lambda: QualityService.check_emission_factor_issues(emission_record),
            lambda: QualityService.check_location_issues(emission_record),
            lambda: QualityService.check_quantity_anomalies(emission_record, tenant),
            lambda: QualityService.check_duplicates(emission_record, tenant),
        ]

        for checker in checkers:
            try:
                all_issues.extend(checker())
            except Exception:
                logger.exception("Quality checker failed for record %s", emission_record.id)

        flags = [i.issue_type for i in all_issues]
        emission_record.quality_flags = flags

        if all_issues:
            severities = {i.severity for i in all_issues}
            if DataQualityIssue.Severity.CRITICAL in severities:
                score = NormalizedEmissionRecord.DataQuality.LOW
            elif DataQualityIssue.Severity.ERROR in severities:
                score = NormalizedEmissionRecord.DataQuality.LOW
            elif DataQualityIssue.Severity.WARNING in severities:
                score = NormalizedEmissionRecord.DataQuality.MEDIUM
            else:
                score = emission_record.data_quality_score  # keep existing if only INFO
        else:
            score = NormalizedEmissionRecord.DataQuality.HIGH

        emission_record.data_quality_score = score
        emission_record.save(update_fields=["quality_flags", "data_quality_score"])

        logger.debug("Record %s: %d quality issue(s) found.", emission_record.id, len(all_issues))
        return all_issues

    @staticmethod
    def check_quantity_anomalies(
        record: NormalizedEmissionRecord, tenant: Tenant
    ) -> list[DataQualityIssue]:
        issues: list[DataQualityIssue] = []

        if record.quantity_normalized == Decimal("0"):
            issues.append(_create_issue(
                tenant=tenant,
                record=record,
                issue_type=QualityService.QUANTITY_ZERO,
                severity=DataQualityIssue.Severity.WARNING,
                description="Quantity is zero. Verify this is intentional.",
            ))
            return issues

        result = (
            NormalizedEmissionRecord.objects
            .filter(
                tenant=tenant,
                activity_type=record.activity_type,
                unit_normalized=record.unit_normalized,
            )
            .exclude(id=record.id)
            .aggregate(avg=Avg("quantity_normalized"), count=Avg("id"))
        )

        # Use a count query separately — aggregate count of records
        from django.db.models import Count  # local import to avoid circular at module level
        count_result = (
            NormalizedEmissionRecord.objects
            .filter(
                tenant=tenant,
                activity_type=record.activity_type,
                unit_normalized=record.unit_normalized,
            )
            .exclude(id=record.id)
            .aggregate(count=Count("id"), avg=Avg("quantity_normalized"))
        )

        count = count_result.get("count") or 0
        avg = count_result.get("avg")

        if count < QualityService.ANOMALY_MIN_SAMPLE or avg is None or avg == 0:
            return issues

        avg = Decimal(str(avg))
        ratio = record.quantity_normalized / avg

        if ratio > QualityService.ANOMALY_HIGH_MULTIPLIER:
            issues.append(_create_issue(
                tenant=tenant,
                record=record,
                issue_type=QualityService.QUANTITY_ANOMALY,
                severity=DataQualityIssue.Severity.WARNING,
                description=(
                    f"Quantity {record.quantity_normalized} {record.unit_normalized} is "
                    f"{ratio:.1f}x the tenant average of {avg:.2f} for '{record.activity_type}'. "
                    "Possible data entry error."
                ),
            ))
        elif ratio < QualityService.ANOMALY_LOW_MULTIPLIER:
            issues.append(_create_issue(
                tenant=tenant,
                record=record,
                issue_type=QualityService.QUANTITY_ANOMALY,
                severity=DataQualityIssue.Severity.WARNING,
                description=(
                    f"Quantity {record.quantity_normalized} {record.unit_normalized} is only "
                    f"{ratio:.1%} of the tenant average of {avg:.2f} for '{record.activity_type}'. "
                    "Possible data entry error."
                ),
            ))

        return issues

    @staticmethod
    def check_date_issues(record: NormalizedEmissionRecord) -> list[DataQualityIssue]:
        issues: list[DataQualityIssue] = []
        today = timezone.now().date()
        tenant = record.tenant

        if record.activity_date > today:
            issues.append(_create_issue(
                tenant=tenant,
                record=record,
                issue_type=QualityService.DATE_FUTURE,
                severity=DataQualityIssue.Severity.ERROR,
                description=(
                    f"Activity date {record.activity_date} is in the future "
                    f"({(record.activity_date - today).days} days ahead)."
                ),
            ))

        cutoff = today - timedelta(days=365 * QualityService.DATE_MAX_AGE_YEARS)
        if record.activity_date < cutoff:
            issues.append(_create_issue(
                tenant=tenant,
                record=record,
                issue_type=QualityService.DATE_TOO_OLD,
                severity=DataQualityIssue.Severity.INFO,
                description=(
                    f"Activity date {record.activity_date} is more than "
                    f"{QualityService.DATE_MAX_AGE_YEARS} years old. Verify this is not a data entry error."
                ),
            ))

        if record.activity_end_date and record.activity_end_date < record.activity_date:
            issues.append(_create_issue(
                tenant=tenant,
                record=record,
                issue_type=QualityService.DATE_END_BEFORE_START,
                severity=DataQualityIssue.Severity.ERROR,
                description=(
                    f"activity_end_date {record.activity_end_date} is before "
                    f"activity_date {record.activity_date}."
                ),
            ))

        return issues

    @staticmethod
    def check_emission_factor_issues(record: NormalizedEmissionRecord) -> list[DataQualityIssue]:
        issues: list[DataQualityIssue] = []
        tenant = record.tenant
        today = timezone.now().date()

        if record.emission_factor is None:
            issues.append(_create_issue(
                tenant=tenant,
                record=record,
                issue_type=QualityService.MISSING_FACTOR,
                severity=DataQualityIssue.Severity.ERROR,
                description=(
                    f"No emission factor found for activity_type='{record.activity_type}', "
                    f"unit='{record.unit_normalized}'. CO2e value is estimated as zero."
                ),
            ))
            return issues

        factor_age_cutoff = today - timedelta(days=365 * QualityService.FACTOR_MAX_AGE_YEARS)
        if record.emission_factor.valid_from < factor_age_cutoff:
            issues.append(_create_issue(
                tenant=tenant,
                record=record,
                issue_type=QualityService.STALE_FACTOR,
                severity=DataQualityIssue.Severity.WARNING,
                description=(
                    f"Emission factor '{record.emission_factor.factor_type}' "
                    f"(source: {record.emission_factor.source}) is from "
                    f"{record.emission_factor.valid_from}. Consider updating to a more recent factor."
                ),
            ))

        return issues

    @staticmethod
    def check_location_issues(record: NormalizedEmissionRecord) -> list[DataQualityIssue]:
        issues: list[DataQualityIssue] = []
        tenant = record.tenant

        is_travel = record.ghg_scope == 3 and record.activity_type.startswith(("flight_", "travel_"))

        if is_travel and not record.location_name:
            issues.append(_create_issue(
                tenant=tenant,
                record=record,
                issue_type=QualityService.MISSING_LOCATION,
                severity=DataQualityIssue.Severity.WARNING,
                description="Travel record is missing location name (origin/destination).",
            ))

        if not record.country_code:
            issues.append(_create_issue(
                tenant=tenant,
                record=record,
                issue_type=QualityService.MISSING_COUNTRY,
                severity=DataQualityIssue.Severity.INFO,
                description=(
                    "Country code is missing. Regional emission factor selection may be less accurate."
                ),
            ))

        return issues

    @staticmethod
    def check_duplicates(
        record: NormalizedEmissionRecord, tenant: Tenant
    ) -> list[DataQualityIssue]:
        issues: list[DataQualityIssue] = []

        tolerance = record.quantity_normalized * QualityService.DUPLICATE_QUANTITY_TOLERANCE
        date_window = timedelta(days=QualityService.DUPLICATE_DATE_WINDOW_DAYS)

        duplicate_qs = (
            NormalizedEmissionRecord.objects
            .filter(
                tenant=tenant,
                activity_type=record.activity_type,
                activity_date__range=(
                    record.activity_date - date_window,
                    record.activity_date + date_window,
                ),
                quantity_normalized__range=(
                    record.quantity_normalized - tolerance,
                    record.quantity_normalized + tolerance,
                ),
            )
            .exclude(id=record.id)
        )

        duplicate = duplicate_qs.first()
        if duplicate:
            issues.append(_create_issue(
                tenant=tenant,
                record=record,
                issue_type=QualityService.DUPLICATE_SUSPECTED,
                severity=DataQualityIssue.Severity.WARNING,
                description=(
                    f"Possible duplicate of record {duplicate.id} "
                    f"(same activity_type, date within {QualityService.DUPLICATE_DATE_WINDOW_DAYS}d, "
                    f"quantity within {int(QualityService.DUPLICATE_QUANTITY_TOLERANCE * 100)}%)."
                ),
            ))

        return issues

    @staticmethod
    def batch_quality_check(
        tenant: Tenant,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """
        Run quality checks across all emission records for a tenant in the given date range.

        Returns a summary dict with counts per severity.
        """
        qs = NormalizedEmissionRecord.objects.filter(tenant=tenant)
        if start_date:
            qs = qs.filter(activity_date__gte=start_date)
        if end_date:
            qs = qs.filter(activity_date__lte=end_date)

        total = qs.count()
        summary: dict = {
            "total_records": total,
            "records_checked": 0,
            "issues_created": 0,
            DataQualityIssue.Severity.INFO: 0,
            DataQualityIssue.Severity.WARNING: 0,
            DataQualityIssue.Severity.ERROR: 0,
            DataQualityIssue.Severity.CRITICAL: 0,
        }

        for record in qs.iterator(chunk_size=200):
            try:
                issues = QualityService.check_record_quality(record)
                summary["records_checked"] += 1
                summary["issues_created"] += len(issues)
                for issue in issues:
                    summary[issue.severity] += 1
            except Exception:
                logger.exception("batch_quality_check failed on record %s", record.id)

        logger.info(
            "batch_quality_check tenant=%s: %d/%d records checked, %d issues",
            tenant.id, summary["records_checked"], total, summary["issues_created"],
        )
        return summary


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _create_issue(
    tenant: Tenant,
    record: NormalizedEmissionRecord,
    issue_type: str,
    severity: str,
    description: str,
) -> DataQualityIssue:
    issue = DataQualityIssue.objects.create(
        tenant=tenant,
        record=record,
        issue_type=issue_type,
        severity=severity,
        description=description,
        auto_detected=True,
        resolved=False,
    )
    logger.debug("Created %s issue '%s' for record %s", severity, issue_type, record.id)
    return issue

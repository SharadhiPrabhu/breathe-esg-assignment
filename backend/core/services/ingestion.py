import io
import logging
from datetime import datetime
from typing import Optional

import pandas as pd
from django.db import transaction
from django.utils import timezone

from ..models import IngestionBatch, RawEmissionData

logger = logging.getLogger(__name__)

# Required columns per source type
REQUIRED_COLUMNS = {
    "sap_procurement": ["Material", "Quantity", "Unit", "Posting Date"],
    "utility_electricity": ["Meter", "Account Number", "Bill Period", "kWh", "Site", "Country"],
    "corporate_travel": ["Date", "Employee", "From", "To", "Distance", "Mode"],
}

# Signature headers used for auto-detection
SOURCE_SIGNATURES = {
    "sap_procurement": {"material", "quantity", "unit", "posting date"},
    "utility_electricity": {"meter", "account number", "bill period", "kwh", "site", "country"},
    "corporate_travel": {"date", "employee", "from", "to", "distance", "mode"},
}


class IngestionService:

    @staticmethod
    def detect_source_type(file_content: str) -> Optional[str]:
        """Return the source type key whose signature best matches the CSV headers."""
        try:
            sample = pd.read_csv(io.StringIO(file_content), nrows=0)
        except Exception:
            return None

        headers = {col.strip().lower() for col in sample.columns}

        best_match = None
        best_score = 0
        for source_type, signature in SOURCE_SIGNATURES.items():
            score = len(signature & headers)
            if score > best_score:
                best_score = score
                best_match = source_type

        # Require at least half the signature columns to match
        min_required = len(SOURCE_SIGNATURES[best_match]) // 2 if best_match else 1
        return best_match if best_score >= min_required else None

    @staticmethod
    @transaction.atomic
    def parse_csv_file(file, data_source, ingestion_batch: IngestionBatch, user):
        """
        Parse an uploaded CSV file into RawEmissionData rows.

        Returns (success_count, error_count, errors_list).
        Rolls back all row inserts if an unexpected exception occurs.
        """
        source_type = data_source.source_type
        errors_list = []
        success_count = 0
        error_count = 0

        ingestion_batch.status = IngestionBatch.Status.PROCESSING
        ingestion_batch.processing_started_at = timezone.now()
        ingestion_batch.save(update_fields=["status", "processing_started_at"])

        try:
            content = file.read()
            if isinstance(content, bytes):
                content = content.decode("utf-8-sig")  # handle BOM-prefixed files

            df = pd.read_csv(io.StringIO(content), dtype=str, keep_default_na=False)
            df.columns = df.columns.str.strip()

        except Exception as exc:
            logger.exception("Failed to read CSV for batch %s", ingestion_batch.id)
            ingestion_batch.status = IngestionBatch.Status.FAILED
            ingestion_batch.error_log = [{"row": None, "errors": [str(exc)]}]
            ingestion_batch.processing_completed_at = timezone.now()
            ingestion_batch.save(update_fields=["status", "error_log", "processing_completed_at"])
            return 0, 0, [str(exc)]

        # Validate that required columns are present
        required = REQUIRED_COLUMNS.get(source_type, [])
        missing = [col for col in required if col not in df.columns]
        if missing:
            msg = f"Missing required columns: {', '.join(missing)}"
            logger.warning("Batch %s: %s", ingestion_batch.id, msg)
            ingestion_batch.status = IngestionBatch.Status.FAILED
            ingestion_batch.error_log = [{"row": None, "errors": [msg]}]
            ingestion_batch.processing_completed_at = timezone.now()
            ingestion_batch.save(update_fields=["status", "error_log", "processing_completed_at"])
            return 0, 0, [msg]

        total_rows = len(df)
        ingestion_batch.total_rows = total_rows
        ingestion_batch.save(update_fields=["total_rows"])

        raw_records = []
        for idx, row in df.iterrows():
            row_number = idx + 2  # 1-based, +1 for header row
            row_dict = row.to_dict()

            is_valid, row_errors = IngestionService.validate_row(row_dict, source_type)

            raw_records.append(
                RawEmissionData(
                    tenant=data_source.tenant,
                    ingestion_batch=ingestion_batch,
                    row_number=row_number,
                    raw_data=row_dict,
                    parsing_status=RawEmissionData.ParsingStatus.PARSED if is_valid else RawEmissionData.ParsingStatus.FAILED,
                    parsing_errors=row_errors,
                    parsed_at=timezone.now() if is_valid else None,
                )
            )

            if is_valid:
                success_count += 1
            else:
                error_count += 1
                errors_list.append({"row": row_number, "errors": row_errors})
                logger.debug("Batch %s row %d validation errors: %s", ingestion_batch.id, row_number, row_errors)

        RawEmissionData.objects.bulk_create(raw_records, batch_size=500)

        if error_count == 0:
            final_status = IngestionBatch.Status.COMPLETED
        elif success_count == 0:
            final_status = IngestionBatch.Status.FAILED
        else:
            final_status = IngestionBatch.Status.PARTIAL

        ingestion_batch.status = final_status
        ingestion_batch.processed_rows = total_rows
        ingestion_batch.successful_rows = success_count
        ingestion_batch.failed_rows = error_count
        ingestion_batch.error_log = errors_list
        ingestion_batch.processing_completed_at = timezone.now()
        ingestion_batch.save(update_fields=[
            "status", "processed_rows", "successful_rows",
            "failed_rows", "error_log", "processing_completed_at",
        ])

        logger.info(
            "Batch %s complete: %d/%d rows parsed, %d errors (status=%s)",
            ingestion_batch.id, success_count, total_rows, error_count, final_status,
        )
        return success_count, error_count, errors_list

    @staticmethod
    def validate_row(row: dict, source_type: str) -> tuple[bool, list[str]]:
        """
        Validate a single CSV row dict against source-type rules.

        Returns (is_valid, errors_list).
        """
        errors = []

        validators = {
            "sap_procurement": _validate_sap_row,
            "utility_electricity": _validate_utility_row,
            "corporate_travel": _validate_travel_row,
        }
        validator = validators.get(source_type)
        if validator:
            errors.extend(validator(row))

        return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# Per-source validators
# ---------------------------------------------------------------------------

def _require_non_empty(row: dict, fields: list[str], errors: list[str]) -> None:
    for field in fields:
        if not str(row.get(field, "")).strip():
            errors.append(f"'{field}' is required and must not be empty.")


def _validate_date(value: str, field_name: str, errors: list[str], fmt: str = "%Y-%m-%d") -> None:
    if not value or not value.strip():
        return  # presence check handled separately
    for date_fmt in (fmt, "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            datetime.strptime(value.strip(), date_fmt)
            return
        except ValueError:
            continue
    errors.append(f"'{field_name}' value '{value}' is not a recognised date format.")


def _validate_positive_number(value: str, field_name: str, errors: list[str]) -> None:
    if not value or not value.strip():
        return
    try:
        num = float(value.strip().replace(",", ""))
        if num < 0:
            errors.append(f"'{field_name}' must be a positive number, got {value!r}.")
    except ValueError:
        errors.append(f"'{field_name}' must be numeric, got {value!r}.")


def _validate_sap_row(row: dict) -> list[str]:
    errors: list[str] = []
    _require_non_empty(row, ["Material", "Quantity", "Unit", "Posting Date"], errors)
    _validate_date(row.get("Posting Date", ""), "Posting Date", errors)
    _validate_positive_number(row.get("Quantity", ""), "Quantity", errors)
    return errors


def _validate_utility_row(row: dict) -> list[str]:
    errors: list[str] = []
    _require_non_empty(row, ["Meter", "Account Number", "Bill Period", "kWh", "Site", "Country"], errors)
    _validate_positive_number(row.get("kWh", ""), "kWh", errors)

    bill_period = row.get("Bill Period", "").strip()
    if bill_period:
        # Accept "YYYY-MM" or "MM/YYYY"
        valid = False
        for fmt in ("%Y-%m", "%m/%Y"):
            try:
                datetime.strptime(bill_period, fmt)
                valid = True
                break
            except ValueError:
                continue
        if not valid:
            errors.append(f"'Bill Period' value '{bill_period}' must be YYYY-MM or MM/YYYY.")

    return errors


def _validate_travel_row(row: dict) -> list[str]:
    errors: list[str] = []
    _require_non_empty(row, ["Date", "Employee", "From", "To", "Distance", "Mode"], errors)
    _validate_date(row.get("Date", ""), "Date", errors)
    _validate_positive_number(row.get("Distance", ""), "Distance", errors)

    mode = row.get("Mode", "").strip().lower()
    valid_modes = {"flight", "rail", "car", "bus", "ferry", "taxi"}
    if mode and mode not in valid_modes:
        errors.append(f"'Mode' value '{mode}' is not recognised. Expected one of: {', '.join(sorted(valid_modes))}.")

    flight_class = row.get("Flight Class", "").strip().lower()
    if flight_class:
        valid_classes = {"economy", "premium economy", "business", "first"}
        if flight_class not in valid_classes:
            errors.append(f"'Flight Class' value '{flight_class}' is not recognised.")

    return errors

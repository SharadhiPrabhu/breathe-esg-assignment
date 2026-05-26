import logging
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Optional, Tuple

from django.db import transaction
from django.utils import timezone

from ..models import EmissionFactor, NormalizedEmissionRecord, RawEmissionData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Unit conversion tables
# All values convert TO the canonical unit for each category.
# ---------------------------------------------------------------------------

UNIT_CONVERSIONS: dict[str, dict[str, Decimal]] = {
    # Volume → liters
    "gallon": Decimal("3.78541"),
    "gallons": Decimal("3.78541"),
    "gal": Decimal("3.78541"),
    "m3": Decimal("1000"),
    "cubic_meter": Decimal("1000"),
    "litre": Decimal("1"),
    "liter": Decimal("1"),
    "l": Decimal("1"),
    # Energy → kWh
    "mwh": Decimal("1000"),
    "kwh": Decimal("1"),
    "gj": Decimal("277.778"),
    "mj": Decimal("0.277778"),
    # Distance → km
    "mile": Decimal("1.60934"),
    "miles": Decimal("1.60934"),
    "mi": Decimal("1.60934"),
    "km": Decimal("1"),
    "kilometer": Decimal("1"),
    "kilometre": Decimal("1"),
    # Mass → kg
    "tonne": Decimal("1000"),
    "tonnes": Decimal("1000"),
    "t": Decimal("1000"),
    "metric_ton": Decimal("1000"),
    "lb": Decimal("0.453592"),
    "lbs": Decimal("0.453592"),
    "pound": Decimal("0.453592"),
    "kg": Decimal("1"),
    "kilogram": Decimal("1"),
}

# Canonical (normalised) unit per source type
CANONICAL_UNITS = {
    "sap_procurement": "liter",
    "utility_electricity": "kWh",
    "corporate_travel": "km",
}

# Scope classification rules
SCOPE_MAP: dict[str, Tuple[int, Optional[int]]] = {
    "sap_procurement": (1, None),
    "utility_electricity": (2, None),
    "corporate_travel": (3, 6),   # GHG Protocol category 6 – business travel
}


class NormalizationService:

    @staticmethod
    @transaction.atomic
    def normalize_raw_record(raw_record: RawEmissionData) -> Tuple[Optional[NormalizedEmissionRecord], list[str]]:
        """
        Normalise a single RawEmissionData row into a NormalizedEmissionRecord.

        Returns (record, errors). On partial success the record is still saved
        with a LOW quality score and the errors captured in quality_flags.
        """
        errors: list[str] = []
        source_type = raw_record.ingestion_batch.data_source.source_type
        raw = raw_record.raw_data

        # --- parse source-specific fields ---
        try:
            parsed = _PARSERS[source_type](raw)
        except KeyError:
            errors.append(f"No parser for source type '{source_type}'.")
            _mark_failed(raw_record, errors)
            return None, errors
        except Exception as exc:
            errors.append(f"Parsing error: {exc}")
            _mark_failed(raw_record, errors)
            return None, errors

        errors.extend(parsed.get("errors", []))

        # --- unit conversion ---
        canonical_unit = CANONICAL_UNITS.get(source_type, parsed.get("unit", ""))
        try:
            qty_normalized = NormalizationService.convert_units(
                parsed["quantity"], parsed.get("unit", canonical_unit), canonical_unit
            )
        except (ValueError, InvalidOperation) as exc:
            errors.append(str(exc))
            qty_normalized = parsed.get("quantity", Decimal("0"))

        # --- emission factor lookup ---
        activity_date: Optional[date] = parsed.get("activity_date")
        emission_factor = NormalizationService.find_emission_factor(
            activity_type=parsed.get("activity_type", ""),
            unit=canonical_unit,
            region=parsed.get("country_code", "GLOBAL"),
            date=activity_date,
        )
        if emission_factor is None:
            errors.append(
                f"No emission factor found for activity_type='{parsed.get('activity_type')}' "
                f"unit='{canonical_unit}' on {activity_date}."
            )
            factor_value = Decimal("0")
        else:
            factor_value = emission_factor.factor_value_kg_co2e

        co2e_kg = (qty_normalized * factor_value).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

        # --- scope classification ---
        ghg_scope, scope3_category = NormalizationService.classify_ghg_scope(
            parsed.get("activity_type", ""), source_type
        )

        record = NormalizedEmissionRecord(
            tenant=raw_record.tenant,
            raw_data=raw_record,
            ingestion_batch=raw_record.ingestion_batch,
            activity_date=activity_date or timezone.now().date(),
            activity_end_date=parsed.get("activity_end_date"),
            activity_type=parsed.get("activity_type", ""),
            ghg_scope=ghg_scope,
            scope3_category=scope3_category,
            quantity_original=parsed.get("quantity", Decimal("0")),
            unit_original=parsed.get("unit", ""),
            quantity_normalized=qty_normalized,
            unit_normalized=canonical_unit,
            location_name=parsed.get("location_name"),
            location_code=parsed.get("location_code"),
            country_code=parsed.get("country_code"),
            emission_factor=emission_factor,
            emission_factor_value=factor_value,
            co2e_kg=co2e_kg,
            metadata=parsed.get("metadata", {}),
            quality_flags=errors,
            review_status=NormalizedEmissionRecord.ReviewStatus.PENDING,
        )

        record.data_quality_score = NormalizationService.calculate_data_quality_score(record, raw)
        record.save()

        raw_record.parsing_status = RawEmissionData.ParsingStatus.PARSED
        raw_record.parsed_at = timezone.now()
        raw_record.save(update_fields=["parsing_status", "parsed_at"])

        logger.info("Normalised raw record %s → emission record %s", raw_record.id, record.id)
        return record, errors

    @staticmethod
    def convert_units(quantity, from_unit: str, to_unit: str) -> Decimal:
        """
        Convert quantity from from_unit to to_unit.

        Both units must belong to the same physical dimension
        (both volume, both energy, etc.). Raises ValueError if unknown.
        """
        qty = Decimal(str(quantity))
        from_key = from_unit.strip().lower()
        to_key = to_unit.strip().lower()

        if from_key == to_key:
            return qty

        from_factor = UNIT_CONVERSIONS.get(from_key)
        to_factor = UNIT_CONVERSIONS.get(to_key)

        if from_factor is None:
            raise ValueError(f"Unknown unit '{from_unit}'.")
        if to_factor is None:
            raise ValueError(f"Unknown unit '{to_unit}'.")

        # Convert: qty × (from→canonical) ÷ (to→canonical)
        return (qty * from_factor / to_factor).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def find_emission_factor(
        activity_type: str,
        unit: str,
        region: str = "GLOBAL",
        date: Optional[date] = None,
    ) -> Optional[EmissionFactor]:
        """
        Look up the best matching EmissionFactor.

        Prefers regional match over GLOBAL fallback.
        Filters to factors valid on `date` when provided.
        """
        qs = EmissionFactor.objects.filter(
            factor_type__iexact=activity_type,
            unit__iexact=unit,
        )
        if date:
            qs = qs.filter(valid_from__lte=date).filter(
                valid_until__isnull=True
            ) | EmissionFactor.objects.filter(
                factor_type__iexact=activity_type,
                unit__iexact=unit,
                valid_from__lte=date,
                valid_until__gte=date,
            )

        # Try regional first, fall back to GLOBAL
        regional = qs.filter(region__iexact=region).order_by("-valid_from").first()
        if regional:
            return regional

        if region != "GLOBAL":
            return qs.filter(region__iexact="GLOBAL").order_by("-valid_from").first()

        return None

    @staticmethod
    def classify_ghg_scope(activity_type: str, source_type: str) -> Tuple[int, Optional[int]]:
        """Return (ghg_scope, scope3_category) for the given source type."""
        return SCOPE_MAP.get(source_type, (3, None))

    @staticmethod
    def calculate_data_quality_score(
        record: NormalizedEmissionRecord, raw: dict
    ) -> str:
        """
        Score quality as 'high', 'medium', or 'low'.

        Penalty points are accumulated; final band determined by total.
        """
        penalties = 0

        if record.emission_factor is None:
            penalties += 3

        if not record.activity_date:
            penalties += 2

        missing_location = not record.location_name and not record.country_code
        if missing_location:
            penalties += 1

        if record.quantity_original == Decimal("0"):
            penalties += 2

        if record.quality_flags:
            penalties += len(record.quality_flags)

        # Stale data (> 2 years old)
        if record.activity_date:
            age_days = (timezone.now().date() - record.activity_date).days
            if age_days > 730:
                penalties += 1

        if penalties == 0:
            return NormalizedEmissionRecord.DataQuality.HIGH
        if penalties <= 3:
            return NormalizedEmissionRecord.DataQuality.MEDIUM
        return NormalizedEmissionRecord.DataQuality.LOW


# ---------------------------------------------------------------------------
# Source-specific row parsers
# Each returns a dict with normalised keys plus an 'errors' list.
# ---------------------------------------------------------------------------

def _parse_date(value: str, field: str) -> Tuple[Optional[date], list[str]]:
    if not value or not value.strip():
        return None, [f"'{field}' is missing."]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date(), []
        except ValueError:
            continue
    return None, [f"'{field}' value '{value}' is not a recognised date format."]


def _parse_decimal(value: str, field: str) -> tuple[Decimal, list[str]]:
    try:
        return Decimal(str(value).strip().replace(",", "")), []
    except InvalidOperation:
        return Decimal("0"), [f"'{field}' value '{value}' is not numeric."]


def _classify_sap_material(description: str) -> str:
    desc = description.lower()
    if "diesel" in desc:
        return "fuel_diesel_combustion"
    if "petrol" in desc or "gasoline" in desc:
        return "fuel_petrol_combustion"
    if "natural gas" in desc or "gas" in desc:
        return "fuel_natural_gas_combustion"
    return f"fuel_purchase_{description.lower().replace(' ', '_')}"


def _parse_sap_row(raw: dict) -> dict:
    errors: list[str] = []

    quantity, errs = _parse_decimal(raw.get("Quantity", ""), "Quantity")
    errors.extend(errs)

    activity_date, errs = _parse_date(raw.get("Posting Date", ""), "Posting Date")
    errors.extend(errs)

    material_desc = raw.get("Material Description") or raw.get("Material", "unknown")

    return {
        "activity_type": _classify_sap_material(material_desc),
        "quantity": quantity,
        "unit": raw.get("Unit", "liter").strip().lower(),
        "activity_date": activity_date,
        "location_name": raw.get("Plant") or raw.get("Location"),
        "location_code": raw.get("Plant Code") or raw.get("Cost Center"),
        "country_code": raw.get("Country"),
        "metadata": {k: v for k, v in raw.items() if k not in ("Quantity", "Unit", "Posting Date", "Material")},
        "errors": errors,
    }


def _parse_utility_row(raw: dict) -> dict:
    errors: list[str] = []

    kwh, errs = _parse_decimal(raw.get("kWh", ""), "kWh")
    errors.extend(errs)

    bill_period = raw.get("Bill Period", "").strip()
    activity_date = None
    activity_end_date = None
    if bill_period:
        for fmt in ("%Y-%m", "%m/%Y"):
            try:
                dt = datetime.strptime(bill_period, fmt)
                activity_date = dt.date().replace(day=1)
                # Last day of the month
                next_month = (dt.replace(day=28) + __import__("datetime").timedelta(days=4)).replace(day=1)
                activity_end_date = (next_month - __import__("datetime").timedelta(days=1)).date()
                break
            except ValueError:
                continue
        else:
            errors.append(f"'Bill Period' value '{bill_period}' is not a recognised format.")

    return {
        "activity_type": "electricity_consumption",
        "quantity": kwh,
        "unit": "kWh",
        "activity_date": activity_date,
        "activity_end_date": activity_end_date,
        "location_name": raw.get("Site") or raw.get("Location"),
        "location_code": raw.get("Meter"),
        "country_code": raw.get("Country"),
        "metadata": {k: v for k, v in raw.items() if k not in ("kWh", "Bill Period", "Meter", "Reading")},
        "errors": errors,
    }


def _parse_travel_row(raw: dict) -> dict:
    errors: list[str] = []

    distance, errs = _parse_decimal(raw.get("Distance", ""), "Distance")
    errors.extend(errs)

    activity_date, errs = _parse_date(raw.get("Date", ""), "Date")
    errors.extend(errs)

    mode = raw.get("Mode", "").strip().lower()
    flight_class = raw.get("Flight Class", "").strip().lower()

    if mode == "flight":
        # DEFRA threshold: ≥ 3700 km = long haul
        haul = "long_haul" if distance >= Decimal("3700") else "short_haul"
        cls = flight_class.replace(" ", "_") if flight_class else "economy"
        activity_type = f"flight_{cls}_{haul}"
    else:
        activity_type = f"travel_{mode}"

    from_loc = raw.get("From", "").strip()
    to_loc = raw.get("To", "").strip()
    location_name = f"{from_loc} → {to_loc}" if from_loc or to_loc else None

    return {
        "activity_type": activity_type,
        "quantity": distance,
        "unit": raw.get("Distance Unit", "km").strip().lower(),
        "activity_date": activity_date,
        "location_name": location_name,
        "country_code": raw.get("Country"),
        "metadata": {k: v for k, v in raw.items() if k not in ("Distance", "Mode", "Flight Class", "Date")},
        "errors": errors,
    }


_PARSERS = {
    "sap_procurement": _parse_sap_row,
    "utility_electricity": _parse_utility_row,
    "corporate_travel": _parse_travel_row,
}


def _mark_failed(raw_record: RawEmissionData, errors: list[str]) -> None:
    raw_record.parsing_status = RawEmissionData.ParsingStatus.FAILED
    raw_record.parsing_errors = errors
    raw_record.save(update_fields=["parsing_status", "parsing_errors"])

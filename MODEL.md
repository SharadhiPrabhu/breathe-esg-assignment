# Breathe ESG — Data Model Reference

A technical walkthrough of the Django data model powering the Breathe ESG carbon emissions tracking platform. This document explains not just what each model does, but why it is designed the way it is, and where the deliberate trade-offs lie.

---

## 1. Overview

The data model is built around a single central question: **"Where did this CO2e number come from, and can we prove it?"**

Every emission record in the system is traceable back to:
- The exact CSV row that was uploaded
- The user who uploaded it
- The emission factor that was applied
- Any edits made after the fact, and who made them

This chain of provenance is what makes a sustainability platform audit-ready rather than just a reporting tool.

The nine models divide cleanly into four layers:

```
┌─────────────────────────────────────────────────────────────┐
│  MULTI-TENANCY LAYER          Tenant · User                 │
├─────────────────────────────────────────────────────────────┤
│  INGESTION LAYER              DataSource · IngestionBatch   │
│                               RawEmissionData               │
├─────────────────────────────────────────────────────────────┤
│  PROCESSING LAYER             EmissionFactor                │
│                               NormalizedEmissionRecord      │
├─────────────────────────────────────────────────────────────┤
│  AUDIT LAYER                  EmissionRecordEdit            │
│                               DataQualityIssue              │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Core Principles

### Multi-tenancy
Every model that holds business data carries a `tenant` foreign key. All queries in production would filter by `request.user.tenant`, ensuring complete data isolation between organisations without requiring separate databases or schemas. This is the "shared database, shared schema" multi-tenancy pattern — simpler to operate than per-tenant schemas, with isolation enforced at the application layer.

### Immutable source data
`RawEmissionData` is never modified after it is written. It stores exactly what was in the uploaded CSV row. If an analyst later corrects a quantity, the correction goes into `EmissionRecordEdit` with a justification field, not a silent overwrite of the raw record. The original is always there to compare against.

### GHG Protocol alignment
The model encodes the GHG Protocol's three-scope framework directly into the schema. `ghg_scope` is an integer choice field with values 1, 2, or 3. Scope 3 records additionally carry a `scope3_category` integer corresponding to the 15 standard Scope 3 categories (e.g., category 6 = business travel). This means reporting can filter by scope without any string matching or post-processing classification.

### Audit trail by design
`EmissionRecordEdit` stores every field change with the old value, new value, editor, timestamp, and a mandatory justification. The `is_audit_locked` flag on `NormalizedEmissionRecord` prevents changes to records that have been submitted to regulators or included in a verified report. Two separate user foreign keys (`reviewed_by` and `locked_by`) make the approval chain explicit.

---

## 3. Database Schema

### 3.1 Tenant

```python
class Tenant(models.Model):
    id         = UUIDField(primary_key=True, default=uuid.uuid4)
    name       = CharField(max_length=255)
    slug       = SlugField(unique=True)
    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)
```

**What it does:** The top-level isolation boundary. Every piece of business data in the system belongs to exactly one tenant.

**Why UUIDs as primary keys:** All nine models use `uuid.uuid4` as the primary key instead of auto-incrementing integers. This prevents ID enumeration attacks (an attacker cannot guess `/records/1001` to see another org's data), and it makes records safe to reference across systems or export without leaking internal sequence counts.

**Why a slug:** The slug (e.g., `breathe-demo`) is a stable, URL-safe identifier that can be used in subdomain routing (`breathe-demo.platform.com`) or API path prefixing without exposing the UUID. It is constrained `unique=True` at the database level.

**Trade-off:** In this implementation, tenant resolution is manual — every view and queryset must explicitly filter by `request.user.tenant`. A more robust approach would use a middleware that sets a thread-local or attaches the tenant to the request object early, eliminating the risk of a developer forgetting the filter.

---

### 3.2 User

```python
class User(AbstractUser):
    class Role(TextChoices):
        ANALYST = "analyst"
        MANAGER = "manager"
        AUDITOR = "auditor"
        ADMIN   = "admin"

    tenant = ForeignKey(Tenant, on_delete=CASCADE, null=True, blank=True)
    role   = CharField(max_length=20, choices=Role.choices, default=Role.ANALYST)
```

**What it does:** Extends Django's built-in `AbstractUser` with two fields: a tenant membership and a role.

**Why extend `AbstractUser` rather than use a `Profile` model:** A separate `Profile` model requires an extra join on every authenticated request. `AbstractUser` keeps identity and role in the same row, which is simpler and faster. The cost is that migrating away from this approach later (e.g., to support users belonging to multiple tenants) requires a more complex migration.

**Why `null=True` on tenant:** Superusers and platform-level admins don't belong to any tenant — they operate across all tenants for support and operations purposes. `null=True, blank=True` makes the tenant optional for these accounts without a separate user model.

**Role design:** Four roles form a graduated permission hierarchy:
- `analyst` — can upload data and view records
- `manager` — can approve/reject records and manage the review workflow
- `auditor` — read-only access to all records including locked ones (external audit use)
- `admin` — full control including data source configuration and user management

Role enforcement is not implemented in this demo — it is a schema-level declaration of intent, ready to be wired into Django REST Framework's permission classes.

---

### 3.3 DataSource

```python
class DataSource(models.Model):
    class SourceType(TextChoices):
        SAP_PROCUREMENT      = "sap_procurement"
        UTILITY_ELECTRICITY  = "utility_electricity"
        CORPORATE_TRAVEL     = "corporate_travel"

    tenant        = ForeignKey(Tenant, ...)
    source_type   = CharField(choices=SourceType.choices)
    name          = CharField(max_length=255)
    configuration = JSONField(default=dict)
    is_active     = BooleanField(default=True)
```

**What it does:** Describes a class of data that a tenant uploads — not a specific file, but a category (SAP fuel purchases, electricity bills, travel reports). Each `IngestionBatch` is linked to a `DataSource`, which tells the pipeline how to parse and interpret the CSV.

**The `configuration` JSONField:** This is the extensibility point. It stores source-specific settings as a JSON object rather than adding columns for every possible setting. For example, the corporate travel source stores its column mappings here:

```json
{
  "column_mappings": {
    "date": "Date",
    "employee": "Employee",
    "from": "From",
    "to": "To",
    "distance": "Distance",
    "mode": "Mode",
    "flight_class": "Flight Class"
  }
}
```

This lets the platform support variations within the same source type (e.g., one customer's SAP export uses "Posting Date" while another uses "Document Date") without schema changes.

**`is_active` flag:** Data sources can be deactivated without deletion. If a data source is deactivated, the upload UI stops accepting files for it and historical batches remain linked and queryable. Hard deletion would orphan historical batches or cascade-delete years of emissions data.

**Trade-off:** Auto-detection of source type (matching CSV headers against signatures) is implemented in `IngestionService.detect_source_type()`. This is convenient for the demo but fragile in production — header names vary by vendor and export template. The `DataSource.configuration` field is designed to eventually hold explicit column mappings that override auto-detection.

---

### 3.4 IngestionBatch

```python
class IngestionBatch(models.Model):
    class Status(TextChoices):
        PENDING    = "pending"
        PROCESSING = "processing"
        COMPLETED  = "completed"
        FAILED     = "failed"
        PARTIAL    = "partial"

    tenant                  = ForeignKey(Tenant, ...)
    data_source             = ForeignKey(DataSource, ...)
    file_name               = CharField(max_length=255)
    status                  = CharField(choices=Status.choices, default=PENDING)
    total_rows              = IntegerField(default=0)
    processed_rows          = IntegerField(default=0)
    successful_rows         = IntegerField(default=0)
    failed_rows             = IntegerField(default=0)
    error_log               = JSONField(default=list)
    uploaded_by             = ForeignKey(User, on_delete=SET_NULL, null=True)
    uploaded_at             = DateTimeField(auto_now_add=True)
    processing_started_at   = DateTimeField(null=True, blank=True)
    processing_completed_at = DateTimeField(null=True, blank=True)
```

**What it does:** Represents one file upload event. It is the unit of work for the ingestion pipeline and the primary thing shown in the "Recent Uploads" dashboard table.

**The five statuses form a state machine:**

```
PENDING → PROCESSING → COMPLETED
                     → FAILED      (all rows errored, or file could not be read)
                     → PARTIAL     (some rows succeeded, some failed)
```

`PARTIAL` is a first-class status because real-world CSV files are messy. A 1000-row file might have 3 malformed rows. Refusing the entire upload because of 3 bad rows is too strict. Silently accepting everything is too loose. `PARTIAL` lets analysts see exactly which rows failed and why, then decide whether to re-upload a corrected file or leave the batch as-is.

**The `error_log` JSONField:** Stores a list of `{"row": N, "errors": ["..."]}` objects — one per failed row. This gives the analyst enough information to fix their source data without needing to download the original file and cross-reference it manually.

**Timestamp triplet:** Three timestamps (`uploaded_at`, `processing_started_at`, `processing_completed_at`) enable monitoring of processing latency. If `processing_started_at` is set but `processing_completed_at` is not, the batch is stuck — useful for alerting on hung jobs in a production async pipeline.

**`uploaded_by` uses `SET_NULL`:** If the user account is deleted, the batch history is preserved. The file name and timestamps remain even without the user reference, which matters for compliance — you need to know *when* data was ingested even if the employee has left the company.

**Trade-off:** In this implementation, ingestion is synchronous — the CSV is parsed in the same HTTP request that receives the upload. For files beyond a few thousand rows, this would time out. The architecture is ready for async processing (a Celery task would call the same `IngestionService.parse_csv_file` and `NormalizationService.normalize_raw_record` methods) but the task queue itself is not implemented.

---

### 3.5 RawEmissionData

```python
class RawEmissionData(models.Model):
    class ParsingStatus(TextChoices):
        PENDING = "pending"
        PARSED  = "parsed"
        FAILED  = "failed"

    tenant           = ForeignKey(Tenant, ...)
    ingestion_batch  = ForeignKey(IngestionBatch, related_name="raw_rows")
    row_number       = IntegerField()
    raw_data         = JSONField()
    parsing_status   = CharField(choices=ParsingStatus.choices, default=PENDING)
    parsing_errors   = JSONField(default=list)
    parsed_at        = DateTimeField(null=True, blank=True)
```

**What it does:** Stores one CSV row exactly as it arrived — the raw column names and values, untransformed. This is the immutable source of truth.

**Why store raw data at all:** Without this model, if the normalization logic has a bug, you cannot reprocess old uploads without asking the customer to re-upload the original files. With `RawEmissionData`, you can fix the normalization bug and replay every historical raw row through the corrected pipeline.

**`raw_data` as JSONField:** Each row is stored as a Python dict (column name → value), serialized to JSON. This handles schema variation gracefully — if one batch has a "Department" column and another doesn't, both are stored correctly without any schema migration.

**`row_number` field:** Stores the 1-based row number from the CSV (including the header row in the count, so data starts at row 2). This lets error messages say "row 47 is invalid" in a way that matches what the analyst sees when they open the file in Excel.

**The link to `NormalizedEmissionRecord`:** The reverse relation is `raw_record.normalized_records` — one raw row can produce exactly one normalized record (or zero, if parsing failed entirely). The FK on `NormalizedEmissionRecord` uses `SET_NULL` so that the normalized record survives even if the raw row is somehow deleted.

**Trade-off:** Storing every raw row in the database has a storage cost. For a platform processing millions of rows per day, this table would grow very large. A common mitigation is to store raw rows in object storage (S3) and keep only a reference in the database, with on-demand retrieval. For the scale of this demo, database storage is appropriate.

---

### 3.6 EmissionFactor

```python
class EmissionFactor(models.Model):
    factor_type           = CharField(max_length=100)
    factor_value_kg_co2e  = DecimalField(max_digits=15, decimal_places=6)
    unit                  = CharField(max_length=50)
    region                = CharField(max_length=10)
    source                = CharField(max_length=50)
    valid_from            = DateField()
    valid_until           = DateField(null=True, blank=True)
```

**What it does:** Stores CO2e conversion factors. An emission factor answers the question: "how many kilograms of CO2e does one unit of this activity produce?"

**`factor_type` naming convention:** Factor types use a hierarchical naming scheme that matches the `activity_type` field on `NormalizedEmissionRecord`:

| factor_type | Meaning |
|---|---|
| `fuel_diesel_combustion` | Diesel burned in vehicles or boilers |
| `fuel_natural_gas_combustion` | Gas burned on-site |
| `electricity_consumption` | Grid electricity (Scope 2) |
| `flight_economy_short_haul` | Economy class flight < 3,700 km |
| `flight_economy_long_haul` | Economy class flight ≥ 3,700 km |
| `flight_business_short_haul` | Business class flight < 3,700 km |
| `travel_rail` | Train travel |
| `travel_car` | Car travel |
| `travel_bus` | Bus travel |

The lookup in `NormalizationService.find_emission_factor()` matches `factor_type` case-insensitively against the normalized record's `activity_type`.

**`factor_value_kg_co2e` uses Decimal:** Floating-point arithmetic introduces rounding errors that accumulate across thousands of records. `DecimalField` with `decimal_places=6` gives sub-milligram precision, which is important when summing CO2e across large datasets.

**Temporal validity:** The `valid_from` / `valid_until` pair allows the database to hold multiple vintages of the same factor. DEFRA updates emission factors annually. When a company reports emissions for 2023, they should use 2023 factors, not 2025 factors. The lookup service filters factors by the `activity_date` of the record being normalized, ensuring temporally correct factors are applied automatically.

**Region hierarchy:** The lookup tries a regional match first (`region = "UK"`, for example) and falls back to `GLOBAL`. This allows country-specific grid emission factors (which vary significantly — UK grid is much cleaner than coal-heavy grids) to override the global average when country data is available.

**Source citation:** The `source` field records the publication the factor came from (e.g., `DEFRA_2024`). This is the citation that appears in sustainability reports and audit submissions. It makes factors auditable — an auditor can look up the original publication to verify the number.

---

### 3.7 NormalizedEmissionRecord

This is the central model — the processed, quantified emission event. All reporting, charting, and analytics are built on top of this table.

```python
class NormalizedEmissionRecord(models.Model):
    # Identity and provenance
    tenant           = ForeignKey(Tenant, ...)
    raw_data         = ForeignKey(RawEmissionData, on_delete=SET_NULL, null=True)
    ingestion_batch  = ForeignKey(IngestionBatch, ...)

    # Activity description
    activity_date     = DateField()
    activity_end_date = DateField(null=True, blank=True)
    activity_type     = CharField(max_length=100)

    # GHG classification
    ghg_scope       = IntegerField(choices=GHGScope.choices)   # 1, 2, or 3
    scope3_category = IntegerField(null=True, blank=True)      # 1–15 per GHG Protocol

    # Quantity (original and normalized)
    quantity_original   = DecimalField(max_digits=15, decimal_places=4)
    unit_original       = CharField(max_length=50)
    quantity_normalized = DecimalField(max_digits=15, decimal_places=4)
    unit_normalized     = CharField(max_length=50)

    # Location
    location_name = CharField(null=True, blank=True)
    location_code = CharField(null=True, blank=True)
    country_code  = CharField(max_length=3, null=True, blank=True)

    # Emission calculation
    emission_factor       = ForeignKey(EmissionFactor, on_delete=SET_NULL, null=True)
    emission_factor_value = DecimalField(max_digits=15, decimal_places=6)
    co2e_kg               = DecimalField(max_digits=15, decimal_places=4)

    # Quality
    metadata           = JSONField(default=dict)
    data_quality_score = CharField(choices=DataQuality.choices, default=MEDIUM)
    quality_flags      = JSONField(default=list)

    # Review workflow
    review_status = CharField(choices=ReviewStatus.choices, default=PENDING)
    reviewed_by   = ForeignKey(User, null=True, related_name="reviewed_records")
    reviewed_at   = DateTimeField(null=True, blank=True)
    review_notes  = TextField(blank=True)

    # Audit lock
    is_audit_locked = BooleanField(default=False)
    locked_by       = ForeignKey(User, null=True, related_name="locked_records")
    locked_at       = DateTimeField(null=True, blank=True)
```

**Why store both original and normalized quantity:** If a utility bill reports `5 MWh` and the platform normalizes it to `5000 kWh`, both values are preserved. `quantity_original` / `unit_original` are what was in the source system. `quantity_normalized` / `unit_normalized` are what the emission factor is applied against. This lets analysts verify the conversion and catch unit errors (e.g., a bill accidentally entered in GJ instead of kWh would look obviously wrong when you see the original quantity next to the normalized one).

**Why denormalize `emission_factor_value`:** The `emission_factor` FK points to the `EmissionFactor` record that was used. But the FK alone is not enough — emission factors can be revised or deleted. `emission_factor_value` stores the exact numerical value that was applied at calculation time. If the factor is later corrected, old records still show the value that was actually used to produce the CO2e figure, and the discrepancy is visible.

**`activity_end_date` for period-based data:** Point-in-time events (a fuel purchase, a flight) have only `activity_date`. But electricity bills cover a billing period — a record might run from 2025-01-01 to 2025-01-31. `activity_end_date` handles this without requiring a separate model.

**The `metadata` JSONField:** Stores source-specific fields that don't map to standard columns. For SAP procurement, this includes the vendor name, cost center, and purchase order number. For corporate travel, it includes the employee name and trip origin/destination. Keeping these in `metadata` rather than dedicated columns prevents model bloat while retaining all original context.

**Data quality scoring:** The `data_quality_score` field is calculated at normalization time by `NormalizationService.calculate_data_quality_score()` using a penalty system:

| Condition | Penalty |
|---|---|
| No emission factor found | +3 |
| Missing activity date | +2 |
| Zero quantity | +2 |
| Each quality flag (warning) | +1 each |
| Missing location | +1 |
| Data older than 2 years | +1 |

Final score: 0 penalties = `high`, 1–3 = `medium`, 4+ = `low`. This gives analysts a quick signal about which records need attention without requiring them to read every quality flag individually.

**Review workflow:** The four-state review status (`pending → needs_info → approved / rejected`) mirrors standard corporate approval workflows. `reviewed_by` and `reviewed_at` record who approved or rejected, satisfying audit requirements for human sign-off on emissions data. `review_notes` allow the reviewer to document their reasoning.

**Audit lock:** Once a record is included in a verified sustainability report, `is_audit_locked = True` prevents further edits (even by admins). `locked_by` and `locked_at` record who locked it and when. This is the mechanism that makes the record legally defensible — you can prove it hasn't been altered after submission.

---

### 3.8 EmissionRecordEdit

```python
class EmissionRecordEdit(models.Model):
    record        = ForeignKey(NormalizedEmissionRecord, related_name="edits")
    field_name    = CharField(max_length=100)
    old_value     = TextField()
    new_value     = TextField()
    edited_by     = ForeignKey(User, on_delete=CASCADE)
    edited_at     = DateTimeField(auto_now_add=True)
    justification = TextField()
```

**What it does:** Records every manual change made to a normalized emission record after it was created. This is an append-only audit log — edits are never updated or deleted.

**Why field-level granularity:** Rather than storing the entire record state before and after (a snapshot approach), the model stores individual field changes. This is more space-efficient and makes it easy to see "who changed the emission factor, and when?" without diffing two large JSON blobs.

**`justification` is non-nullable:** Every edit requires an explanation. This is a deliberate friction point — analysts cannot silently correct numbers. They must document why a change was made (e.g., "Meter reading was in MWh not kWh — corrected unit"). This justification appears in audit reports.

**`edited_by` uses `CASCADE` (not `SET_NULL`):** Unlike most user references in this model, the editor FK cascades on user deletion. The reasoning is that audit records without an identifiable editor are less useful — if the user is deleted, the audit trail for their edits should be reviewed by an admin before deletion, not silently nullified. (In practice, user accounts should be deactivated, not deleted, to preserve this trail.)

**`old_value` and `new_value` as TextField:** All values are stored as strings regardless of the underlying field type. This avoids type-conversion complexity and makes the audit log readable as plain text. The `field_name` column tells you what type to expect.

---

### 3.9 DataQualityIssue

```python
class DataQualityIssue(models.Model):
    class Severity(TextChoices):
        INFO     = "info"
        WARNING  = "warning"
        ERROR    = "error"
        CRITICAL = "critical"

    tenant        = ForeignKey(Tenant, ...)
    record        = ForeignKey(NormalizedEmissionRecord, null=True, blank=True)
    issue_type    = CharField(max_length=100)
    severity      = CharField(choices=Severity.choices)
    description   = TextField()
    auto_detected = BooleanField(default=True)
    resolved      = BooleanField(default=False)
    resolved_by   = ForeignKey(User, on_delete=SET_NULL, null=True)
    resolved_at   = DateTimeField(null=True, blank=True)
```

**What it does:** A structured issue tracker for data quality problems. Where `NormalizedEmissionRecord.quality_flags` stores a simple list of warning strings, `DataQualityIssue` stores each problem as a first-class record with a severity level, resolution tracking, and the ability to link to a specific emission record or stand alone (for batch-level issues).

**Four severity levels:** `INFO` (informational, no action required) → `WARNING` (should be reviewed) → `ERROR` (likely incorrect, should be corrected before reporting) → `CRITICAL` (must be resolved before any reporting can proceed). This graduated scale lets the system prioritize analyst attention without treating every data quirk as a blocker.

**`record = null` for batch-level issues:** The record FK is nullable, allowing issues to be attached to an entire ingestion batch (e.g., "50% of rows are missing location data — check your export settings") rather than to a specific record. This catches systemic problems that would require fixing the source system rather than individual record edits.

**`auto_detected` flag:** Issues can be created by the normalization pipeline (auto-detected) or manually flagged by an analyst. Separating these two sources lets managers filter the issue list — "show me only the issues a human flagged" is a meaningful query for prioritization.

**Resolution tracking:** `resolved`, `resolved_by`, `resolved_at` close the loop. An unresolved issue is a known problem. A resolved issue is documented evidence that the problem was identified and addressed — exactly what auditors want to see.

---

## 4. Data Flow

The lifecycle of a single CSV row from upload to audit-ready record:

```
1. UPLOAD
   User uploads CSV via the /upload endpoint.
   ↓
   IngestionBatch is created (status: PENDING).

2. PARSING  [IngestionService.parse_csv_file]
   File is read with pandas.
   Headers are validated against REQUIRED_COLUMNS for the source type.
   Each row is validated (date formats, positive numbers, valid enum values).
   ↓
   One RawEmissionData row is created per CSV row.
   RawEmissionData.parsing_status = PARSED (valid) or FAILED (invalid).
   IngestionBatch.status updated to COMPLETED / PARTIAL / FAILED.

3. NORMALIZATION  [NormalizationService.normalize_raw_record]
   Called for each RawEmissionData with parsing_status = PARSED.
   Source-specific parser extracts structured fields from raw_data JSON.
   Unit conversion applied (gallons→liters, miles→km, MWh→kWh, etc.).
   EmissionFactor looked up by activity_type + unit + region + date.
   co2e_kg = quantity_normalized × emission_factor_value_kg_co2e
   GHG scope classified from source_type.
   Data quality score calculated.
   ↓
   One NormalizedEmissionRecord is created.
   review_status = PENDING.

4. REVIEW
   Manager reviews pending records.
   Status updated to APPROVED, REJECTED, or NEEDS_INFO.
   Any corrections are logged as EmissionRecordEdit entries.
   Data quality issues are flagged on DataQualityIssue.

5. LOCK
   After records are included in a verified report or regulatory submission:
   is_audit_locked = True.
   No further edits permitted.
```

---

## 5. Source-of-Truth Tracking

Every `NormalizedEmissionRecord` is connected to its origin through an unbroken FK chain:

```
NormalizedEmissionRecord
  → raw_data (RawEmissionData)
      → ingestion_batch (IngestionBatch)
          → data_source (DataSource)
              → tenant (Tenant)
  → emission_factor (EmissionFactor)
  → reviewed_by (User)
```

This means you can answer these audit questions from the database alone:

- "Show me the original CSV row that produced this emission record" → `record.raw_data.raw_data`
- "What file did this come from?" → `record.ingestion_batch.file_name`
- "Who uploaded it?" → `record.ingestion_batch.uploaded_by`
- "What emission factor was used?" → `record.emission_factor` (FK) and `record.emission_factor_value` (snapshot)
- "Has this record been changed since ingestion?" → `record.edits.count() > 0`
- "Who approved this for reporting?" → `record.reviewed_by`

---

## 6. Unit Normalization

The normalization service converts all quantities to canonical units before applying emission factors. This means emission factors only need to exist in one unit per category — there is no need for a `fuel_diesel_combustion_per_gallon` factor alongside `fuel_diesel_combustion_per_liter`.

**Canonical units by source type:**

| Source Type | Canonical Unit |
|---|---|
| `sap_procurement` | liter |
| `utility_electricity` | kWh |
| `corporate_travel` | km |

**Conversion table (selection):**

| Input Unit | Converts To | Factor |
|---|---|---|
| gallon, gal | liter | × 3.78541 |
| m³ | liter | × 1000 |
| MWh | kWh | × 1000 |
| GJ | kWh | × 277.778 |
| mile, mi | km | × 1.60934 |
| tonne, t | kg | × 1000 |

**How the conversion works:**

```
qty_normalized = qty_original × (from_unit_factor / to_unit_factor)
```

Both `from_unit_factor` and `to_unit_factor` express the number of canonical-base units in one of that unit (e.g., gallons convert to liters via factor 3.78541, liters convert to liters via factor 1.0). The ratio cancels correctly for any pair of units within the same physical dimension.

**Unknown units:** If a unit is not in the conversion table, a `ValueError` is raised and logged as a quality flag on the normalized record. The record is still saved with a `LOW` quality score rather than discarded — this preserves the raw data for reprocessing once the unit mapping is added.

---

## 7. GHG Scope Classification

Scope classification is deterministic based on source type, not on the content of individual rows:

```python
SCOPE_MAP = {
    "sap_procurement":     (1, None),   # Direct combustion of purchased fuels
    "utility_electricity": (2, None),   # Purchased electricity
    "corporate_travel":    (3, 6),      # Scope 3, Category 6: Business Travel
}
```

This is a deliberate simplification. In reality, SAP procurement data could contain Scope 3 purchases (e.g., raw materials), and travel data might occasionally be Scope 1 (company-owned vehicles). But inferring scope from activity type alone, without additional context, would require complex rules with many exceptions.

The current approach guarantees correctness for the three source types in scope, and the `scope3_category` integer field is ready to be populated with more granular classification as additional source types are added.

**Scope 3 Category 6 (Business Travel):** Flights, rail, car, and bus travel all fall under GHG Protocol Category 6. The category integer (6) is stored on every corporate travel record, enabling filtering for Scope 3 sub-category breakdowns in reporting.

---

## 8. Trade-offs

### What this model handles well

**Audit completeness:** The combination of immutable raw data, a field-level edit log, temporal emission factors, and audit locking gives the platform a genuinely defensible audit trail. Every number can be traced back to its source with full provenance.

**Real-world data messiness:** The model is designed to handle partial failures gracefully. Bad rows are stored with error details rather than discarded. Records with missing emission factors are saved at `LOW` quality rather than rejected. This prevents data loss at ingestion time while making problems visible for human review.

**Multi-source extensibility:** Adding a new data source requires: (1) adding a `SourceType` choice, (2) adding required columns and a source signature to `ingestion.py`, (3) writing a row parser in `normalization.py`, and (4) adding emission factors for the new activity types. The rest of the pipeline — validation, quality scoring, review workflow, audit locking — works for any source type without changes.

**Temporal correctness:** Emission factors are date-bound. Records processed in different years automatically use the factors that were valid at the time of the activity, not the current factor. This matters for retroactive reporting when factors have changed.

### What this model does not handle well

**Multi-tenant query enforcement:** Tenant isolation is enforced manually in each view. A missing `.filter(tenant=...)` clause would silently return cross-tenant data. A row-level security system (PostgreSQL RLS, or a custom QuerySet manager that always filters by tenant) would be safer.

**Async ingestion:** Large files block the HTTP request. Moving ingestion to a background task queue (Celery + Redis) would require adding a task ID to `IngestionBatch` and a polling or webhook mechanism for the frontend. The schema is ready for this, but the async infrastructure is not implemented.

**Re-normalization workflow:** When an emission factor is corrected, there is no built-in mechanism to re-calculate CO2e for all affected records. A `reprocess` management command could iterate over all records that used the old factor, but the review and audit lock states would need careful handling — reprocessing a locked record should probably require an admin override and create a new `EmissionRecordEdit` entry.

**Unit validation at upload time:** The ingestion validator checks that `Quantity` is a positive number but not that the unit is recognized by the normalization service. An unknown unit only surfaces as a quality flag after normalization. Validating unit recognition at ingestion time would give users earlier, clearer feedback.

**Scope 3 category granularity:** All corporate travel is assigned to Category 6 unconditionally. A complete Scope 3 implementation would need at least 15 source types (one per category), or a more sophisticated classification engine that examines activity type and supplier metadata to assign categories.

---

*Model version 1.0 — reflects implementation as of May 2026. Based on `backend/core/models.py`, `backend/core/services/ingestion.py`, and `backend/core/services/normalization.py`.*

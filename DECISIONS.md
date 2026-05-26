# Breathe ESG — Engineering Decisions

This document explains the deliberate choices made during development, the ambiguities I resolved on my own, and the questions I'd bring to the PM before building the next version. The goal is to show that every default was considered, not accepted blindly.

---

## 1. Data Source Choices

### SAP Procurement

**Format chosen:** Flat CSV export that mirrors a typical SAP FI/MM posting journal.

**Columns included:**

| Column | Why |
|---|---|
| `Material` / `Material Description` | Determines activity type (diesel, petrol, gas) via keyword classification |
| `Quantity` | The consumed amount |
| `Unit` | The unit of that amount (handled by unit normalization) |
| `Posting Date` | When the transaction was recorded in SAP |
| `Plant` | Maps to `location_name` — which facility generated the emission |
| `Country` | Enables regional emission factor lookup |

**Deliberately left out:** Vendor/supplier name, purchase order number, cost center, GL account code, material number (as distinct from description). These are available in SAP exports but don't affect the emission calculation. They are preserved in the `metadata` JSONField rather than modelled as columns, which keeps the schema stable when a customer's SAP export includes extra fields.

**What I simplified:** SAP exports are not just fuel purchases — they contain everything from office supplies to raw materials. A production system would need a classification engine (possibly ML-based) to determine which line items represent direct emissions. I simplified this to keyword matching on the material description for three fuel types: diesel, petrol, and natural gas.

---

### Utility Electricity

**Format chosen:** Monthly electricity billing export, matching the format produced by most UK/US utility portals (CSV downloads from supplier account pages).

**Columns included:**

| Column | Why |
|---|---|
| `Meter` | Uniquely identifies the physical meter — maps to `location_code` |
| `Account Number` | The supplier account reference — validated as required but stored in metadata |
| `Bill Period` | The billing month (YYYY-MM or MM/YYYY) — maps to `activity_date` and `activity_end_date` |
| `kWh` | Electricity consumed — the quantity for CO2e calculation |
| `Site` | The building or facility — maps to `location_name` |
| `Country` | Enables UK/US/GLOBAL emission factor selection |

**Deliberately left out:** Demand charges, reactive power (kVAR), power factor, tariff name, peak vs off-peak split, renewable energy certificate (REC) claims. These are on real utility bills but irrelevant to a basic location-based Scope 2 calculation.

**The `Bill Period` decision:** Electricity bills cover a period, not a point in time. Rather than forcing users to provide explicit start and end dates (which most billing exports don't have), I parse a single `Bill Period` field in YYYY-MM or MM/YYYY format and derive the first and last day of that month automatically in `_parse_utility_row`. This matches how analysts actually think about electricity data.

---

### Corporate Travel

**Format chosen:** An employee expense-style travel log, matching the structure of outputs from corporate travel management platforms (Concur, Egencia, TravelPerk).

**Columns included:**

| Column | Why |
|---|---|
| `Date` | When the trip occurred |
| `Employee` | Who travelled — stored in metadata, used for deduplication checks |
| `From` | Origin — combined with `To` to form `location_name` (e.g., "London → New York") |
| `To` | Destination |
| `Distance` | Distance in km — the quantity for CO2e calculation |
| `Mode` | Transport mode (flight, rail, car, bus, ferry, taxi) |
| `Flight Class` | Economy, premium economy, business, first — affects emission factor |

**Deliberately left out:** Hotel nights, taxi receipts, meal expenses, currency amounts. These don't produce direct travel emissions. In a complete Scope 3 implementation, hotel stays would be Category 1 (purchased goods) rather than Category 6 (business travel) and would need a different source type and different emission factors.

**The `Flight Class` decision:** This is an optional column. If absent, `economy` is assumed. This matters significantly — a business class long-haul flight produces 3× the emissions of economy on the same route. Making it optional rather than required reduces the barrier to uploading simpler travel logs while still giving accurate numbers when the data is available.

---

## 2. CSV Upload vs API Integration

I chose synchronous CSV file upload for all three source types for four reasons:

**1. Appropriate scope for a 4-day prototype.** A live SAP OData API integration requires OAuth tokens, entity-set discovery, pagination handling, and a scheduled sync job. A utility API would vary by supplier. These are weeks of integration work per source, not days. CSV handles 100% of the semantic content with a fraction of the complexity.

**2. This is how initial client onboarding actually works.** Before any customer grants API access to their ERP system, they send files. The first three months of any sustainability platform engagement are almost always manual data exports. Building file upload first means the product is useful from day one, even before API integrations are built.

**3. Easier to test and demonstrate.** Anyone evaluating this prototype can upload the sample CSV files in `backend/sample_data/` and immediately see real data in the dashboard. An API integration would require mocking or a staging environment.

**4. The architecture is API-ready.** The `IngestionService` and `NormalizationService` are pure Python service classes with no HTTP dependencies. An API integration would call the same services — it would just produce `RawEmissionData` rows differently. The `DataSource.configuration` JSONField already holds the column mapping config that an API poller would need.

---

## 3. Unit Normalization Strategy

### The approach

Each source type normalizes to a canonical unit at ingestion time:

- SAP procurement → **liter** (all fuel quantities)
- Utility electricity → **kWh** (all energy quantities)
- Corporate travel → **km** (all distances)

Normalization happens in `NormalizationService.convert_units()` before the emission factor is applied. The conversion table in `normalization.py` covers the most common industrial units:

- Volume: gallon, m³, litre (all → liter)
- Energy: MWh, GJ, MJ (all → kWh, using 1 MWh = 1000 kWh, 1 GJ = 277.778 kWh)
- Distance: miles (all → km, using 1 mile = 1.60934 km)
- Mass: tonne, lb (all → kg)

### Why normalize at ingestion, not at query time

**Emission factors are defined in canonical units.** If I store raw quantities and convert at query time, every query that touches `co2e_kg` would need to carry the original unit and apply a conversion. That makes every aggregate query more complex and slower.

**The original value is preserved.** `quantity_original` and `unit_original` are never overwritten. Analysts can always see what was in the source system. Storing both values means there is no information loss — normalization is additive, not destructive.

**Conversion factors are stable.** A gallon has always been 3.78541 liters. These conversions don't change with new data — they are physical constants. Doing them once at write time is correct.

### Conversion factor sources

Conversions are standard SI/imperial relationships, not climate-specific. Energy conversions (GJ → kWh) are from the IEA unit conversion table. The 3700 km flight haul threshold is from DEFRA 2024 guidance on classifying short vs long haul for radiative forcing.

---

## 4. GHG Scope Classification Logic

### How it works

Scope is assigned based on `source_type`, not `activity_type`:

```
sap_procurement     → Scope 1 (direct fuel combustion)
utility_electricity → Scope 2 (purchased electricity)
corporate_travel    → Scope 3, Category 6 (business travel)
```

This is implemented as a lookup table in `normalization.py` (`SCOPE_MAP`). There is no inference from the content of the row.

### Why this is sufficient for the prototype

For the three source types in scope, the mapping is unambiguous. Every SAP fuel purchase in this model is a direct combustion activity (Scope 1). Every electricity bill is a Scope 2 purchased energy activity. Every travel record is a Scope 3 Category 6 activity. The model doesn't include any source type where the scope would be ambiguous.

### What would need refinement in production

**SAP procurement contains both Scope 1 and Scope 3 activities.** A real SAP export includes diesel (Scope 1), electricity (Scope 2), raw materials (Scope 3 Cat. 1), and purchased services (Scope 3 Cat. 1). Correctly classifying each line item requires either:
- A supplier-specific mapping table (complex)
- A classification model trained on material descriptions (expensive to build)
- Human review for line items that don't match a known pattern

**Location-based vs market-based Scope 2.** The GHG Protocol allows two methods for Scope 2. Location-based uses grid average emission factors (what this prototype does). Market-based uses the factor from the actual electricity supplier's fuel mix, which requires supplier certificates (REGOs in the UK, RECs in the US). Market-based is increasingly the preferred method for corporate reporting. This prototype only implements location-based.

**Biogenic carbon.** Combustion of biomass (wood pellets, biodiesel) is technically carbon-neutral in the GHG Protocol because the carbon was absorbed from the atmosphere during growth. These emissions are reported separately as biogenic CO2, not in Scope 1. The current model has no `is_biogenic` flag and would incorrectly include biomass combustion in Scope 1.

---

## 5. Emission Factor Lookup

### Regional vs GLOBAL fallback

`NormalizationService.find_emission_factor()` always tries a regional match first. If no regional factor exists for the record's `country_code`, it falls back to `GLOBAL`. This is the correct hierarchy — a UK electricity bill should use the UK grid factor (0.233 kg/kWh), not the global average (0.475 kg/kWh), because the UK grid has a much higher renewable penetration.

The seed data includes:
- **UK** electricity: 0.233 kg CO2e / kWh (DEFRA 2024)
- **US** electricity: 0.386 kg CO2e / kWh (EPA 2024)
- **GLOBAL** electricity: 0.475 kg CO2e / kWh (IEA 2024)

All fuel and travel factors are GLOBAL only, since there is no meaningful regional variation for diesel combustion or aviation.

### Why DEFRA 2024

DEFRA (UK Department for Environment, Food & Rural Affairs) publishes one of the most widely-used emission factor datasets globally, covering fuels, electricity, freight, and travel. It is:
- Free and publicly available
- Updated annually
- Cited in CDP submissions, GRI reports, and TCFD disclosures
- Specific enough to distinguish short vs long haul flights and different travel classes

EPA factors are used for US electricity because DEFRA does not publish US grid data.

### What happens when no factor matches

The normalization service does not fail silently. When no matching factor is found:

1. `emission_factor` FK is set to `null`
2. `emission_factor_value` is stored as `0`
3. `co2e_kg` is calculated as `0` (effectively reporting zero emissions)
4. A quality flag is added: `"No emission factor found for activity_type='...' unit='...' on YYYY-MM-DD"`
5. A `DataQualityIssue` is created with severity `ERROR` and type `missing_emission_factor`
6. The record's `data_quality_score` is set to `LOW`

The record is saved and visible in the dashboard at zero CO2e, with a visible quality issue. This is preferable to discarding the record — the raw data is preserved, the gap is flagged, and when a factor is added later, the record can be re-normalized.

---

## 6. Data Quality Scoring

### The two-tier system

Quality scoring runs twice for each record:

**Tier 1 — Normalization time** (`NormalizationService.calculate_data_quality_score`): A simple penalty accumulator based on structural completeness (missing date: +2, missing factor: +3, zero quantity: +2, missing location: +1, stale data: +1, each quality flag: +1). Produces an initial score.

**Tier 2 — Post-normalization** (`QualityService.check_record_quality`): A richer set of semantic checks run after the record is saved. These include:
- **Statistical anomaly detection** — flags quantities >3× or <30% of the tenant average for the same activity type (requires at least 5 historical records to avoid false positives on new tenants)
- **Duplicate detection** — flags records with the same activity type, date within ±1 day, and quantity within ±5% of an existing record
- **Date validation** — flags future dates (ERROR) and records older than 5 years (INFO)
- **Stale emission factor** — flags factors older than 3 years (WARNING)

The Tier 2 run overwrites the Tier 1 score using a severity-based rule: any CRITICAL or ERROR issue → LOW, any WARNING → MEDIUM, only INFO → keep existing, no issues → HIGH.

### Why three levels and not more

`HIGH / MEDIUM / LOW` maps directly to traffic-light thinking: green means safe to include in reporting, yellow means review before reporting, red means do not include without correction. More granular scoring (e.g., a 0–100 numeric score) would be more precise but harder to act on — "is 72 good enough?" is a harder question than "is this MEDIUM?". The three-level system is opinionated enough to drive workflow.

---

## 7. Review Workflow

### Status progression

```
PENDING → APPROVED    (manager approves, record included in reporting)
        → REJECTED    (manager rejects, record excluded with reason)
        → NEEDS_INFO  (manager flags for analyst follow-up, then back to PENDING)
```

`NEEDS_INFO` exists because the binary APPROVED/REJECTED choice is too strict for real workflows. Analysts often upload data that is mostly correct but needs one clarification (e.g., "was this diesel or HVO diesel?"). `NEEDS_INFO` lets the manager send it back without rejecting it outright, and the analyst can correct and resubmit.

The `review_notes` field is a free-text field on the record where the reviewer can explain their decision. This is separate from the `EmissionRecordEdit` log, which is structured field-level history.

### Why include audit lock

The `is_audit_locked` field exists because sustainability reports are legal documents in many jurisdictions (EU CSRD, UK SECR, SEC climate disclosure rules). Once numbers are submitted, they cannot be changed without formal restatement. The audit lock is the technical enforcement of that constraint — it prevents accidental re-normalization or quiet edits to figures that have already been signed off and published.

In the demo, the lock is modelled but not enforced in the API (because `AllowAny` permissions skip role checks). In production, a `CanEditLockedRecord` permission class would block any write request to a locked record for all roles except Admin.

### Role-based permissions (not enforced in demo)

The four roles were designed with a clear permission matrix in mind:

| Action | Analyst | Manager | Auditor | Admin |
|---|---|---|---|---|
| Upload CSV | ✓ | ✓ | — | ✓ |
| View records | ✓ | ✓ | ✓ | ✓ |
| Edit records | ✓ | ✓ | — | ✓ |
| Approve/reject | — | ✓ | — | ✓ |
| View locked records | — | — | ✓ | ✓ |
| Lock/unlock records | — | — | — | ✓ |
| Manage data sources | — | — | — | ✓ |

---

## 8. Authentication Decision

All API endpoints use `AllowAny` permissions:

```python
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
}
```

This is a deliberate choice for the demo, not an oversight.

**Why:** The assignment asks for a working prototype that can be evaluated without credential setup. Adding JWT authentication would require the evaluator to create an account, log in, obtain a token, and include it in every API request — adding friction with no benefit for single-evaluator use.

**What production authentication would look like:**

1. `djangorestframework-simplejwt` for JWT token issuance (`/api/token/` and `/api/token/refresh/`)
2. Tokens scoped to a tenant — the JWT payload includes `tenant_id` and `role`
3. A custom middleware that reads `tenant_id` from the token and attaches it to `request.tenant` so all views filter automatically
4. DRF permission classes per viewset: `IsAnalystOrAbove`, `IsManagerOrAbove`, `IsAuditLocked` etc.
5. Refresh token rotation with 24-hour access token TTL

The `User` model already has the `tenant` FK and `role` field ready — authentication implementation would not require schema changes.

---

## 9. Technology Stack Choices

### Django + Django REST Framework

Python is the dominant language in the ESG/sustainability space, which means:
- More engineers available who know the domain
- Better ecosystem for data science integrations (pandas, NumPy, scikit-learn for anomaly detection)
- Mature ORM for complex audit queries

DRF was chosen over alternatives (FastAPI, Flask) because the `ModelViewSet` pattern produced full CRUD + filtering + pagination + ordering for each model with minimal code. The `django-filter` integration with `DjangoFilterBackend` handles all query parameter filtering without custom view logic.

### React 19 + Vite (not Next.js)

This is a single-page dashboard application with client-side navigation. There is no SEO requirement, no server-rendered pages, and no content that needs to be indexed by search engines. Next.js adds SSR/SSG complexity that is entirely unnecessary here. Vite's development server starts in under a second and has no configuration overhead.

React 19 was chosen over Vue or Svelte because:
- Largest talent pool
- Recharts (the charting library) has the best React integration
- lucide-react icon library targets React specifically

### SQLite for demo, `dj_database_url` for production

The `settings.py` reads `DATABASE_URL` from the environment:

```python
if _db_url:
    DATABASES = {"default": dj_database_url.parse(_db_url, conn_max_age=600)}
else:
    DATABASES = {"default": {"ENGINE": "sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
```

SQLite requires zero configuration for evaluation. A production deployment sets `DATABASE_URL=postgresql://...` and the switch is complete. All Django ORM queries are compatible with both backends.

SQLite has one real limitation for this use case: it does not support concurrent writes. If two analysts upload files simultaneously, one request will wait. For a prototype, this is acceptable. For production with async processing, PostgreSQL's row-level locking handles concurrent ingestion correctly.

### Recharts for charts

The GHG scope bar chart on the dashboard is built with Recharts (`BarChart`, `Bar`, `Cell`, `Tooltip`, `ResponsiveContainer`). The decision criteria:
- **Recharts**: Composable, declarative, excellent dark mode support via CSS variables, good responsive container behaviour
- **Chart.js**: Imperative API, harder to theme dynamically
- **Victory**: Good but heavier bundle
- **D3**: Maximum flexibility but too much overhead for three chart types

### lucide-react for icons

Consistent icon library with 1500+ icons, MIT licensed, tree-shakeable (unused icons don't enter the bundle), and available as React components that inherit CSS `color` and `size` props. All emojis were replaced with lucide icons to ensure consistent rendering across operating systems and dark/light themes.

---

## 10. What I Would Ask the PM

Before building the next version, these are the questions I'd need answered:

**1. How should we handle duplicate records across batches?**
If an analyst uploads the same electricity bill twice (easy to do in a multi-person team), should the system flag a suspected duplicate and block the second upload, merge the records, or allow both and surface the conflict for human review? Currently, the quality service flags suspected duplicates as `WARNING` issues but does not block anything. The right answer depends on whether the reporting team deduplicates manually or expects the platform to enforce uniqueness.

**2. What is the SLA for CSV processing?**
The current implementation processes CSV files synchronously in the HTTP request. For files up to ~5,000 rows this is fine (< 2 seconds). For larger files from enterprise customers — an annual SAP export might be 50,000+ rows — synchronous processing will time out. If the SLA is "results within 5 minutes," Celery is the right answer. If results are needed immediately, we need to discuss file size limits.

**3. Do clients use SAP OData APIs or flat file exports?**
The SAP integration in this prototype assumes flat file exports (`.csv` downloaded from SAP or emailed by a colleague). Enterprise SAP instances expose OData endpoints that can be queried directly. If clients have IT teams willing to configure API access, a direct SAP integration would eliminate the manual export step and enable near-real-time data. This is a significant scope difference.

**4. Should analysts be able to edit locked records with manager approval?**
The current model treats `is_audit_locked = True` as a hard block. But real audit workflows sometimes require corrections to submitted figures — for example, if an error is discovered after submission. The GHG Protocol allows formal restatements. Should the platform support a "restatement" workflow (manager approves an exception, the change is logged, the original value is preserved alongside the new value, the report is flagged as restated)?

**5. What level of Scope 3 detail do auditors require?**
This prototype maps all corporate travel to Scope 3, Category 6 (business travel). CSRD and GRI 305 require disclosure of all 15 Scope 3 categories. Do we need to build out the other 14? Categories 1 (purchased goods), 11 (use of sold products), and 15 (investments) typically account for 70–90% of a company's total emissions footprint. Prioritising those would have the highest impact on reporting accuracy.

**6. Do we need separate handling for biogenic carbon?**
Companies that use biomass fuel (wood pellets, biogas, biodiesel) must report biogenic CO2 separately from fossil CO2 under GHG Protocol and most regulatory frameworks. Biogenic emissions appear in Scope 1 but with a separate line item, not in the main Scope 1 total. The current model has no `is_biogenic` field and would incorrectly aggregate biogenic emissions with fossil Scope 1.

**7. Should utility bills support multiple fuels?**
The current utility source type only handles electricity (kWh). Real utility bills from industrial sites often include natural gas, district heating, and steam on the same account. Should the utility source type support multi-fuel bills (which would require fuel-type classification per row), or should gas go through a separate "Utility Gas" source type with its own emission factors?

**8. For travel, do we calculate WTT (well-to-tank) emissions separately?**
DEFRA 2024 provides both combustion-only emission factors and total lifecycle (WTT + combustion) factors. Aviation fuel production (the "well-to-tank" component) adds roughly 40–60% to the combustion-only figure. Some corporate reporters include WTT in their travel emissions; others do not. Which convention should we follow, and should we store WTT and TTW (tank-to-wheel) as separate fields?

---

## 11. Prototype Scope Boundaries

These are the explicit simplifications I made to keep the prototype achievable in four days. They are not technical debt — they are deliberate scope decisions that should inform what comes next.

**SAP procurement:** Only three material types are classified (diesel, petrol, natural gas). All other materials produce an `activity_type` of `fuel_purchase_<material_name>` which will have no matching emission factor and will produce a `missing_emission_factor` quality issue. In production, a full classification engine covering hundreds of material codes would be needed.

**Utility source:** Only electricity. Natural gas, district heating, water, and steam are not supported. Gas would be Scope 1 (direct combustion at the site), not Scope 2, and would need separate source configuration.

**Travel source:** Flights, rail, car, and bus are supported. Ferry and taxi are accepted as valid modes (validated without errors) but have no emission factors in the seed data — they will produce missing factor quality issues until factors are added.

**Scope 3 coverage:** Only Category 6 (business travel) is implemented. The remaining 14 Scope 3 categories — particularly Category 1 (purchased goods and services), Category 11 (use of sold products), and Category 15 (investments) — are not modelled.

**Emission factor granularity:** All factors are GLOBAL or two-region (UK/US for electricity). Country-specific grid factors for the 30+ countries where major companies operate (Germany, Japan, India, Australia, etc.) are not seeded. Any record with a country code other than UK or US falls back to the GLOBAL IEA average.

**No supplier-specific factors:** DEFRA and CDP allow companies to use supplier-specific emission factors when a utility provides a certified renewable tariff (e.g., 100% wind electricity with REGO certificates). This would produce a 0 kg/kWh Scope 2 factor for that meter. The current model has no concept of supplier certificates or market-based Scope 2 factors.

**No uncertainty quantification:** GHG Protocol Advanced guidance recommends reporting confidence intervals alongside CO2e figures. The current model stores a single `co2e_kg` value with no uncertainty range. This is standard for primary corporate disclosure but would be insufficient for scientific reporting or TCFD scenario analysis.

**No multi-year factor versioning in the UI:** The emission factor lookup correctly uses the factor valid on the activity date. But the dashboard and records list do not expose which factor vintage was applied, or flag cases where a newer factor has been published that would change historical totals. An "Impact of factor update" report would require a separate re-calculation query.

---

*DECISIONS.md — reflects implementation as of May 2026.*

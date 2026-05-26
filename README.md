# Breathe ESG — Carbon Emissions Tracking Platform

## Overview

Full-stack carbon emissions tracking platform for ingesting, normalizing, and reviewing emissions data from multiple sources (SAP procurement, utility electricity bills, corporate travel).

**Built for:** Breathe ESG Tech Intern Assignment  
**Time frame:** 4 days  
**Tech stack:** Django REST Framework + React + Vite

---

## Live Demo

**Deployed Application:** [URL will be added after deployment]  
**Login:** No authentication required (demo mode — all endpoints use `AllowAny`)

---

## Features

- Multi-source data ingestion (SAP procurement, utility electricity, corporate travel)
- CSV file upload with per-row validation and error reporting
- Automatic unit normalization (gallons → liters, MWh → kWh, miles → km)
- GHG Protocol Scope 1 / 2 / 3 classification with Scope 3 Category 6 (business travel)
- Emission factor lookup with regional fallback (UK/US → GLOBAL)
- CO2e calculation using DEFRA 2024 conversion factors
- Data quality scoring (HIGH / MEDIUM / LOW) with automated anomaly and duplicate detection
- Review workflow (Pending → Approved / Rejected / Needs Info)
- Audit trail (every field change tracked with justification)
- Audit lock (prevent edits to records included in verified reports)
- Professional dashboard with bar chart and stats
- Dark mode (slate palette, persisted in localStorage)

---

## Architecture

```
breathe-esg-assignment/
├── backend/                          Django REST Framework API
│   ├── breathe_esg/                  Project settings and root URL config
│   └── core/                         Main application
│       ├── models.py                 9 database models
│       ├── serializers.py            DRF serializers
│       ├── views.py                  API viewsets and upload endpoint
│       ├── services/
│       │   ├── ingestion.py          CSV parsing and row validation
│       │   ├── normalization.py      Unit conversion and CO2e calculation
│       │   └── quality.py            Data quality checks
│       └── management/commands/
│           └── seed_data.py          Emission factors and sample tenant
│
└── frontend/                         React + Vite SPA
    └── src/
        ├── pages/
        │   ├── Dashboard.jsx         Stats, chart, recent records
        │   ├── Upload.jsx            Drag-and-drop CSV upload
        │   ├── RecordsList.jsx       Filterable emissions table
        │   ├── RecordDetail.jsx      Single record view
        │   └── Settings.jsx          Placeholder settings page
        ├── context/ThemeContext.jsx   Light/dark mode
        ├── api.js                     Axios API client
        └── App.jsx                    Layout, routing, sidebar
```

---

## Documentation

| File | Contents | Assignment Weight |
|---|---|---|
| [MODEL.md](MODEL.md) | Data model design — all 9 models, relationships, design decisions | 35% |
| [DECISIONS.md](DECISIONS.md) | Every technical decision made, ambiguities resolved, PM questions | 25% |
| [SOURCES.md](SOURCES.md) | Research on real-world data formats, sample data justification | 20% |
| [TRADEOFFS.md](TRADEOFFS.md) | Three things deliberately not built and why | 10% |

---

## Prerequisites

- Python 3.9+
- Node.js 16+
- npm

---

## Installation

### Backend Setup

```bash
cd backend
```

Create and activate a virtual environment:

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create `backend/.env`:

```env
DEBUG=True
SECRET_KEY=django-insecure-change-this-in-production-abc123xyz789
DATABASE_URL=sqlite:///db.sqlite3
```

Run migrations, seed the database, and start the server:

```bash
python manage.py migrate
python manage.py seed_data
python manage.py runserver
```

| | URL |
|---|---|
| API | http://localhost:8000/api/v1/ |
| Health check | http://localhost:8000/api/v1/health/ |
| Django admin | http://localhost:8000/admin/ |

> **Note:** `seed_data` creates the demo tenant, three data sources, sample users, and all emission factors. It is idempotent — safe to run multiple times.

---

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: **http://localhost:5173**

---

## Testing the Application

### 1. Dashboard

Open http://localhost:5173. The dashboard shows stats and a bar chart broken down by GHG scope. With only seed data (no uploads yet) the stats reflect whatever records exist in the database.

### 2. Upload Sample Data

Go to **Upload Data** and test with the provided files in `backend/sample_data/`:

| File | Data Source to Select | Scope | Expected Records |
|---|---|---|---|
| `sample_sap_procurement.csv` | Demo SAP System | Scope 1 | 10 rows, fuel emissions |
| `sample_utility_electricity.csv` | Demo Utility Bills | Scope 2 | 12 rows, electricity emissions |
| `sample_corporate_travel_simple.csv` | Demo Corporate Travel | Scope 3 | 5 rows, travel emissions |

After each upload, return to the Dashboard to see the stats and chart update.

### 3. Emissions Records

Go to **Emissions Records** to:
- Filter by GHG Scope, Review Status, Data Quality, or date range
- Search by activity type or location
- Click any row to see the full record detail

### 4. Dark Mode

Click the moon/sun icon in the top-right corner. Theme is persisted in `localStorage` across sessions.

---

## API Reference

Base URL: `http://localhost:8000/api/v1/`

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `health/` | Health check |
| `GET` | `emission-records/` | List emission records (paginated, filterable) |
| `GET` | `emission-records/{id}/` | Single record detail |
| `PATCH` | `emission-records/{id}/` | Update a record |
| `POST` | `emission-records/bulk-approve/` | Bulk approve by ID list |
| `GET` | `data-sources/` | List configured data sources |
| `GET` | `ingestion-batches/` | List upload batches |
| `POST` | `ingestion/upload/` | Upload a CSV file |
| `GET` | `emission-factors/` | List emission factors |
| `GET` | `quality-issues/` | List data quality issues |
| `POST` | `quality-issues/{id}/resolve/` | Mark an issue resolved |
| `GET` | `emission-edits/` | Audit log of record edits |
| `GET` | `tenants/` | List tenants |

### Common Query Parameters

```
GET /api/v1/emission-records/?ghg_scope=1
GET /api/v1/emission-records/?review_status=pending
GET /api/v1/emission-records/?activity_date_from=2024-01-01&activity_date_to=2024-12-31
GET /api/v1/emission-records/?search=diesel
GET /api/v1/emission-records/?ordering=-co2e_kg
GET /api/v1/emission-factors/?valid_on=2024-06-01
```

### Upload CSV (multipart/form-data)

```bash
curl -X POST http://localhost:8000/api/v1/ingestion/upload/ \
  -F "file=@backend/sample_data/sample_sap_procurement.csv" \
  -F "data_source_id=<uuid-from-data-sources-endpoint>"
```

Response:

```json
{
  "batch_id": "...",
  "status": "completed",
  "total_rows": 10,
  "successful_rows": 10,
  "failed_rows": 0,
  "normalized_records": 10,
  "errors": [],
  "message": "Successfully processed 10 of 10 rows; 10 emission records created."
}
```

---

## Emission Factors (Seeded)

All factors from DEFRA 2024 unless noted.

| Activity Type | Factor | Unit | Region | Source |
|---|---|---|---|---|
| `fuel_diesel_combustion` | 2.68 kg CO2e | per liter | GLOBAL | DEFRA 2024 |
| `fuel_petrol_combustion` | 2.31 kg CO2e | per liter | GLOBAL | DEFRA 2024 |
| `fuel_natural_gas_combustion` | 0.18 kg CO2e | per kWh | GLOBAL | DEFRA 2024 |
| `electricity_consumption` | 0.233 kg CO2e | per kWh | UK | DEFRA 2024 |
| `electricity_consumption` | 0.386 kg CO2e | per kWh | US | EPA 2024 |
| `electricity_consumption` | 0.475 kg CO2e | per kWh | GLOBAL | IEA 2024 |
| `flight_economy_short_haul` | 0.158 kg CO2e | per km | GLOBAL | DEFRA 2024 |
| `flight_economy_long_haul` | 0.103 kg CO2e | per km | GLOBAL | DEFRA 2024 |
| `flight_business_short_haul` | 0.237 kg CO2e | per km | GLOBAL | DEFRA 2024 |
| `flight_business_long_haul` | 0.309 kg CO2e | per km | GLOBAL | DEFRA 2024 |
| `travel_rail` | 0.041 kg CO2e | per km | GLOBAL | DEFRA 2024 |
| `travel_car` | 0.171 kg CO2e | per km | GLOBAL | DEFRA 2024 |
| `travel_bus` | 0.097 kg CO2e | per km | GLOBAL | DEFRA 2024 |

Short haul = < 3,700 km (DEFRA threshold). Long haul = ≥ 3,700 km.

---

## Tech Stack

### Backend

| Package | Version | Purpose |
|---|---|---|
| Django | 4.2.7 | Web framework and ORM |
| djangorestframework | 3.14.0 | REST API |
| django-cors-headers | 4.3.0 | CORS for frontend dev |
| django-filter | 23.3 | Query parameter filtering |
| pandas | 2.1.3 | CSV parsing |
| dj-database-url | 2.1.0 | `DATABASE_URL` → Django config |
| python-dotenv | 1.0.0 | `.env` file loading |
| psycopg2-binary | 2.9.9 | PostgreSQL driver (production) |
| gunicorn | 21.2.0 | WSGI server (production) |
| whitenoise | 6.6.0 | Static file serving |
| geopy | 2.4.1 | Location utilities |

### Frontend

| Package | Version | Purpose |
|---|---|---|
| react | 19.x | UI framework |
| react-router-dom | 7.x | Client-side routing |
| recharts | 3.x | GHG scope bar chart |
| lucide-react | 1.x | Icon library |
| vite | 8.x | Build tool and dev server |

---

## Key Design Decisions

See [DECISIONS.md](DECISIONS.md) for the full rationale. In brief:

1. **CSV upload over API integration** — same pipeline logic, fraction of the complexity; realistic for initial client onboarding
2. **Multi-tenant from day 1** — every model carries a `tenant` FK; single-tenant in demo but ready to scale
3. **Immutable raw data** — `RawEmissionData` is never modified; all corrections go through `EmissionRecordEdit`
4. **Dual quantity storage** — `quantity_original` + `quantity_normalized` so analysts can verify unit conversions
5. **Emission factor snapshot** — `emission_factor_value` denormalized onto the record so CO2e is reproducible even if the factor is later revised
6. **No authentication in demo** — `AllowAny` for frictionless evaluation; `User` model and role schema are production-ready

---

## Known Limitations

See [TRADEOFFS.md](TRADEOFFS.md) for full context.

- **No real-time API integration** — CSV file upload only
- **Scope 3 coverage** — Category 6 (business travel) only; Categories 1–15 not fully implemented
- **No authentication** — disabled for demo evaluation
- **SQLite in demo** — set `DATABASE_URL=postgresql://...` to switch to PostgreSQL
- **Synchronous upload processing** — large files (10,000+ rows) will be slow; Celery would be the production fix

---

## Production Readiness Checklist

- [ ] Enable JWT authentication (`djangorestframework-simplejwt`)
- [ ] Enforce role-based permissions per viewset
- [ ] Switch `DATABASE_URL` to PostgreSQL
- [ ] Move CSV processing to Celery background tasks
- [ ] Add API rate limiting
- [ ] Configure `ALLOWED_HOSTS` and disable `DEBUG`
- [ ] Set a strong `SECRET_KEY` from environment
- [ ] Add structured logging and error monitoring (Sentry)
- [ ] Set up automated backups
- [ ] Load-test the upload endpoint

---

## Troubleshooting

**Backend won't start:**
- Confirm Python 3.9+: `python --version`
- Virtual environment activated? Prompt should show `(venv)`
- All packages installed: `pip install -r requirements.txt`
- `.env` file present with `SECRET_KEY`?

**"SECRET_KEY not found" error:**
- Create `backend/.env` with `SECRET_KEY=anything-for-local-dev`

**Frontend can't reach the API (network error):**
- Backend must be running on port 8000 before starting the frontend
- Check browser console — CORS errors mean the backend isn't running

**Upload returns "Data source not found":**
- Run `python manage.py seed_data` to create the demo data sources
- Select the correct data source from the dropdown in the Upload UI

**Records show 0 CO2e:**
- The emission factor for that activity type is missing — check `backend/sample_data/` files match the expected column names
- Run `seed_data` again if emission factors are missing

---

## Project Documents

- [MODEL.md](MODEL.md) — complete data model reference
- [DECISIONS.md](DECISIONS.md) — engineering decisions and PM questions
- [TRADEOFFS.md](TRADEOFFS.md) — deliberate scope boundaries
- [SOURCES.md](SOURCES.md) — research on real-world data formats

---

Built by: Sagar Prabhu (MCA, Manipal Institute of Technology)  
For: Breathe ESG Tech Intern Assignment — May 2026

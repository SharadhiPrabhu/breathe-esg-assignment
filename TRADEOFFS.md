# TRADEOFFS.md

## Three Things I Deliberately Did Not Build

### 1. Real-time API Integration with External Systems

**What it would be:**
- Live connections to SAP OData APIs
- Direct integration with utility provider APIs (e.g., Schneider Electric, Siemens)
- Concur/Navan API polling for travel data
- Webhook listeners for real-time data push

**Why I didn't build it:**
- **Time constraint**: 4 days to build entire platform
- **Complexity**: Each API has different auth (OAuth2, API keys, SAP RFC), error handling, rate limits
- **Prototype value**: CSV upload demonstrates the core logic (parsing, normalization, calculation) which is the same regardless of ingestion method
- **Real-world reality**: Most initial client onboarding starts with file exports anyway, not API access
- **Testing difficulty**: Would need mock servers or test credentials for each service

**What I built instead:**
- CSV file upload with realistic column structures
- Configuration system (`DataSource.configuration`) that could be extended to store API credentials
- Batch tracking that works identically whether source is file or API

**When this should be built:**
- After initial client validation with file uploads
- When client has API access provisioned (often takes weeks/months)
- Phase 2 feature with proper async job queues (Celery) and retry logic

---

### 2. Advanced Scope 3 Category Breakdown and Supply Chain Emissions

**What it would be:**
- Full GHG Protocol Scope 3 categorization (Categories 1–15)
- Category 1: Purchased goods and services (supplier-specific factors)
- Category 4: Upstream transportation
- Category 9: Downstream transportation
- Category 11: Use of sold products
- Supplier engagement workflows (requesting supplier emissions data)
- Spend-based estimation when activity data unavailable

**Why I didn't build it:**
- **Data complexity**: Scope 3 requires detailed supply chain data rarely available in SAP/ERP exports
- **Factor availability**: Most companies don't have supplier-specific emission factors; spend-based proxies introduce significant uncertainty
- **Estimation methodology**: Spend-based vs activity-based approaches require fundamentally different data models
- **Uncertainty**: Scope 3 has high inherent uncertainty; proper implementation needs confidence intervals and data quality tiers
- **Not core to prototype**: Demonstrating accurate Scope 1/2 calculation is more important than wide but shallow Scope 3 coverage

**What I built instead:**
- Scope 3 support for corporate travel (Category 6 — the most commonly reported Scope 3 category)
- `ghg_scope` and `scope3_category` fields on `NormalizedEmissionRecord` ready to support all 15 categories
- `EmissionFactor` table structured to store supplier-specific factors when they become available

**When this should be built:**
- After Scope 1/2 is validated and audit-ready
- When the client has a supply chain data collection process in place
- Phase 3 feature, after travel, waste, and basic upstream supply chain emissions are covered

---

### 3. Authentication, Authorization, and Multi-User Workflows

**What it would be:**
- JWT-based authentication with refresh tokens
- Role-based access control (Analyst, Manager, Auditor, Admin) enforced at the API level
- User management UI (invite users, assign roles, deactivate accounts)
- Approval workflows (Manager must approve Analyst submissions before audit lock)
- Activity logs (who viewed which record, and when)
- Password reset, email verification, 2FA

**Why I didn't build it:**
- **Demo purpose**: Assignment reviewers need immediate access without a login flow
- **Time vs value**: 4 days better spent on data model correctness and calculation accuracy
- **Already designed**: The `User` model has a `role` field; `EmissionRecordEdit` tracks who changed what; `is_audit_locked` prevents unauthorized changes — the schema is auth-ready
- **Security context**: A local demo running on localhost does not need production-grade auth
- **Framework support**: Django REST Framework + SimpleJWT makes this straightforward to retrofit without schema changes

**What I built instead:**
- `User` model with four roles (`ANALYST`, `MANAGER`, `AUDITOR`, `ADMIN`)
- Audit trail fields throughout: `uploaded_by`, `reviewed_by`, `locked_by`, `edited_by`, `resolved_by`
- `is_audit_locked` flag and `EmissionRecordEdit` log as the enforcement and evidence layer
- `AllowAny` permissions for frictionless demo access, with comments marking the production replacement points

**When this should be built:**
- Before any production deployment — this is Day 1 of production development, not a later phase
- Stack: `djangorestframework-simplejwt` for token issuance, custom DRF permission classes per role, tenant ID embedded in JWT payload
- Estimate: 2–3 days for a complete auth system given the schema is already in place

---

## Summary

These three omissions were deliberate prioritization decisions, not gaps:

1. **API integration** — same pipeline logic, far more integration overhead. CSV proves the concept faster.
2. **Full Scope 3** — wide but shallow coverage adds noise without proving calculation quality. Scope 3 Cat. 6 demonstrates the end-to-end pattern.
3. **Auth/RBAC** — designed into the schema, deferred from the API layer to remove friction for evaluation.

The prototype demonstrates:
- Multi-tenant data model design
- Ingestion, normalization, and CO2e calculation pipeline
- Audit trail and review workflow
- Data quality scoring with anomaly and duplicate detection
- Professional analyst UI with dark mode, filtering, and charting

Not building these features was a strategic choice about what to prove in four days — not an oversight.

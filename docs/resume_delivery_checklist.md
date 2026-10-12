# Resume evidence and completion checklist

## Previous checkpoint

Notebook 01 standardized inpatient claims, separated 20,867 headers and 58,066
lines, linked annual beneficiaries, and explored utilization/payment concentration
and overlapping records. Notebook 02 completed descriptive DRG payment analyses,
fixed-threshold tail contributions, and the principal diagnosis contributions.
These notebooks are preserved. The earlier repository lacked reusable pipelines
for the other claims/PDE files, FFS denominators, readmission implementation,
and a Power BI report.

## Current implementation

| Resume statement | Evidence | Status / qualification |
|---|---|---|
| 10,000 beneficiaries, 11 enrollment years | analytics_validation.json, beneficiary_year | Verified; claims do not span all 11 years |
| 2.4M claims/prescription records across 19 files | source inventory + source preservation checks | Verified as raw claim-line/PDE records, not distinct claims |
| Reusable Python and SQL pipelines | build_analytics.py, SQL 02-04 | Implemented, executed on all sources |
| Normalized SQLite and Power BI-ready extracts | analytics.sqlite, processed/powerbi/*.csv | Built and checked |
| Key, duplicate, date, linkage, financial, enrollment checks | full dq_exception + quality report + unit tests | Implemented; warnings retained; CSV exceptions are sampled |
| Payments, charges, paid/charge ratios, LOS | eligible_claim, annual_service_metrics | Implemented; base vs pass-through distinction documented |
| 30-day all-cause readmissions | episode_claim, stay_episode, fact_readmission | Implemented as descriptive temporal-episode returns, not CMS HWR |
| PMPM and utilization with FFS member months | member_month, fact_member_month, annual_service_metrics | Implemented using documented annual-zero-HMO inference; monthly HMO raw data are blank |
| Beneficiary cohorts and service drivers | beneficiary_cohort, patient-year/service facts, notebooks | Implemented as descriptive annual cohorts |
| Three-page Power BI, Power Query, star schema, DAX | Medicare_Analytics.pbip and report/model folders | Three pages render; aggregate values agree with SQL; user confirms two values match after 2022 filter instructions. Core functional acceptance complete; final Desktop save is a user action. |

## Desktop acceptance and final save

Three user screenshots show the report pages running and aggregate metrics matching
SQL at displayed precision. The user subsequently confirmed two matching numbers
after instructions for the 2022 filter. Exact names of those two numbers were not
enumerated, so the record does not assert individual testing of every measure or
every cohort/service filter combination. This is sufficient to close the agreed
core functional scope; layout improvements are explicitly out of scope.
The final Desktop save is a remaining mechanical user action, not a new analysis.
Evidence: `reports/powerbi_desktop_observation.json` and `powerbi/screenshots/`.

## Resume wording corrections

Use "2.4M claim-line and prescription-event records across 19 source files".
Use "10,000 beneficiaries with 2015-2025 enrollment snapshots and claims observed
through early 2023" rather than implying 11 full years of claims.
Use "descriptive all-cause 30-day readmission analysis using temporal episodes".
Use "PMPM and utilization using documented FFS member-month eligibility proxies"
because monthly HMO indicators are unavailable. Avoid calling the measure risk
adjusted, unplanned-only, or the official CMS readmission measure.
The source is synthetic; mention CMS synthetic data in the project description.

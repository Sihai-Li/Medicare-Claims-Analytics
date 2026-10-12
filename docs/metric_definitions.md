# Metric definitions and analytical limits

## Data scope and provenance

The pipeline processes 11 annual beneficiary files (2015-2025) and eight claims/PDE files.
The 2,404,380 claims/PDE source rows are **claim lines and prescription events**, not
2.4 million distinct claims. There are 555,218 distinct service-category/claim-ID
headers, 1,888,860 source claim lines, and 515,520 source prescription events.
The enrollment universe has 10,000 distinct beneficiaries and 86,917 annual records.
Claims start dates are observed from 2014-11-18 through 2023-03-02 depending on service;
PDE dates end 2023-03-03. Primary annual comparisons use 2016-2022. Presence of all
months is not evidence of complete claim capture. These are synthetic data.

`claim_key = service_category | CLM_ID`. Header fields are checked on every source
line. A conflicting header retains its first normalized representation, all original
lines, and source locators, and is excluded from eligible claim metrics. Repeated
header amounts are never summed across lines. Every line/event has a distinct
source-row key; candidate duplicate business keys are reported without deleting rows.
All source files remain unchanged; SHA-256 checksums and row counts are recorded.
The normalized model is a selected-field analysis model. It does not copy every
source column; original columns remain available through file/row provenance.

## Enrollment and denominator

Part A+B entitlement is monthly buy-in code `3` or `C`. Monthly HMO `0` or `4`
supports FFS classification. Source references:
[entitlement codes](https://resdac.org/cms-data/variables/medicare-entitlementbuy-indicator),
[HMO codes](https://resdac.org/cms-data/variables/hmo-indicator).

**Every raw monthly HMO field is blank in this local synthetic dataset.** An eligible
month is therefore an **annual-information-inferred FFS proxy**, not independently
verified monthly FFS enrollment. A blank HMO code is inferred as non-MA only when
the annual HMO total is explicitly zero. Missing monthly A+B codes can be inferred
only when both annual Part A and Part B totals explicitly equal 12; an explicit
noneligible or invalid monthly code is never overwritten. Raw monthly values stay
blank and `member_month.eligibility_basis` records the inference separately.
Other unknown entitlement/HMO conditions remain excluded. Annual/monthly coverage
disagreements are reported. No subtraction of unrelated annual counts is used.

The conservative complete-calendar-month rule additionally requires birth and
coverage start on/before month start and death, if reported, on/after month end.
Birth/coverage/death partial months are excluded rather than fractionally prorated.
This is an explicit portfolio rule, not a CMS production eligibility algorithm.

Claims enter the FFS numerator only if their claim-start month is eligible, dates are
valid, payment is present, and header fields are consistent. Prescription events
additionally require a nonblank Part D contract in the event month. The same
year/cohort/month scope is used for each numerator and denominator. Part D plan
payments use the separate eligible Part D denominator.

## Financial fields

All normalized money values are stored as exact integer cents. Blank or invalid
values remain NULL and generate exceptions; they are not silently converted to zero.
Negative values are retained and flagged. Reports convert cents to dollars.

- **Base medical claim payment:** `CLM_PMT_AMT`, once per eligible claim.
- **Charges:** `CLM_TOT_CHRG_AMT` for institutional claims; `NCH_CARR_CLM_SBMTD_CHRG_AMT`
  for carrier/DME. These are submitted charges, not costs or patient reimbursement.
- **Total Medicare payment derived:** inpatient base plus per-diem pass-through
  amount multiplied by utilization days, when both fields are available. This is
  exposed separately and is not the default PMPM numerator.
- **Paid-to-charge ratio:** sum of base payments divided by sum of charges, using
  the same matched claims with strictly positive known charges. Ratios above one
  are not automatically deleted. Missing/nonpositive charges are flagged.
- **Rx plan payment:** covered plus noncovered Part D plan-paid amounts. This is
  separate from total drug cost, patient pay, other payer pay, and medical payments.

[CMS/ResDAC claim payment definition](https://resdac.org/cms-data/variables/claim-medicare-payment-amount)
explains pass-through amounts and the carrier/DME line-payment reconciliation.

Medical PMPM = base medical claim payment / eligible inferred FFS member-months.
Rx plan PMPM = Rx plan-paid amount / eligible inferred FFS Part D member-months.
Utilization = medical claim count × 12,000 / eligible inferred FFS member-months,
reported as **claims per 1,000 member-years**, not admissions per 1,000 people.
Mean inpatient date span = sum(discharge date − admission date) / valid-date claims.
Same-day claims have zero date span. Covered utilization days stay separate;
the 1,572 inpatient one-day differences remain documented and unchanged.

## All-cause 30-day returns

The pipeline builds **temporal episode proxies** for each beneficiary across the
entire observed inpatient history, including cross-year claims. Overlapping or
same-day-boundary intervals are merged using a running maximum discharge date.
This is conservative de-overlap handling across providers, not proof that the
clinical hospitalizations are identical. `episode_claim` retains claim membership;
claim counts, temporal episodes, and eligible index episodes are distinct quantities.

An index episode is eligible if dates are valid, there is no conflicting header,
no discharge death code (20/40/41/42), no reported death through follow-up end,
the discharge cohort/year exists, the file's maximum inpatient claim-start date
provides 30 observed follow-up days, and every calendar month touched from admission
through discharge+30 is eligible under the documented inferred-FFS rule.
The first next episode beginning **1-30 days after discharge** is an all-cause return.
Day 31 is not counted. Same-day boundaries belong to the preceding temporal episode.
The numerator is eligible index episodes with a qualifying next admission; the
denominator is all eligible index episodes, assigned by discharge year.
Episodes near the end of the observed file are excluded even if a return is visible,
to apply the same ascertainment rule to positives and negatives.

This metric is **descriptive, unadjusted, all-cause**. It does not implement a planned
readmission exclusion algorithm, a 12-month clinical lookback, formal transfer
adjudication, age-65 restriction, or risk standardization. It is not HRRP or the
official CMS HWR measure. Documentation reference:
[CMS HRRP](https://www.cms.gov/medicare/quality/value-based-programs/hospital-readmissions).

## Cohorts and concentration

Annual mutually exclusive cohorts use ESRD enrollment flag first, then an observed
same-year diagnosis-prefix diabetes flag (E08/E09/E10/E11/E13), then other/no selected
flag. This is a retrospective descriptive cohort, not a validated phenotype or a
prospective risk model. Secondary diagnoses are included; historical diagnosis
version consistency is not certified. HF/COPD proxy flags are retained in headers.
Member-month and numerator tables use the same cohort assignment. Inpatient episodes
use the discharge-year cohort. Age bands use source age at year end.

The Power BI top-10% member payment share ranks eligible members independently by
year on total eligible **medical base payment** across service categories, including
eligible zero-payment members. Ties are broken by beneficiary ID. This differs from
Notebook 01's inpatient-only rankings among claimants; the two results must not be
presented as the same population. Multi-year selection sums yearly top-group payments
before division. Cohort filters apply; a service-category filter does not redefine
this all-medical patient-year measure or the DRG-only summary.

## Quality and reproducibility

`dq_exception` contains the full exception set. `analytics_exception_samples.csv`
is capped at 5,000 rows and is labeled a sample. `fact_quality` contains full counts
per dataset/check; counts are findings, not counts of unique bad source records.
Warnings retain original data. Raw structural failures stop the build. Outputs
are staged and replace `analytics.sqlite` only after all acceptance checks pass.
The older notebook database `medicare_claims.sqlite` is separate and preserved.
Unit tests cover money precision, repeated header payment, unknown monthly codes,
partial birth months, overlapping/same-day episodes, day-30/day-31 returns,
cross-year follow-up, death exclusion, and loss of enrollment during follow-up.

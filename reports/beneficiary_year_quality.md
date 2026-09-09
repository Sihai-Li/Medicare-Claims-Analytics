# Beneficiary-year data quality report

Generated: 2026-09-09 16:10 UTC

## Build result

- Beneficiary-year rows: 86,917
- Unique beneficiaries: 10,000
- Reference years: 2015–2025
- Columns in analytical table: 28
- Quality checks: 20 (19 pass, 1 warning, 0 failures)

## Quality checks

| check_name | severity | status | failed_rows_or_entities | population | failed_pct | details |
| --- | --- | --- | --- | --- | --- | --- |
| required_primary_key | error | PASS | 0 | 86917 | 0.0 | beneficiary_id and reference_year are required. |
| unique_beneficiary_year | error | PASS | 0 | 86917 | 0.0 | Expected one row per beneficiary and reference year. |
| filename_year_matches_record | error | PASS | 0 | 86917 | 0.0 | Reference year must match the year in the source filename. |
| valid_birth_date | error | PASS | 0 | 86917 | 0.0 | Nonblank source values must parse using the CMS day-month-year format. |
| valid_death_date | error | PASS | 0 | 86917 | 0.0 | Nonblank source values must parse using the CMS day-month-year format. |
| valid_coverage_start_date | error | PASS | 0 | 86917 | 0.0 | Nonblank source values must parse using the CMS day-month-year format. |
| birth_before_death | error | PASS | 0 | 86917 | 0.0 | Birth date must not occur after death date. |
| plausible_age_range | error | PASS | 0 | 86917 | 0.0 | Age must be between 0 and 120 inclusive. |
| age_above_110 | warning | WARN | 138 | 86917 | 0.1588 | Retain valid source values but document ages above 110 in the synthetic data. |
| age_matches_birth_year | warning | PASS | 0 | 86917 | 0.0 | Age at year end should equal reference year minus birth year. |
| part_a_coverage_months_range | error | PASS | 0 | 86917 | 0.0 | Coverage months must be between 0 and 12 inclusive. |
| part_b_coverage_months_range | error | PASS | 0 | 86917 | 0.0 | Coverage months must be between 0 and 12 inclusive. |
| state_buyin_months_range | error | PASS | 0 | 86917 | 0.0 | Coverage months must be between 0 and 12 inclusive. |
| hmo_coverage_months_range | error | PASS | 0 | 86917 | 0.0 | Coverage months must be between 0 and 12 inclusive. |
| part_d_coverage_months_range | error | PASS | 0 | 86917 | 0.0 | Coverage months must be between 0 and 12 inclusive. |
| retiree_drug_subsidy_months_range | error | PASS | 0 | 86917 | 0.0 | Coverage months must be between 0 and 12 inclusive. |
| dual_eligible_months_range | error | PASS | 0 | 86917 | 0.0 | Coverage months must be between 0 and 12 inclusive. |
| birth_date_consistent_across_years | error | PASS | 0 | 10000 | 0.0 | A beneficiary should not have multiple nonblank birth dates. |
| age_progresses_across_consecutive_years | warning | PASS | 0 | 76917 | 0.0 | Age should increase by one across consecutive annual records. |
| no_record_after_death_year | warning | PASS | 0 | 86917 | 0.0 | Review beneficiary-year records occurring after a reported death year. |

## Annual enrollment summary

| reference_year | beneficiary_year_rows | unique_beneficiaries | newly_observed_beneficiaries | deaths_reported | average_age | full_part_a_beneficiaries | full_part_b_beneficiaries | beneficiaries_with_hmo | beneficiaries_with_part_d | dual_eligible_beneficiaries |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2015 | 5975 | 5975 | 5975 | 0 | 56.5 | 5975 | 5975 | 0 | 4334 | 0 |
| 2016 | 6288 | 6288 | 313 | 0 | 57.2 | 6288 | 6288 | 0 | 4554 | 0 |
| 2017 | 6613 | 6613 | 325 | 0 | 57.9 | 6613 | 6613 | 0 | 4795 | 0 |
| 2018 | 7002 | 7002 | 389 | 0 | 58.6 | 7002 | 7002 | 0 | 5093 | 0 |
| 2019 | 7446 | 7446 | 444 | 0 | 59.1 | 7446 | 7446 | 0 | 5388 | 0 |
| 2020 | 7837 | 7837 | 391 | 0 | 59.8 | 7837 | 7837 | 0 | 5645 | 0 |
| 2021 | 8246 | 8246 | 409 | 0 | 60.4 | 8246 | 8246 | 0 | 5911 | 0 |
| 2022 | 8671 | 8671 | 425 | 0 | 61.0 | 8671 | 8671 | 0 | 6190 | 0 |
| 2023 | 9179 | 9179 | 508 | 0 | 61.6 | 9179 | 9179 | 0 | 6616 | 0 |
| 2024 | 9660 | 9660 | 481 | 0 | 62.2 | 9660 | 9660 | 0 | 6950 | 0 |
| 2025 | 10000 | 10000 | 340 | 0 | 63.2 | 0 | 0 | 0 | 7013 | 0 |

## Interpretation

Warnings identify synthetic-data patterns that require documentation; they do not automatically invalidate the table.
The source contains one annual snapshot per beneficiary and should be joined to claims using beneficiary_id plus an appropriate service-year rule.

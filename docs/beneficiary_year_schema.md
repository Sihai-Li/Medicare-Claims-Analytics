# beneficiary_year schema

| position | column_name | source_column | data_type | role | definition |
| --- | --- | --- | --- | --- | --- |
| 1 | beneficiary_id | BENE_ID | TEXT | Primary key | Synthetic beneficiary identifier used across CMS files. |
| 2 | reference_year | BENE_ENROLLMT_REF_YR | INTEGER | Primary key | Calendar year represented by the enrollment record. |
| 3 | state_code | STATE_CODE | TEXT | Dimension | CMS beneficiary state code. |
| 4 | county_code | COUNTY_CD | TEXT | Dimension | CMS beneficiary county code. |
| 5 | zip_code | ZIP_CD | TEXT | Dimension | Beneficiary ZIP code; stored as text to preserve leading zeros. |
| 6 | birth_date | BENE_BIRTH_DT | DATE | Dimension | Beneficiary date of birth in ISO format. |
| 7 | death_date | BENE_DEATH_DT | DATE | Dimension | Beneficiary date of death when present, in ISO format. |
| 8 | age_at_year_end | AGE_AT_END_REF_YR | INTEGER | Dimension | Beneficiary age at the end of the reference year. |
| 9 | sex_code | SEX_IDENT_CD | TEXT | Dimension | CMS sex identification code. |
| 10 | race_code | BENE_RACE_CD | TEXT | Dimension | CMS beneficiary race code. |
| 11 | rti_race_code | RTI_RACE_CD | TEXT | Dimension | Research Triangle Institute race code. |
| 12 | original_entitlement_reason_code | ENTLMT_RSN_ORIG | TEXT | Dimension | Original reason for Medicare entitlement. |
| 13 | current_entitlement_reason_code | ENTLMT_RSN_CURR | TEXT | Dimension | Current reason for Medicare entitlement. |
| 14 | esrd_indicator | ESRD_IND | TEXT | Dimension | End-stage renal disease indicator. |
| 15 | part_a_coverage_months | BENE_HI_CVRAGE_TOT_MONS | INTEGER | Measure | Months with Part A coverage during the year. |
| 16 | part_b_coverage_months | BENE_SMI_CVRAGE_TOT_MONS | INTEGER | Measure | Months with Part B coverage during the year. |
| 17 | state_buyin_months | BENE_STATE_BUYIN_TOT_MONS | INTEGER | Measure | Months with state buy-in coverage during the year. |
| 18 | hmo_coverage_months | BENE_HMO_CVRAGE_TOT_MONS | INTEGER | Measure | Months with HMO or managed-care coverage. |
| 19 | part_d_coverage_months | PTD_PLAN_CVRG_MONS | INTEGER | Measure | Months with Part D plan coverage. |
| 20 | retiree_drug_subsidy_months | RDS_CVRG_MONS | INTEGER | Measure | Months with retiree drug subsidy coverage. |
| 21 | dual_eligible_months | DUAL_ELGBL_MONS | INTEGER | Measure | Months with Medicare-Medicaid dual eligibility. |
| 22 | coverage_start_date | COVSTART | DATE | Dimension | Coverage start date supplied by the source. |
| 23 | enrollment_source | ENRL_SRC | TEXT | Lineage | Enrollment source code. |
| 24 | sample_group | SAMPLE_GROUP | TEXT | Lineage | Synthetic sample group identifier. |
| 25 | enhanced_five_percent_flag | ENHANCED_FIVE_PERCENT_FLAG | TEXT | Lineage | Enhanced five-percent sample flag. |
| 26 | current_bic_code | CRNT_BIC_CD | TEXT | Dimension | Current beneficiary identification code. |
| 27 | valid_death_date_flag | VALID_DEATH_DT_SW | TEXT | Quality | Source indicator for a validated death date. |
| 28 | source_file | derived | TEXT | Lineage | Raw file from which the row was loaded. |

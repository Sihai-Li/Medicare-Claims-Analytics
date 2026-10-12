-- Portfolio definitions: eligible complete A+B FFS calendar months; 2016-2022 comparisons.
-- Readmissions are descriptive all-cause returns, not the CMS risk-standardized HWR measure.
CREATE VIEW observed_coverage AS
 SELECT service_category, MIN(service_start) observed_start, MAX(service_start) observed_end,
 COUNT(*) claim_count FROM claim_header GROUP BY service_category
 UNION ALL SELECT 'pde',MIN(service_date),MAX(service_date),COUNT(*) FROM prescription_event;

CREATE TABLE dim_year AS
 SELECT reference_year AS service_year,
 CASE WHEN reference_year BETWEEN 2016 AND 2022 THEN 'Primary comparison'
 ELSE 'Enrollment only or partial claims coverage' END AS coverage_label
 FROM beneficiary_year GROUP BY reference_year;
CREATE TABLE dim_service(service_category TEXT PRIMARY KEY,service_label TEXT,record_unit TEXT);
INSERT INTO dim_service VALUES
 ('inpatient','Inpatient','claim'),('outpatient','Outpatient','claim'),
 ('carrier','Professional / Carrier','claim'),('dme','DME','claim'),
 ('snf','Skilled nursing','claim'),('hha','Home health','claim'),('hospice','Hospice','claim'),
 ('pde','Prescription event','prescription event');
CREATE TABLE dim_cohort(cohort_key TEXT PRIMARY KEY,cohort_label TEXT,definition TEXT);
INSERT INTO dim_cohort VALUES
 ('esrd','ESRD indicated','Annual enrollment ESRD_IND=Y or 1; precedence over diabetes'),
 ('diabetes','Observed diabetes without ESRD','Any diagnosis E08/E09/E10/E11/E13 in same-year claims, no annual ESRD flag'),
 ('other','Other / no selected flag','Neither of the selected ESRD/diabetes flags');

CREATE TABLE beneficiary_cohort AS
 SELECT b.beneficiary_year_key,b.beneficiary_id,b.reference_year,
 CASE WHEN b.esrd_indicator IN ('1','Y') THEN 'esrd'
 WHEN COALESCE(c.diabetes,0)=1 THEN 'diabetes' ELSE 'other' END AS cohort_key,
 CASE WHEN b.age<18 THEN '0-17' WHEN b.age<65 THEN '18-64'
 WHEN b.age<75 THEN '65-74' WHEN b.age<85 THEN '75-84'
 WHEN b.age IS NOT NULL THEN '85+' ELSE 'Missing' END AS age_band
 FROM beneficiary_year b LEFT JOIN (
 SELECT beneficiary_id,CAST(substr(service_start,1,4) AS INTEGER) yr,
 MAX(has_diabetes) diabetes FROM claim_header WHERE header_conflict=0 GROUP BY beneficiary_id,yr
 ) c ON c.beneficiary_id=b.beneficiary_id AND c.yr=b.reference_year;
CREATE UNIQUE INDEX ux_cohort_key ON beneficiary_cohort(beneficiary_year_key);

CREATE TABLE eligible_claim AS
 SELECT h.*,m.beneficiary_year_key,c.cohort_key,c.age_band,
 CAST(substr(h.service_start,1,4) AS INTEGER) service_year,
 substr(h.service_start,1,7) service_month,
 CASE WHEN h.service_category='inpatient' AND h.pass_through_per_diem_cents IS NOT NULL
 AND h.utilization_days IS NOT NULL
 THEN h.payment_cents+h.pass_through_per_diem_cents*h.utilization_days
 WHEN h.service_category!='inpatient' THEN h.payment_cents END total_medicare_payment_cents,
 CASE WHEN h.admission_date IS NOT NULL AND h.discharge_date IS NOT NULL
 THEN CAST(julianday(h.discharge_date)-julianday(h.admission_date) AS INTEGER) END date_span_days
 FROM claim_header h JOIN member_month m
 ON m.beneficiary_id=h.beneficiary_id AND substr(m.month_start,1,7)=substr(h.service_start,1,7)
 JOIN beneficiary_cohort c USING(beneficiary_year_key)
 WHERE m.eligible_ffs=1 AND h.header_conflict=0
 AND h.service_start IS NOT NULL AND h.service_end>=h.service_start AND h.payment_cents IS NOT NULL;
CREATE INDEX ix_eligible_bene_year ON eligible_claim(beneficiary_id,service_year);

CREATE TABLE fact_member_month AS
 SELECT CAST(substr(m.month_start,1,4) AS INTEGER) service_year,
 substr(m.month_start,1,7) service_month,c.cohort_key,c.age_band,
 COUNT(*) member_months,SUM(m.eligible_ffs) eligible_ffs_member_months,
 SUM(m.eligible_part_d) eligible_part_d_member_months,
 SUM(CASE WHEN m.eligible_ffs=1 AND m.eligibility_basis!='monthly_codes' THEN 1 ELSE 0 END) inferred_ffs_member_months
 FROM member_month m JOIN beneficiary_cohort c USING(beneficiary_year_key)
 GROUP BY service_year,service_month,c.cohort_key,c.age_band;

CREATE TABLE fact_service_month AS
 SELECT service_year,service_month,service_category,cohort_key,age_band,
 COUNT(*) record_count,SUM(payment_cents)/100.0 base_payment,
 SUM(total_medicare_payment_cents)/100.0 total_medicare_payment,
 SUM(charge_cents)/100.0 charges,SUM(charge_cents IS NOT NULL) records_with_charge,
 SUM(CASE WHEN charge_cents>0 THEN payment_cents END)/100.0 matched_payment,
 SUM(CASE WHEN charge_cents>0 THEN charge_cents END)/100.0 matched_charge,
 SUM(date_span_days) date_span_days,SUM(date_span_days IS NOT NULL) claims_with_date_span,
 SUM(utilization_days) covered_days,NULL AS drug_total_cost
 FROM eligible_claim GROUP BY service_year,service_month,service_category,cohort_key,age_band
 UNION ALL
 SELECT CAST(substr(p.service_date,1,4) AS INTEGER),substr(p.service_date,1,7),'pde',c.cohort_key,c.age_band,
 COUNT(*),SUM(p.covered_plan_payment_cents+p.noncovered_plan_payment_cents)/100.0,
 NULL,NULL,0,NULL,NULL,NULL,0,NULL,SUM(p.total_cost_cents)/100.0
 FROM prescription_event p JOIN member_month m
 ON p.beneficiary_id=m.beneficiary_id AND substr(p.service_date,1,7)=substr(m.month_start,1,7)
 JOIN beneficiary_cohort c USING(beneficiary_year_key)
 WHERE m.eligible_part_d=1
 GROUP BY 1,2,4,5;

CREATE VIEW annual_service_metrics AS
 WITH denominator AS (
 SELECT service_year, SUM(eligible_ffs_member_months) ffs_months,
 SUM(eligible_part_d_member_months) part_d_months FROM fact_member_month
 WHERE service_year BETWEEN 2016 AND 2022 GROUP BY service_year
 )
 SELECT f.service_year,f.service_category,SUM(f.record_count) record_count,
 SUM(f.base_payment) base_payment,SUM(f.charges) charges,
 SUM(f.matched_payment)/NULLIF(SUM(f.matched_charge),0) paid_to_charge_ratio,
 CASE WHEN f.service_category='pde' THEN d.part_d_months ELSE d.ffs_months END eligible_member_months,
 SUM(f.base_payment)/NULLIF(CASE WHEN f.service_category='pde' THEN d.part_d_months ELSE d.ffs_months END,0) pmpm,
 SUM(f.record_count)*12000.0/NULLIF(CASE WHEN f.service_category='pde' THEN d.part_d_months ELSE d.ffs_months END,0) records_per_1000_member_years,
 SUM(f.date_span_days)*1.0/NULLIF(SUM(f.claims_with_date_span),0) mean_date_span_days
 FROM fact_service_month f JOIN denominator d USING(service_year)
 GROUP BY f.service_year,f.service_category;

-- Combine overlapping and same-day-boundary claims into temporal episodes across providers.
-- These are analytical proxies; do not assert a uniquely resolved clinical hospitalization.
INSERT INTO dq_exception(dataset,source_file,source_row,record_key,check_name,detail)
 SELECT service_category,source_file,source_row,claim_key,'invalid_stay_dates',
 'Excluded from episode construction; claim retained' FROM claim_header
 WHERE service_category='inpatient' AND
 (admission_date IS NULL OR discharge_date IS NULL OR discharge_date<admission_date OR beneficiary_id IS NULL);

CREATE TABLE episode_claim AS
 WITH ordered AS (
 SELECT h.*,MAX(discharge_date) OVER(
 PARTITION BY beneficiary_id ORDER BY admission_date,discharge_date,claim_key
 ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) prior_latest_discharge
 FROM claim_header h WHERE service_category='inpatient' AND beneficiary_id IS NOT NULL
 AND admission_date IS NOT NULL AND discharge_date>=admission_date
 ), boundaries AS (
 SELECT *,CASE WHEN prior_latest_discharge IS NULL OR admission_date>prior_latest_discharge
 THEN 1 ELSE 0 END new_episode FROM ordered
 ), numbered AS (
 SELECT *,SUM(new_episode) OVER(PARTITION BY beneficiary_id ORDER BY admission_date,discharge_date,claim_key
 ROWS UNBOUNDED PRECEDING) episode_number FROM boundaries
 )
 SELECT claim_key,beneficiary_id,beneficiary_id||'|episode:'||episode_number episode_key,
 admission_date,discharge_date,prior_latest_discharge FROM numbered;
CREATE UNIQUE INDEX ux_episode_claim ON episode_claim(claim_key);

CREATE TABLE stay_episode AS
 WITH totals AS (
 SELECT e.episode_key,e.beneficiary_id,MIN(h.admission_date) admission_date,
 MAX(h.discharge_date) discharge_date,COUNT(*) claim_count,SUM(h.payment_cents) payment_cents,
 MAX(h.header_conflict) header_conflict,
 MAX(CASE WHEN h.discharge_status IN ('20','40','41','42') THEN 1 ELSE 0 END) any_death_status
 FROM episode_claim e JOIN claim_header h USING(claim_key) GROUP BY e.episode_key,e.beneficiary_id
 ) SELECT *,CAST(julianday(discharge_date)-julianday(admission_date) AS INTEGER) date_span_days
 FROM totals;
CREATE UNIQUE INDEX ux_episode_key ON stay_episode(episode_key);

CREATE TABLE fact_readmission AS
 WITH next_stay AS (
 SELECT s.*,LEAD(admission_date) OVER(PARTITION BY beneficiary_id ORDER BY admission_date,discharge_date,episode_key) next_admission,
 LEAD(episode_key) OVER(PARTITION BY beneficiary_id ORDER BY admission_date,discharge_date,episode_key) next_episode_key
 FROM stay_episode s
 ), base AS (
 SELECT s.*,date(s.discharge_date,'+30 days') followup_end,
 CAST(substr(s.discharge_date,1,4) AS INTEGER) service_year,
 c.cohort_key,c.age_band,b.death_date,
 (SELECT MAX(service_start) FROM claim_header WHERE service_category='inpatient') observation_end,
 CAST(julianday(s.next_admission)-julianday(s.discharge_date) AS INTEGER) days_to_next
 FROM next_stay s LEFT JOIN beneficiary_year b
 ON b.beneficiary_id=s.beneficiary_id AND b.reference_year=CAST(substr(s.admission_date,1,4) AS INTEGER)
 LEFT JOIN beneficiary_cohort c ON c.beneficiary_id=s.beneficiary_id
 AND c.reference_year=CAST(substr(s.discharge_date,1,4) AS INTEGER)
 ), assessed AS (
 SELECT *,CASE
 WHEN header_conflict=1 THEN 'header_conflict'
 WHEN any_death_status=1 OR (death_date IS NOT NULL AND death_date<=followup_end) THEN 'death_before_followup_end'
 WHEN followup_end>observation_end THEN 'insufficient_observed_followup'
 WHEN cohort_key IS NULL THEN 'missing_beneficiary_year'
 WHEN (SELECT COUNT(*) FROM member_month m WHERE m.beneficiary_id=base.beneficiary_id
 AND m.month_start<=base.followup_end AND m.month_end>=base.admission_date AND m.eligible_ffs=1)
 != (CAST(strftime('%Y',followup_end) AS INTEGER)*12+CAST(strftime('%m',followup_end) AS INTEGER)
 -CAST(strftime('%Y',admission_date) AS INTEGER)*12-CAST(strftime('%m',admission_date) AS INTEGER)+1)
 THEN 'not_continuous_FFS_admission_to_followup'
 ELSE 'eligible' END eligibility_reason FROM base
 ) SELECT episode_key,beneficiary_id,service_year,cohort_key,age_band,admission_date,discharge_date,
 followup_end,next_admission,next_episode_key,days_to_next,claim_count,date_span_days,
 payment_cents/100.0 base_payment,eligibility_reason,
 CASE WHEN eligibility_reason='eligible' THEN 1 ELSE 0 END eligible_index,
 CASE WHEN eligibility_reason='eligible' AND days_to_next BETWEEN 1 AND 30 THEN 1 ELSE 0 END readmitted_30d,
 CASE WHEN claim_count>1 THEN 1 ELSE 0 END multiple_claims_episode
 FROM assessed;
CREATE VIEW readmission_summary AS
 SELECT service_year,COUNT(*) episodes,SUM(eligible_index) eligible_index_episodes,
 SUM(readmitted_30d) readmitted_episodes,
 SUM(readmitted_30d)*1.0/NULLIF(SUM(eligible_index),0) readmission_rate,
 SUM(multiple_claims_episode) merged_episodes
 FROM fact_readmission GROUP BY service_year;

CREATE TABLE fact_patient_year AS
 WITH payments AS (
 SELECT beneficiary_id,service_year,COUNT(*) claim_count,SUM(payment_cents)/100.0 base_payment,
 SUM(CASE WHEN service_category='inpatient' THEN 1 ELSE 0 END) inpatient_claim_count
 FROM eligible_claim GROUP BY beneficiary_id,service_year
 ), episodes AS (
 SELECT beneficiary_id,service_year,SUM(eligible_index) eligible_index_episodes,SUM(readmitted_30d) readmissions
 FROM fact_readmission GROUP BY beneficiary_id,service_year
 ), members AS (
 SELECT m.beneficiary_year_key,SUM(m.eligible_ffs) eligible_ffs_member_months
 FROM member_month m GROUP BY m.beneficiary_year_key
 ) SELECT b.beneficiary_year_key,b.beneficiary_id,b.reference_year service_year,c.cohort_key,c.age_band,
 b.sex_code,b.state_code,m.eligible_ffs_member_months,
 COALESCE(p.claim_count,0) claim_count,COALESCE(p.base_payment,0) base_payment,
 COALESCE(p.inpatient_claim_count,0) inpatient_claim_count,
 COALESCE(e.eligible_index_episodes,0) eligible_index_episodes,COALESCE(e.readmissions,0) readmissions
 FROM beneficiary_year b JOIN beneficiary_cohort c USING(beneficiary_year_key)
 JOIN members m USING(beneficiary_year_key)
 LEFT JOIN payments p ON p.beneficiary_id=b.beneficiary_id AND p.service_year=b.reference_year
 LEFT JOIN episodes e ON e.beneficiary_id=b.beneficiary_id AND e.service_year=b.reference_year;

CREATE TABLE fact_drg_year AS
 SELECT service_year,COALESCE(drg_code,'Missing') drg_code,COUNT(*) claim_count,
 SUM(payment_cents)/100.0 base_payment,SUM(charge_cents)/100.0 charges,
 SUM(date_span_days) date_span_days,SUM(date_span_days IS NOT NULL) claims_with_date_span
 FROM eligible_claim WHERE service_category='inpatient' GROUP BY service_year,drg_code;

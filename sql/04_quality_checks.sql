-- Full exceptions live in SQLite. CSV exception export is explicitly a 5,000-row sample.
INSERT INTO dq_exception(dataset,source_file,source_row,record_key,check_name,detail)
 SELECT h.service_category,l.source_file,l.source_row,l.source_record_key,'duplicate_line_candidate',
 'Claim ID + line number duplicated; original lines retained'
 FROM claim_line l JOIN claim_header h USING(claim_key)
 JOIN (SELECT claim_key,line_number FROM claim_line GROUP BY claim_key,line_number HAVING COUNT(*)>1) d
 ON l.claim_key=d.claim_key AND l.line_number IS d.line_number;
INSERT INTO dq_exception(dataset,source_file,source_row,record_key,check_name,detail)
 SELECT 'pde',p.source_file,p.source_row,p.source_record_key,'duplicate_prescription_event_id','Original events retained'
 FROM prescription_event p JOIN (SELECT event_id FROM prescription_event GROUP BY event_id HAVING COUNT(*)>1) d
 ON p.event_id=d.event_id;
INSERT INTO dq_exception(dataset,source_file,source_row,record_key,check_name,detail)
 SELECT h.service_category,h.source_file,h.source_row,h.claim_key,'missing_beneficiary_year',
 'No beneficiary-year at claim start year' FROM claim_header h LEFT JOIN beneficiary_year b
 ON h.beneficiary_id=b.beneficiary_id AND CAST(substr(h.service_start,1,4) AS INTEGER)=b.reference_year
 WHERE b.beneficiary_year_key IS NULL;
INSERT INTO dq_exception(dataset,source_file,source_row,record_key,check_name,detail)
 SELECT h.service_category,h.source_file,h.source_row,h.claim_key,'claim_outside_eligible_FFS_month',
 'Claim retained; excluded from FFS numerator' FROM claim_header h LEFT JOIN member_month m
 ON h.beneficiary_id=m.beneficiary_id AND substr(h.service_start,1,7)=substr(m.month_start,1,7)
 WHERE COALESCE(m.eligible_ffs,0)=0;
INSERT INTO dq_exception(dataset,source_file,source_row,record_key,check_name,detail)
 SELECT 'pde',p.source_file,p.source_row,p.source_record_key,'event_outside_eligible_part_D_month',
 'Event retained; excluded from Part D numerator' FROM prescription_event p LEFT JOIN member_month m
 ON p.beneficiary_id=m.beneficiary_id AND substr(p.service_date,1,7)=substr(m.month_start,1,7)
 WHERE COALESCE(m.eligible_part_d,0)=0;
INSERT INTO dq_exception(dataset,source_file,source_row,record_key,check_name,detail)
 SELECT h.service_category,h.source_file,h.source_row,h.claim_key,'missing_or_nonpositive_charge',
 'Payment retained; excluded from paid-to-charge matched denominator'
 FROM claim_header h WHERE charge_cents IS NULL OR charge_cents<=0;
INSERT INTO dq_exception(dataset,source_file,source_row,record_key,check_name,detail)
 SELECT h.service_category,h.source_file,h.source_row,h.claim_key,'inpatient_pass_through_unavailable',
 'Base payment known; total Medicare payment cannot be derived'
 FROM claim_header h WHERE service_category='inpatient'
 AND (pass_through_per_diem_cents IS NULL OR utilization_days IS NULL);
INSERT INTO dq_exception(dataset,source_file,source_row,record_key,check_name,detail)
 SELECT h.service_category,h.source_file,h.source_row,h.claim_key,'professional_line_payment_reconciliation',
 'Sum LINE_NCH_PMT_AMT differs from CLM_PMT_AMT; retain source values'
 FROM claim_header h JOIN (SELECT claim_key,SUM(line_payment_cents) amount FROM claim_line GROUP BY claim_key) l USING(claim_key)
 WHERE service_category IN ('carrier','dme') AND l.amount IS NOT NULL AND h.payment_cents!=l.amount;
CREATE TABLE fact_quality AS
 SELECT dataset,check_name,COUNT(*) exception_count FROM dq_exception GROUP BY dataset,check_name;

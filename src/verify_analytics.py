"""Verify exported star-schema facts and write independent Desktop comparison values."""
import csv
import json
from pathlib import Path
import sqlite3

ROOT=Path(__file__).resolve().parents[1]


def main():
    db=sqlite3.connect(f'file:{(ROOT/"data/processed/analytics.sqlite").as_posix()}?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    validations={}
    for table in ['dim_year','dim_cohort','dim_service','fact_member_month','fact_service_month',
                  'fact_patient_year','fact_readmission','fact_drg_year','fact_quality']:
        with (ROOT/'data/processed/powerbi'/f'{table}.csv').open(encoding='utf-8',newline='') as handle:
            exported=sum(1 for _ in csv.DictReader(handle))
        count=db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
        validations[f'{table}_export_rows']=exported==count
    validations['nonempty_medical_metrics']=db.execute('SELECT COUNT(*) FROM eligible_claim').fetchone()[0]>0
    validations['nonzero_ffs_denominator']=db.execute('SELECT SUM(eligible_ffs_member_months) FROM fact_member_month WHERE service_year BETWEEN 2016 AND 2022').fetchone()[0]>0
    validations['claim_patient_year_payment_reconciles']=abs(
        db.execute('SELECT SUM(base_payment) FROM fact_patient_year WHERE service_year BETWEEN 2016 AND 2022').fetchone()[0]
        -db.execute("SELECT SUM(base_payment) FROM fact_service_month WHERE service_category!='pde' AND service_year BETWEEN 2016 AND 2022").fetchone()[0])<0.01
    validations['member_cohort_keys_complete']=db.execute('SELECT COUNT(*) FROM fact_member_month f LEFT JOIN dim_cohort c USING(cohort_key) WHERE c.cohort_key IS NULL').fetchone()[0]==0
    validations['line_payment_no_header_double_count']=db.execute("SELECT COUNT(*) FROM claim_header WHERE service_category='inpatient'").fetchone()[0]==20867
    output=[]
    for label,condition in [('2022','=2022'),('2016-2022','BETWEEN 2016 AND 2022')]:
        counts=db.execute(f'''SELECT SUM(record_count) records,SUM(base_payment) payment,
          SUM(matched_payment) matched_payment,SUM(matched_charge) matched_charge
          FROM fact_service_month WHERE service_category!='pde' AND service_year {condition}''').fetchone()
        members=db.execute(f'''SELECT SUM(eligible_ffs_member_months) ffs,
          SUM(inferred_ffs_member_months) inferred,SUM(eligible_part_d_member_months) part_d
          FROM fact_member_month WHERE service_year {condition}''').fetchone()
        episodes=db.execute(f'''SELECT SUM(eligible_index) eligible,SUM(readmitted_30d) returns
          FROM fact_readmission WHERE service_year {condition}''').fetchone()
        rx=db.execute(f"SELECT SUM(base_payment) FROM fact_service_month WHERE service_category='pde' AND service_year {condition}").fetchone()[0]
        cohort=db.execute(f'''SELECT SUM(base_payment) FROM fact_patient_year
          WHERE service_year {condition}''').fetchone()[0]
        top_amount=0
        years=[2022] if label=='2022' else range(2016,2023)
        for year in years:
            n=db.execute('SELECT COUNT(*) FROM fact_patient_year WHERE service_year=? AND eligible_ffs_member_months>0',(year,)).fetchone()[0]
            import math
            top_amount+=db.execute('''SELECT SUM(base_payment) FROM (
              SELECT base_payment FROM fact_patient_year WHERE service_year=? AND eligible_ffs_member_months>0
              ORDER BY base_payment DESC,beneficiary_id ASC LIMIT ?)''',(year,math.ceil(n*0.1))).fetchone()[0]
        output.append({'selection':label,'medical_claim_payment':counts['payment'],'medical_claim_count':counts['records'],
          'eligible_ffs_member_months':members['ffs'],'inferred_ffs_member_months':members['inferred'],
          'medical_pmpm':counts['payment']/members['ffs'],
          'claims_per_1000_member_years':counts['records']*12000/members['ffs'],
          'paid_to_charge_ratio':counts['matched_payment']/counts['matched_charge'],
          'rx_plan_payment':rx,'rx_plan_pmpm':rx/members['part_d'],
          'eligible_index_episodes':episodes['eligible'],'readmitted_episodes':episodes['returns'],
          'all_cause_return_rate':episodes['returns']/episodes['eligible'],
          'top_10_percent_member_payment_share':top_amount/cohort})
    with (ROOT/'reports/powerbi_expected_values.csv').open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=output[0].keys());writer.writeheader();writer.writerows(output)
    result={'checks':validations,'desktop_reference_values':output}
    (ROOT/'reports/analytics_export_validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    db.close()
    print(json.dumps(result,indent=2))
    if not all(validations.values()):raise SystemExit(1)


if __name__=='__main__':main()

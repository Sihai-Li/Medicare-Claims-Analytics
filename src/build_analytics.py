"""Rebuild the complete analytics database without changing raw data or notebook outputs.

Run: python src/build_analytics.py
Amounts are exact integer cents. Exceptions are retained in SQLite with source locators.
"""
from __future__ import annotations

import argparse
import calendar
from collections import Counter
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ['inpatient', 'outpatient', 'carrier', 'dme', 'snf', 'hha', 'hospice']


def clean(value):
    return value.strip() or None if value is not None else None


@lru_cache(maxsize=100000)
def iso_date(value):
    if not value:
        return None
    return datetime.strptime(value, '%d-%b-%Y').date().isoformat()


def cents(value):
    if value is None:
        return None
    amount = Decimal(value) * 100
    if not amount.is_finite() or amount != amount.to_integral_value():
        raise ValueError('Amount must be finite with at most two decimal places')
    return int(amount)


def integer(value):
    if value is None:
        return None
    number = Decimal(value)
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError('Expected integer')
    return int(number)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


class Loader:
    def __init__(self, connection):
        self.db = connection
        self.exceptions = []
        self.counts = Counter()
        self.context = ('', '', 0, '')

    def issue(self, check, field='', raw=None, detail=''):
        dataset, filename, row, key = self.context
        self.exceptions.append((dataset, filename, row, key, check, field, raw, detail))
        self.counts[(dataset, check)] += 1
        if len(self.exceptions) >= 10000:
            self.flush()

    def flush(self):
        self.db.executemany('''INSERT INTO dq_exception
            (dataset,source_file,source_row,record_key,check_name,field,raw_value,detail)
            VALUES(?,?,?,?,?,?,?,?)''', self.exceptions)
        self.exceptions.clear()

    def parse(self, row, field, converter, required=False):
        raw = clean(row.get(field))
        if raw is None:
            if required:
                self.issue('missing_required_value', field)
            return None
        try:
            result = converter(raw)
        except (ValueError, InvalidOperation, OverflowError):
            self.issue('invalid_type', field, raw)
            return None
        if converter in (cents, integer) and result < 0:
            self.issue('negative_numeric_value', field, raw, 'Retained; review adjustments or source data')
        return result

    def source(self, path):
        with path.open(encoding='utf-8-sig', newline='') as handle:
            yield from enumerate(csv.DictReader(handle, delimiter='|'), start=2)

    def enrollment(self, path):
        rows = 0
        for source_row, row in self.source(path):
            bene = clean(row['BENE_ID'])
            yr = int(path.stem.split('_')[-1])
            key = f'{bene}|{yr}'
            self.context = ('beneficiary', path.name, source_row, key)
            actual_year = self.parse(row, 'BENE_ENROLLMT_REF_YR', integer, True)
            if actual_year != yr:
                self.issue('reference_year_mismatch', 'BENE_ENROLLMT_REF_YR', str(actual_year))
            if bene is None:
                self.issue('missing_beneficiary_id', 'BENE_ID')
                raise ValueError('Enrollment missing beneficiary ID; inspect raw source')
            birth = self.parse(row, 'BENE_BIRTH_DT', iso_date, True)
            death = self.parse(row, 'BENE_DEATH_DT', iso_date)
            coverage = self.parse(row, 'COVSTART', iso_date)
            age = self.parse(row, 'AGE_AT_END_REF_YR', integer)
            counts = [self.parse(row, f, integer) for f in
                      ['BENE_HI_CVRAGE_TOT_MONS','BENE_SMI_CVRAGE_TOT_MONS','BENE_HMO_CVRAGE_TOT_MONS']]
            if any(n is not None and not 0 <= n <= 12 for n in counts):
                self.issue('coverage_month_range', detail=str(counts))
            if age is not None and not 0 <= age <= 120:
                self.issue('age_range', 'AGE_AT_END_REF_YR', str(age))
            self.db.execute('INSERT INTO beneficiary_year VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (key,bene,yr,birth,death,coverage,age,clean(row.get('SEX_IDENT_CD')),
                 clean(row.get('STATE_CODE')),clean(row.get('ESRD_IND')),*counts))
            monthly_a = monthly_b = 0
            if all(clean(row.get(f'HMO_IND_{m:02}')) is None for m in range(1,13)):
                self.issue('monthly_hmo_unavailable', detail='Annual zero-HMO total used only when known; eligibility_basis records inference')
            for month in range(1,13):
                first = date(yr,month,1).isoformat()
                last = date(yr,month,calendar.monthrange(yr,month)[1]).isoformat()
                ent = clean(row.get(f'MDCR_ENTLMT_BUYIN_IND_{month:02}'))
                hmo = clean(row.get(f'HMO_IND_{month:02}'))
                contract = clean(row.get(f'PTD_CNTRCT_ID_{month:02}'))
                monthly_a += ent in {'1','3','A','C'}
                monthly_b += ent in {'2','3','B','C'}
                reasons = []
                basis = []
                both_ab = ent in {'3','C'}
                ffs = hmo in {'0','4'}
                if ent is None and counts[0]==12 and counts[1]==12:
                    both_ab = True
                    basis.append('annual_full_A_B_inference')
                if hmo is None and counts[2]==0:
                    ffs = True
                    basis.append('annual_zero_HMO_inference')
                if ent is not None and ent not in {'0','1','2','3','A','B','C'}:
                    self.issue('unknown_entitlement_code', f'MDCR_ENTLMT_BUYIN_IND_{month:02}', ent)
                if hmo is not None and hmo not in {'0','1','2','4','A','B','C'}:
                    self.issue('unknown_hmo_code', f'HMO_IND_{month:02}', hmo)
                if not both_ab: reasons.append('not_both_A_B')
                if not ffs: reasons.append('not_confirmed_FFS')
                # Conservative complete calendar month rule; partial boundary months excluded.
                if birth is None or birth > first: reasons.append('birth_boundary')
                if coverage is None or coverage > first: reasons.append('coverage_boundary')
                if death and death < last: reasons.append('death_boundary')
                eligible = int(not reasons)
                self.db.execute('INSERT INTO member_month VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (f'{bene}|{first[:7]}',key,bene,first,last,ent,hmo,contract,eligible,
                     int(eligible and contract is not None and contract not in {'0','N','NA'}),
                     ';'.join(reasons) or 'eligible',';'.join(basis) or 'monthly_codes',path.name,source_row))
            if counts[0] != monthly_a or counts[1] != monthly_b:
                self.issue('annual_monthly_coverage_disagreement', detail=f'A:{counts[0]}/{monthly_a};B:{counts[1]}/{monthly_b}')
            rows += 1
        self.inventory(path,'beneficiary',rows,rows,None,None)

    def inventory(self,path,dataset,rows,headers,start,end):
        self.db.execute('INSERT INTO source_inventory VALUES(?,?,?,?,?,?,?)',
                        (path.name,dataset,rows,headers,sha256(path),start,end))

    def claims(self,path,service):
        headers = {}
        lines = []
        diagnoses = []
        conflicts = set()
        rows = 0
        observed_start = observed_end = None
        for source_row,row in self.source(path):
            cid = clean(row.get('CLM_ID'))
            key = f'{service}|{cid}' if cid else f'{service}|missing@{source_row}'
            self.context = (service,path.name,source_row,key)
            if cid is None: self.issue('missing_claim_id','CLM_ID')
            bene = clean(row.get('BENE_ID'))
            if bene is None: self.issue('missing_beneficiary_id','BENE_ID')
            start = self.parse(row,'CLM_FROM_DT',iso_date,True)
            end = self.parse(row,'CLM_THRU_DT',iso_date,True)
            if start:
                observed_start = min(observed_start or start,start)
                observed_end = max(observed_end or start,start)
            if start and end and end < start: self.issue('claim_date_order')
            admission = self.parse(row,'CLM_ADMSN_DT',iso_date,service=='inpatient')
            discharge = self.parse(row,'NCH_BENE_DSCHRG_DT',iso_date,service=='inpatient')
            payment = self.parse(row,'CLM_PMT_AMT',cents,True)
            charge_field = 'NCH_CARR_CLM_SBMTD_CHRG_AMT' if service in {'carrier','dme'} else 'CLM_TOT_CHRG_AMT'
            charge = self.parse(row,charge_field,cents)
            util = self.parse(row,'CLM_UTLZTN_DAY_CNT',integer)
            nonutil = self.parse(row,'CLM_NON_UTLZTN_DAYS_CNT',integer)
            passthrough = self.parse(row,'CLM_PASS_THRU_PER_DIEM_AMT',cents)
            codes = {clean(row.get('PRNCPAL_DGNS_CD'))}
            codes.update(clean(row.get(f'ICD_DGNS_CD{i}')) for i in range(1,26))
            codes.discard(None)
            diabetes = int(any(c.startswith(('E08','E09','E10','E11','E13')) for c in codes))
            hf = int(any(c.startswith('I50') for c in codes))
            copd = int(any(c.startswith(('J43','J44')) for c in codes))
            values = (key,service,cid,bene,start,end,admission,discharge,payment,charge,
                      passthrough,util,nonutil,clean(row.get('PTNT_DSCHRG_STUS_CD')),
                      clean(row.get('PRVDR_NUM')),clean(row.get('ORG_NPI_NUM')) or clean(row.get('PRVDR_NPI')),
                      clean(row.get('CLM_DRG_CD')),clean(row.get('PRNCPAL_DGNS_CD')),
                      diabetes,hf,copd)
            signature = (values,tuple(sorted(codes)))
            if key not in headers:
                headers[key] = signature
                self.db.execute('INSERT INTO claim_header VALUES('+','.join('?'*24)+')',
                                (*values,0,path.name,source_row))
                diagnoses.extend((key,code) for code in codes)
                if admission and discharge:
                    if discharge < admission: self.issue('admission_discharge_order')
                    elif util is not None and util != (date.fromisoformat(discharge)-date.fromisoformat(admission)).days:
                        self.issue('los_utilization_difference', detail='Date span and covered utilization are separate measures')
            elif headers[key] != signature:
                conflicts.add(key)
                self.issue('claim_header_conflict',detail='All lines retained; first header excluded from eligible metrics')
                diagnoses.extend((key,code) for code in codes)
            line_field = 'LINE_NUM' if service in {'carrier','dme'} else 'CLM_LINE_NUM'
            line_number = self.parse(row,line_field,integer,True)
            if line_number is not None and line_number < 1: self.issue('invalid_line_number',line_field,str(line_number))
            line_start = self.parse(row,'LINE_1ST_EXPNS_DT' if service in {'carrier','dme'} else 'REV_CNTR_DT',iso_date)
            line_end = self.parse(row,'LINE_LAST_EXPNS_DT',iso_date)
            lp = self.parse(row,'LINE_NCH_PMT_AMT' if service in {'carrier','dme'} else 'REV_CNTR_PMT_AMT_AMT',cents)
            lc = self.parse(row,'LINE_SBMTD_CHRG_AMT' if service in {'carrier','dme'} else 'REV_CNTR_TOT_CHRG_AMT',cents)
            lines.append((f'{service}|row:{source_row}',key,line_number,clean(row.get('REV_CNTR')),
                          clean(row.get('HCPCS_CD')),line_start,line_end,lp,lc,path.name,source_row))
            if len(lines)>=10000:
                self.db.executemany('INSERT INTO claim_line VALUES('+','.join('?'*11)+')',lines)
                self.db.executemany('INSERT OR IGNORE INTO claim_diagnosis VALUES(?,?)',diagnoses)
                lines.clear(); diagnoses.clear()
            rows += 1
        self.db.executemany('INSERT INTO claim_line VALUES('+','.join('?'*11)+')',lines)
        self.db.executemany('INSERT OR IGNORE INTO claim_diagnosis VALUES(?,?)',diagnoses)
        self.db.executemany('UPDATE claim_header SET header_conflict=1 WHERE claim_key=?',[(k,) for k in conflicts])
        self.inventory(path,service,rows,len(headers),observed_start,observed_end)
        print(f'{service}: {rows:,} source lines -> {len(headers):,} claims',flush=True)

    def prescriptions(self,path):
        rows = 0
        batch = []
        first = last = None
        for source_row,row in self.source(path):
            key = f'pde|row:{source_row}'
            self.context = ('pde',path.name,source_row,key)
            event_id = clean(row.get('PDE_ID'))
            if not event_id: self.issue('missing_event_id','PDE_ID')
            service_date = self.parse(row,'SRVC_DT',iso_date,True)
            if service_date:
                first=min(first or service_date,service_date);last=max(last or service_date,service_date)
            amounts = [self.parse(row,f,cents) for f in ['TOT_RX_CST_AMT','CVRD_D_PLAN_PD_AMT',
                       'NCVRD_PLAN_PD_AMT','PTNT_PAY_AMT','PLRO_AMT']]
            quantity = self.parse(row,'QTY_DSPNSD_NUM',float)
            batch.append((key,event_id,clean(row.get('BENE_ID')),service_date,
                          clean(row.get('PROD_SRVC_ID')),self.parse(row,'DAYS_SUPLY_NUM',integer),
                          quantity,*amounts,path.name,source_row))
            if len(batch)>=10000:
                self.db.executemany('INSERT INTO prescription_event VALUES('+','.join('?'*14)+')',batch)
                batch.clear()
            rows += 1
        self.db.executemany('INSERT INTO prescription_event VALUES('+','.join('?'*14)+')',batch)
        self.inventory(path,'pde',rows,rows,first,last)
        print(f'pde: {rows:,} events',flush=True)


def write_query_csv(db,query,path):
    cursor=db.execute(query)
    with path.open('w',encoding='utf-8',newline='') as handle:
        writer=csv.writer(handle)
        writer.writerow([col[0] for col in cursor.description])
        writer.writerows(cursor)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir',type=Path,default=ROOT/'data/raw')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'data/processed')
    args=parser.parse_args()
    paths=sorted(args.raw_dir.glob('beneficiary_*.csv'))
    if len(paths)!=11: raise ValueError('Expected 11 beneficiary source files')
    for service in SERVICES+['pde']:
        if not (args.raw_dir/f'{service}.csv').exists(): raise FileNotFoundError(service)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    staging=args.output_dir/'analytics_build.sqlite'
    if staging.exists(): staging.unlink()  # Exact disposable build path, never notebook database.
    with sqlite3.connect(staging) as db:
        db.executescript((ROOT/'sql/02_analytics_schema.sql').read_text())
        loader=Loader(db)
        for path in paths:
            print(f'Enrollment: {path.name}',flush=True)
            loader.enrollment(path)
        db.commit()
        for service in SERVICES:
            loader.claims(args.raw_dir/f'{service}.csv',service)
            loader.flush();db.commit()
        loader.prescriptions(args.raw_dir/'pde.csv')
        loader.flush();db.commit()
        db.executescript((ROOT/'sql/03_metrics.sql').read_text())
        db.executescript((ROOT/'sql/04_quality_checks.sql').read_text())
        exports=args.output_dir/'powerbi'
        exports.mkdir(exist_ok=True)
        for table in ['dim_year','dim_service','dim_cohort','fact_member_month','fact_service_month',
                      'fact_readmission','fact_patient_year','fact_drg_year','fact_quality']:
            write_query_csv(db,f'SELECT * FROM {table}',exports/f'{table}.csv')
        reports=ROOT/'reports'
        write_query_csv(db,'SELECT * FROM source_inventory',reports/'analytics_source_inventory.csv')
        write_query_csv(db,'SELECT * FROM fact_quality',reports/'analytics_quality_summary.csv')
        write_query_csv(db,'SELECT * FROM dq_exception LIMIT 5000',reports/'analytics_exception_samples.csv')
        write_query_csv(db,'SELECT * FROM annual_service_metrics',reports/'analytics_annual_service_metrics.csv')
        write_query_csv(db,'SELECT * FROM readmission_summary',reports/'analytics_readmissions.csv')
        write_query_csv(db,'SELECT * FROM observed_coverage',reports/'analytics_observed_coverage.csv')
        checks=verify(db)
        (reports/'analytics_validation.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    if not all(checks['checks'].values()):
        db.close()
        raise RuntimeError('Validation failed; staging database retained, see analytics_validation.json')
    # sqlite3 connection context managers commit but do not close file handles.
    db.close()
    staging.replace(args.output_dir/'analytics.sqlite')
    print(json.dumps(checks,indent=2),flush=True)


def verify(db):
    scalar=lambda sql: db.execute(sql).fetchone()[0]
    counts={name:scalar(f'SELECT COUNT(*) FROM {name}') for name in
            ['beneficiary_year','member_month','claim_header','claim_line','prescription_event','stay_episode','fact_readmission']}
    raw_claims=scalar("SELECT SUM(source_rows) FROM source_inventory WHERE dataset NOT IN ('pde','beneficiary')")
    raw_pde=scalar("SELECT SUM(source_rows) FROM source_inventory WHERE dataset='pde'")
    checks={
        'claim_source_rows_preserved':counts['claim_line']==raw_claims,
        'prescription_source_rows_preserved':counts['prescription_event']==raw_pde,
        'foreign_key_integrity':len(db.execute('PRAGMA foreign_key_check').fetchall())==0,
        'database_integrity':scalar('PRAGMA integrity_check')=='ok',
        'no_missing_member_months':counts['member_month']==counts['beneficiary_year']*12,
        'line_header_referential_integrity':scalar('SELECT COUNT(*) FROM claim_line l LEFT JOIN claim_header h USING(claim_key) WHERE h.claim_key IS NULL')==0,
        'readmission_flags_only_on_eligible_index':scalar('SELECT COUNT(*) FROM fact_readmission WHERE readmitted_30d=1 AND eligible_index=0')==0,
        'every_inpatient_claim_in_episode_or_exception':scalar("SELECT COUNT(*) FROM claim_header WHERE service_category='inpatient'")==scalar('SELECT COUNT(*) FROM episode_claim')+scalar("SELECT COUNT(DISTINCT record_key) FROM dq_exception WHERE check_name='invalid_stay_dates'"),
    }
    return {'counts':counts,'claims_pde_source_rows':raw_claims+raw_pde,
            'distinct_beneficiaries':scalar('SELECT COUNT(DISTINCT beneficiary_id) FROM beneficiary_year'),
            'source_files':scalar('SELECT COUNT(*) FROM source_inventory'), 'checks':checks}


if __name__=='__main__':
    main()

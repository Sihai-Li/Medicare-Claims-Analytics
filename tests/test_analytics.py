"""Boundary tests for money, FFS enrollment, and temporal all-cause readmissions."""
from datetime import date
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from build_analytics import cents, integer, Loader


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.executescript((ROOT/'sql/02_analytics_schema.sql').read_text())

    def tearDown(self):
        self.db.close()

    def member(self,bene,death=None):
        for yr in [2019,2020,2021]:
            key=f'{bene}|{yr}'
            self.db.execute('INSERT INTO beneficiary_year VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (key,bene,yr,'1950-01-01',death,'2010-01-01',yr-1950,'1','01','0',12,12,0))
            for month in range(1,13):
                start=date(yr,month,1).isoformat()
                import calendar
                end=date(yr,month,calendar.monthrange(yr,month)[1]).isoformat()
                self.db.execute('INSERT INTO member_month VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (f'{bene}|{start[:7]}',key,bene,start,end,'3','0','Z0001',1,1,'eligible','monthly_codes','fixture',2))

    def claim(self,cid,bene,admit,discharge,payment=10000,status='1'):
        values=(cid,'inpatient',cid,bene,admit,discharge,admit,discharge,payment,payment,0,
                1,0,status,'001','999','951','Z951',0,0,0,0,'fixture',2)
        self.db.execute('INSERT INTO claim_header VALUES('+','.join('?'*24)+')',values)

    def metrics(self):
        self.db.executescript((ROOT/'sql/03_metrics.sql').read_text())

    def test_exact_money(self):
        self.assertEqual(cents('598716.31'),59871631)
        self.assertEqual(cents('-0.01'),-1)
        self.assertEqual(cents('0'),0)
        for value in ['0.001','NaN','Infinity','abc']:
            with self.assertRaises((ValueError,ArithmeticError)): cents(value)
        with self.assertRaises(ValueError): integer('1.5')

    def test_overlap_same_day_and_cross_year_followup(self):
        for bene in ['A','B','anchor']: self.member(bene)
        self.claim('a1','A','2020-01-01','2020-01-10')
        self.claim('a2','A','2020-01-05','2020-01-06')
        self.claim('a3','A','2020-01-10','2020-01-11')
        self.claim('a4','A','2020-02-10','2020-02-12')  # exactly 30 days
        self.claim('b1','B','2020-12-20','2020-12-21')
        self.claim('b2','B','2021-01-20','2021-01-22')  # across year, 30 days
        self.claim('cutoff','anchor','2021-04-01','2021-04-02')
        self.metrics()
        a=self.db.execute("SELECT claim_count,readmitted_30d FROM fact_readmission WHERE beneficiary_id='A' ORDER BY admission_date").fetchall()
        self.assertEqual(a,[(3,1),(1,0)])
        self.assertEqual(self.db.execute("SELECT readmitted_30d FROM fact_readmission WHERE beneficiary_id='B' ORDER BY admission_date LIMIT 1").fetchone()[0],1)
        self.assertEqual(self.db.execute("SELECT eligible_index FROM fact_readmission WHERE beneficiary_id='anchor'").fetchone()[0],0)

    def test_31_day_gap_death_and_enrollment_exclusions(self):
        for bene in ['A','B','C','anchor']: self.member(bene,'2020-01-20' if bene=='B' else None)
        self.claim('a1','A','2020-01-01','2020-01-02')
        self.claim('a2','A','2020-02-02','2020-02-03')  # 31 days, not readmission
        self.claim('b1','B','2020-01-01','2020-01-02')
        self.claim('c1','C','2020-01-01','2020-01-02')
        self.db.execute("UPDATE member_month SET eligible_ffs=0 WHERE beneficiary_id='C' AND month_start='2020-02-01'")
        self.claim('anchor','anchor','2020-12-01','2020-12-02')
        self.metrics()
        rows=self.db.execute('SELECT beneficiary_id,eligibility_reason,readmitted_30d FROM fact_readmission WHERE admission_date=\'2020-01-01\'').fetchall()
        mapping={r[0]:r[1:] for r in rows}
        self.assertEqual(mapping['A'],('eligible',0))
        self.assertEqual(mapping['B'],('death_before_followup_end',0))
        self.assertEqual(mapping['C'],('not_continuous_FFS_admission_to_followup',0))

    def test_normalization_does_not_repeat_header_money(self):
        raw='BENE_ID|CLM_ID|CLM_FROM_DT|CLM_THRU_DT|CLM_LINE_NUM|CLM_PMT_AMT|CLM_TOT_CHRG_AMT\n'
        raw+='A|x|01-Jan-2020|01-Jan-2020|1|10.10|20.20\n'
        raw+='A|x|01-Jan-2020|01-Jan-2020|2|10.10|20.20\n'
        with tempfile.TemporaryDirectory(dir=ROOT/'data/processed') as folder:
            path=Path(folder)/'outpatient.csv';path.write_text(raw)
            loader=Loader(self.db);loader.claims(path,'outpatient');loader.flush()
        self.assertEqual(self.db.execute('SELECT COUNT(*),SUM(payment_cents) FROM claim_header').fetchone(),(1,1010))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM claim_line').fetchone()[0],2)

    def test_month_boundary_and_unknown_hmo_are_excluded(self):
        fields=['BENE_ID','BENE_ENROLLMT_REF_YR','BENE_BIRTH_DT','COVSTART','AGE_AT_END_REF_YR',
                'BENE_HI_CVRAGE_TOT_MONS','BENE_SMI_CVRAGE_TOT_MONS','BENE_HMO_CVRAGE_TOT_MONS']
        values=['A','2020','15-Jan-2020','15-Jan-2020','0','12','12','0']
        for month in range(1,13):
            fields.extend([f'MDCR_ENTLMT_BUYIN_IND_{month:02}',f'HMO_IND_{month:02}',f'PTD_CNTRCT_ID_{month:02}'])
            values.extend(['3','?' if month==3 else '0','Z0001'])
        with tempfile.TemporaryDirectory(dir=ROOT/'data/processed') as folder:
            path=Path(folder)/'beneficiary_2020.csv';path.write_text('|'.join(fields)+'\n'+'|'.join(values)+'\n')
            loader=Loader(self.db);loader.enrollment(path);loader.flush()
        eligible=dict(self.db.execute('SELECT month_start,eligible_ffs FROM member_month'))
        self.assertEqual(eligible['2020-01-01'],0)
        self.assertEqual(eligible['2020-02-01'],1)
        self.assertEqual(eligible['2020-03-01'],0)

    def test_blank_hmo_uses_only_known_annual_zero_and_retains_raw_null(self):
        fields=['BENE_ID','BENE_ENROLLMT_REF_YR','BENE_BIRTH_DT','COVSTART','AGE_AT_END_REF_YR',
                'BENE_HI_CVRAGE_TOT_MONS','BENE_SMI_CVRAGE_TOT_MONS','BENE_HMO_CVRAGE_TOT_MONS']
        fields += [f'MDCR_ENTLMT_BUYIN_IND_{m:02}' for m in range(1,13)]
        base=['2020','01-Jan-1950','01-Jan-2010','70','12','12']
        # Explicit annual zero allows inference; annual positive or absent does not.
        rows=[['A',*base,'0',*(['3']*12)],['B',*base,'1',*(['3']*12)],['C',*base,'',*(['3']*12)]]
        with tempfile.TemporaryDirectory(dir=ROOT/'data/processed') as folder:
            path=Path(folder)/'beneficiary_2020.csv'
            path.write_text('|'.join(fields)+'\n'+'\n'.join('|'.join(r) for r in rows)+'\n')
            loader=Loader(self.db);loader.enrollment(path);loader.flush()
        result=dict(self.db.execute('SELECT beneficiary_id,SUM(eligible_ffs) FROM member_month GROUP BY beneficiary_id'))
        self.assertEqual(result,{'A':12,'B':0,'C':0})
        self.assertEqual(self.db.execute("SELECT hmo_code,eligibility_basis FROM member_month WHERE beneficiary_id='A' LIMIT 1").fetchone(),(None,'annual_zero_HMO_inference'))


if __name__=='__main__': unittest.main()

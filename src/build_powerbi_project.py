"""Generate a three-page PBIP with a star model, Power Query partitions, and explicit DAX.

The generated project requires Power BI Desktop refresh/render validation.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import shutil
import uuid

ROOT=Path(__file__).resolve().parents[1]
SCHEMA='https://developer.microsoft.com/json-schemas/fabric/item/'
TABLES=['dim_year','dim_service','dim_cohort','fact_member_month','fact_service_month',
        'fact_readmission','fact_patient_year','fact_drg_year','fact_quality']
INTEGER_FIELDS={'service_year','member_months','eligible_ffs_member_months','eligible_part_d_member_months',
 'record_count','records_with_charge','date_span_days','claims_with_date_span','covered_days','claim_count',
 'eligible_index','readmitted_30d','multiple_claims_episode','days_to_next','inpatient_claim_count',
 'eligible_index_episodes','readmissions','exception_count','inferred_ffs_member_months'}
NUMERIC_FIELDS={'base_payment','charges','matched_payment','matched_charge','total_medicare_payment','drug_total_cost'}
MEASURES=[
 ('Medical Claim Payment','CALCULATE(SUM(fact_service_month[base_payment]), KEEPFILTERS(dim_service[service_category] <> "pde"))','$#,0'),
 ('Medical Claim Count','CALCULATE(SUM(fact_service_month[record_count]), KEEPFILTERS(dim_service[service_category] <> "pde"))','#,0'),
 ('Rx Plan Payment','CALCULATE(SUM(fact_service_month[base_payment]), KEEPFILTERS(dim_service[service_category] = "pde"))','$#,0'),
 ('Eligible FFS Member Months','SUM(fact_member_month[eligible_ffs_member_months])','#,0'),
 ('Eligible Part D Member Months','SUM(fact_member_month[eligible_part_d_member_months])','#,0'),
 ('Medical PMPM','DIVIDE([Medical Claim Payment], [Eligible FFS Member Months])','$#,0.00'),
 ('Rx Plan PMPM','DIVIDE([Rx Plan Payment], [Eligible Part D Member Months])','$#,0.00'),
 ('Claims per 1000 Member Years','DIVIDE([Medical Claim Count] * 12000, [Eligible FFS Member Months])','#,0.0'),
 ('Paid to Charge Ratio','DIVIDE(SUM(fact_service_month[matched_payment]), SUM(fact_service_month[matched_charge]))','0.0%'),
 ('Mean Inpatient Date Span','DIVIDE(CALCULATE(SUM(fact_service_month[date_span_days]), KEEPFILTERS(dim_service[service_category] = "inpatient")), CALCULATE(SUM(fact_service_month[claims_with_date_span]), KEEPFILTERS(dim_service[service_category] = "inpatient")))','0.00'),
 ('Eligible Index Episodes','SUM(fact_readmission[eligible_index])','#,0'),
 ('30 Day Readmitted Episodes','SUM(fact_readmission[readmitted_30d])','#,0'),
 ('30 Day All Cause Return Rate','DIVIDE([30 Day Readmitted Episodes], [Eligible Index Episodes])','0.0%'),
 ('Temporal Episodes','COUNTROWS(fact_readmission)','#,0'),
 ('DRG Claim Payment','SUM(fact_drg_year[base_payment])','$#,0'),
 ('DRG Claim Count','SUM(fact_drg_year[claim_count])','#,0'),
 ('Annual Medical Payment per Eligible Member','DIVIDE(SUM(fact_patient_year[base_payment]), CALCULATE(COUNTROWS(fact_patient_year), fact_patient_year[eligible_ffs_member_months] > 0))','$#,0'),
 ('Top 10 Percent Member Payment Share', '''DIVIDE(
 SUMX(VALUES(dim_year[service_year]),
     VAR Patients = FILTER(CALCULATETABLE(fact_patient_year), fact_patient_year[eligible_ffs_member_months] > 0)
     VAR N = ROUNDUP(COUNTROWS(Patients) * 0.10, 0)
     RETURN SUMX(TOPN(N, Patients, fact_patient_year[base_payment], DESC, fact_patient_year[beneficiary_id], ASC), fact_patient_year[base_payment])
 ), SUM(fact_patient_year[base_payment]))''','0.0%'),
 ('Quality Exceptions All Source Years','SUM(fact_quality[exception_count])','#,0'),
]


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')


def make_model(data_folder):
    tables=[]
    for name in TABLES:
        with (data_folder/f'{name}.csv').open(encoding='utf-8',newline='') as handle:
            columns=next(csv.reader(handle))
        definitions=[];m_types=[]
        for col in columns:
            dtype='int64' if col in INTEGER_FIELDS else 'double' if col in NUMERIC_FIELDS else 'string'
            mtype='Int64.Type' if dtype=='int64' else 'type number' if dtype=='double' else 'type text'
            definitions.append({'name':col,'dataType':dtype,'sourceColumn':col,'summarizeBy':'none'})
            m_types.append('{"'+col+'", '+mtype+'}')
        expression=[
            'let',
            f'    Source = Csv.Document(File.Contents(DataFolder & "{name}.csv"), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),',
            '    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),',
            '    Nulls = Table.ReplaceValue(Headers, "", null, Replacer.ReplaceValue, Table.ColumnNames(Headers)),',
            '    Typed = Table.TransformColumnTypes(Nulls, {'+', '.join(m_types)+'}, "en-US")',
        ]
        if 'service_year' in columns:
            expression[-1]+=','
            expression+=['    AnalysisPeriod = Table.SelectRows(Typed, each [service_year] >= 2016 and [service_year] <= 2022)',
                         'in','    AnalysisPeriod']
        else: expression+=['in','    Typed']
        tables.append({'name':name,'columns':definitions,'partitions':[{'name':name,'mode':'import',
                         'source':{'type':'m','expression':expression}}]})
    tables[0]['measures']=[{'name':n,'expression':e,'formatString':f,'displayFolder':'Portfolio metrics'} for n,e,f in MEASURES]
    relationships=[]
    for fact in [n for n in TABLES if n.startswith('fact_')]:
        columns={c['name'] for c in next(t for t in tables if t['name']==fact)['columns']}
        for dim,key in [('dim_year','service_year'),('dim_service','service_category'),('dim_cohort','cohort_key')]:
            if key in columns:
                relationships.append({'name':str(uuid.uuid5(uuid.NAMESPACE_URL,f'{fact}:{dim}')),
                    'fromTable':fact,'fromColumn':key,'toTable':dim,'toColumn':key,
                    'fromCardinality':'many','toCardinality':'one','crossFilteringBehavior':'oneDirection'})
    return {'name':'MedicareAnalytics','compatibilityLevel':1567,
        'model':{'culture':'en-US','sourceQueryCulture':'en-US','defaultPowerBIDataSourceVersion':'powerBI_V3',
                 'discourageImplicitMeasures':True,
                 'expressions':[{'name':'DataFolder','kind':'m','expression':
                     '"'+str(data_folder).replace('\\','/')+'/" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'}],
                 'tables':tables,'relationships':relationships}}


def field(table,column,measure=False):
    return {'Measure' if measure else 'Column':{'Expression':{'SourceRef':{'Entity':table}},'Property':column}}


def projection(table,column,measure=False):
    return {'field':field(table,column,measure),'queryRef':f'{table}.{column}','nativeQueryRef':column}


def visual(name,vtype,title,x,y,w,h,roles):
    if vtype=='card':
        vtype='cardVisual'
        roles={'Data':roles['Values']}
    return {'$schema':SCHEMA+'report/definition/visualContainer/2.1.0/schema.json',
        'name':name,'position':{'x':x,'y':y,'width':w,'height':h,'z':0,'tabOrder':0},
        'visual':{'visualType':vtype,'query':{'queryState':{
            role:{'projections':[projection(*item) for item in values]} for role,values in roles.items()}},
            'visualContainerObjects':{'title':[{'properties':{
                'show':{'expr':{'Literal':{'Value':'true'}}},
                'text':{'expr':{'Literal':{'Value':"'"+title.replace("'","''")+"'"}}},
                'fontSize':{'expr':{'Literal':{'Value':'13D'}}}}}]}}}


def text_visual(name,text,x,y,w,h,size=12):
    return {'$schema':SCHEMA+'report/definition/visualContainer/2.1.0/schema.json',
        'name':name,'position':{'x':x,'y':y,'width':w,'height':h,'z':0,'tabOrder':0},
        'visual':{'visualType':'textbox','objects':{'general':[{'properties':{'paragraphs':[
            {'textRuns':[{'value':text,'textStyle':{'fontSize':f'{size}pt','fontFamily':'Segoe UI'}}]}
        ]}}]}}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-only',action='store_true',help='Preserve the already-refreshed semantic model')
    args=parser.parse_args()
    output=ROOT/'powerbi'
    data=ROOT/'data/processed/powerbi'
    model_folder=output/'Medicare.SemanticModel'
    report_folder=output/'Medicare.Report'
    if not args.report_only:
        dump(model_folder/'model.bim',make_model(data))
        dump(model_folder/'definition.pbism',{'$schema':SCHEMA+'semanticModel/definitionProperties/1.0.0/schema.json','version':'1.0'})
    for folder,item_type in [(report_folder,'Report'),(model_folder,'SemanticModel')]:
        dump(folder/'.platform',{
            '$schema':'https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json',
            'metadata':{'type':item_type,'displayName':'Medicare Analytics'},
            'config':{'version':'2.0','logicalId':str(uuid.uuid5(uuid.NAMESPACE_URL,'medicare-analytics:'+item_type))}})
    dump(output/'Medicare_Analytics.pbip',{'$schema':'https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json','version':'1.0',
         'artifacts':[{'report':{'path':'Medicare.Report'}}],'settings':{'enableAutoRecovery':True}})
    dump(report_folder/'definition.pbir',{'$schema':SCHEMA+'report/definitionProperties/2.0.0/schema.json','version':'4.0',
         'datasetReference':{'byPath':{'path':'../Medicare.SemanticModel'}}})
    definition=report_folder/'definition'
    dump(definition/'version.json',{'$schema':SCHEMA+'report/definition/versionMetadata/1.0.0/schema.json','version':'2.0.0'})
    theme=output/'assets/CY24SU02.json'
    if not theme.exists():
        raise FileNotFoundError('Missing official base theme: powerbi/assets/CY24SU02.json')
    theme_target=report_folder/'StaticResources/SharedResources/BaseThemes/CY24SU02.json'
    theme_target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(theme,theme_target)
    dump(definition/'report.json',{'$schema':SCHEMA+'report/definition/report/3.1.0/schema.json',
        'themeCollection':{'baseTheme':{'name':'CY24SU02','type':'SharedResources',
            'reportVersionAtImport':{'visual':'1.8.89','report':'2.0.89','page':'1.3.89'}}},
        'resourcePackages':[{'name':'SharedResources','type':'SharedResources','items':[
            {'name':'CY24SU02','path':'BaseThemes/CY24SU02.json','type':'BaseTheme'}]}]})
    pages=[('overview','01 Cost and Utilization'),('cohorts','02 Cohorts and Service Drivers'),('readmissions','03 Readmissions and Quality')]
    dump(definition/'pages/pages.json',{'$schema':SCHEMA+'report/definition/pagesMetadata/1.0.0/schema.json',
         'pageOrder':[p[0] for p in pages],'activePageName':'overview'})
    for page,title in pages:
        folder=definition/'pages'/page
        dump(folder/'page.json',{'$schema':SCHEMA+'report/definition/page/2.0.0/schema.json',
             'name':page,'displayName':title,'displayOption':'FitToPage','width':1280,'height':720})
        visuals=[text_visual(page+'_title',title+' | CMS Synthetic Medicare',20,10,1000,40,22),
                 text_visual(page+'_note','2016-2022 | Synthetic data | Annual-inferred FFS eligibility | Unadjusted returns; temporal episode proxies.',20,675,1200,35,10),
                 visual(page+'_years','slicer','Year',1030,5,230,65,{'Values':[('dim_year','service_year')]})]
        if page=='overview':
            for i,(measure,label) in enumerate([('Medical Claim Payment','Medical claim payment (base)'),('Medical PMPM','Medical PMPM'),('Medical Claim Count','Medical claims'),('Rx Plan Payment','Part D plan payment')]):
                visuals.append(visual(f'overview_card{i}','card',label+' (annual FFS proxy)' if measure=='Medical PMPM' else label,20+i*310,85,295,100,{'Values':[('dim_year',measure,True)]}))
            visuals += [
                visual('overview_trend','lineChart','Medical PMPM by year',20,205,600,220,{'Category':[('dim_year','service_year')],'Y':[('dim_year','Medical PMPM',True)]}),
                visual('overview_util','lineChart','Claims per 1,000 eligible member years',640,205,620,220,{'Category':[('dim_year','service_year')],'Y':[('dim_year','Claims per 1000 Member Years',True)]}),
                visual('overview_service','barChart','Medical claim payment by service',20,440,600,215,{'Category':[('dim_service','service_label')],'Y':[('dim_year','Medical Claim Payment',True)]}),
                visual('overview_ratio','barChart','Paid-to-charge ratio (matched positive charges)',640,440,620,215,{'Category':[('dim_service','service_label')],'Y':[('dim_year','Paid to Charge Ratio',True)]})]
        elif page=='cohorts':
            visuals += [visual('cohort_selector','slicer','Retrospective annual cohort',20,85,390,90,{'Values':[('dim_cohort','cohort_label')]}),
                visual('cohort_service_selector','slicer','Service category',430,85,390,90,{'Values':[('dim_service','service_label')]}),
                visual('cohort_topshare','card','Top 10% member payment share (all medical services)',840,85,420,90,{'Values':[('dim_year','Top 10 Percent Member Payment Share',True)]}),
                visual('cohort_pmpm','barChart','Medical PMPM by annual cohort',20,195,600,220,{'Category':[('dim_cohort','cohort_label')],'Y':[('dim_year','Medical PMPM',True)]}),
                visual('cohort_frequency','barChart','Claim utilization by annual cohort',640,195,620,220,{'Category':[('dim_cohort','cohort_label')],'Y':[('dim_year','Claims per 1000 Member Years',True)]}),
                visual('cohort_drg','barChart','Inpatient payment by DRG code (all cohorts)',20,435,600,220,{'Category':[('fact_drg_year','drg_code')],'Y':[('dim_year','DRG Claim Payment',True)]}),
                visual('cohort_table','tableEx','Cohort comparison',640,435,620,220,{'Values':[('dim_cohort','cohort_label'),('dim_year','Medical Claim Count',True),('dim_year','Medical PMPM',True),('dim_year','30 Day All Cause Return Rate',True)]})]
        else:
            for i,(measure,label) in enumerate([('Eligible Index Episodes','Eligible index episodes'),('30 Day Readmitted Episodes','30-day return episodes'),('30 Day All Cause Return Rate','All-cause return rate'),('Quality Exceptions All Source Years','Quality exceptions (all source years)')]):
                visuals.append(visual(f'readmission_card{i}','card',label,20+i*310,85,295,100,{'Values':[('dim_year',measure,True)]}))
            visuals += [visual('readmission_trend','lineChart','All-cause 30-day return rate',20,205,600,220,{'Category':[('dim_year','service_year')],'Y':[('dim_year','30 Day All Cause Return Rate',True)]}),
                visual('readmission_cohort','barChart','Return rate by retrospective cohort',640,205,620,220,{'Category':[('dim_cohort','cohort_label')],'Y':[('dim_year','30 Day All Cause Return Rate',True)]}),
                visual('readmission_eligibility','tableEx','Follow-up and enrollment exclusions',20,440,600,215,{'Values':[('fact_readmission','eligibility_reason'),('dim_year','Temporal Episodes',True)]}),
                visual('quality_table','tableEx','Exceptions by check (all source years)',640,440,620,215,{'Values':[('fact_quality','dataset'),('fact_quality','check_name'),('dim_year','Quality Exceptions All Source Years',True)]})]
        for item in visuals:
            dump(folder/'visuals'/item['name']/'visual.json',item)
    (output/'measures.dax').write_text('\n\n'.join(f'{n} =\n{e}' for n,e,_ in MEASURES)+'\n',encoding='utf-8')
    (output/'power_query_parameter.m').write_text('"'+str(data).replace('\\','/')+'/" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n',encoding='utf-8')
    print('Generated PBIP: 3 pages, 9 import tables, 19 DAX measures. Desktop validation remains required.')


if __name__=='__main__':main()

"""Validate PBIR/PBIP against Microsoft schemas and check model field references.

Requires jsonschema. Online schema downloads are cached under ignored processed data.
This does not execute DAX or render Power BI Desktop.
"""
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlparse
from urllib.request import urlopen
import warnings

ROOT=Path(__file__).resolve().parents[1]
try:
    import jsonschema
except ImportError:
    sys.path.append(str(ROOT/'.venv/Lib/site-packages'))
    import jsonschema

CACHE=ROOT/'data/processed/schema_cache'
CACHE.mkdir(parents=True,exist_ok=True)


def fetch(url):
    if urlparse(url).hostname!='developer.microsoft.com':
        raise ValueError('Only Microsoft schema downloads are allowed')
    path=CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.json')
    if not path.exists():
        # Microsoft's embedded schemas use a dotted $id but a hyphenated download URL.
        download_url=url.replace('/schema.embedded.json','/schema-embedded.json')
        with urlopen(download_url,timeout=30) as response:
            value=json.load(response)
        path.write_text(json.dumps(value),encoding='utf-8')
    return json.loads(path.read_text())


def main():
    root=ROOT/'powerbi'
    model=json.loads((root/'Medicare.SemanticModel/model.bim').read_text())['model']
    columns={t['name']:{c['name'] for c in t['columns']} for t in model['tables']}
    measures={t['name']:{m['name'] for m in t.get('measures',[])} for t in model['tables']}
    errors=[];validated=0
    paths=[p for p in root.rglob('*.json') if '.pbi' not in p.parts]+list(root.rglob('.platform'))+[root/'Medicare_Analytics.pbip',root/'Medicare.Report/definition.pbir',root/'Medicare.SemanticModel/definition.pbism']
    for path in paths:
        obj=json.loads(path.read_text(encoding='utf-8'))
        if '$schema' not in obj:continue
        schema=fetch(obj['$schema'])
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',DeprecationWarning)
            resolver=jsonschema.RefResolver(base_uri=obj['$schema'],referrer=schema,handlers={'https':fetch})
            validator=jsonschema.validators.validator_for(schema)(schema,resolver=resolver)
            for error in validator.iter_errors(obj):
                errors.append({'file':str(path.relative_to(ROOT)),'path':list(error.absolute_path),'error':error.message})
        validated+=1
        def references(value):
            if isinstance(value,dict):
                for kind,mapping in [('Column',columns),('Measure',measures)]:
                    if kind in value and isinstance(value[kind],dict):
                        expr=value[kind]
                        table=expr.get('Expression',{}).get('SourceRef',{}).get('Entity')
                        column=expr.get('Property')
                        if table is not None and column not in mapping.get(table,set()):
                            errors.append({'file':str(path.relative_to(ROOT)),'error':f'Unknown {kind}: {table}.{column}'})
                for child in value.values():references(child)
            elif isinstance(value,list):
                for child in value:references(child)
        references(obj)
    for relation in model['relationships']:
        for side in ['from','to']:
            if relation[side+'Column'] not in columns[relation[side+'Table']]:
                errors.append({'error':'Unknown relationship column','relationship':relation})
    report=root/'Medicare.Report'
    report_version=json.loads((report/'definition/version.json').read_text())['version']
    if report_version!='2.0.0':
        errors.append({'error':'Desktop report content version must be 2.0.0; do not copy definition.pbir version'})
    report_settings=json.loads((report/'definition/report.json').read_text())
    if not report_settings.get('themeCollection',{}).get('baseTheme'):
        errors.append({'error':'Missing Desktop base theme'})
    for package in report_settings.get('resourcePackages',[]):
        for item in package['items']:
            if not (report/'StaticResources'/package['name']/item['path']).exists():
                errors.append({'error':'Missing report resource','resource':item['path']})
    result={'validated_schema_files':validated,'model_tables':len(model['tables']),
            'dax_measure_count':sum(map(len,measures.values())),
            'desktop_refresh_and_render_verified':False,'errors':errors}
    (ROOT/'reports/powerbi_validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    if errors:raise SystemExit(1)


if __name__=='__main__':main()

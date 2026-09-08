from pathlib import Path
import sqlite3,json,hashlib
base=Path('tmp/faz11-preservation.json');manifest=json.loads(base.read_text())
old=sqlite3.connect('file:backups/faz11-before.db?mode=ro',uri=True);new=sqlite3.connect('file:data/app.db?mode=ro',uri=True)
report={'existing_table_count':len(manifest['tables']),'changed_business_tables':[],'session_table_changed':False,'counts':{},'pdfs_unchanged':True}
for table in manifest['tables']:
    query='SELECT * FROM "'+table.replace('"','""')+'" ORDER BY rowid'
    before=old.execute(query).fetchall();after=new.execute(query).fetchall();same=before==after
    report['counts'][table]={'before':len(before),'after':len(after),'unchanged':same}
    if not same:
        if table=='account_sessions':report['session_table_changed']=True
        else:report['changed_business_tables'].append(table)
report['pdfs_unchanged']=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==expected for p,expected in manifest['pdfs'].items())
report['pdf_count']=len(manifest['pdfs']);report['foreign_key_violations']=new.execute('PRAGMA foreign_key_check').fetchall()
report['skill_tables']={t:new.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ('skill_groups','skills','skill_terms','course_skill_mappings','request_skill_needs','skill_evidence','skill_audit')}
report['passed']=not report['changed_business_tables'] and report['pdfs_unchanged'] and not report['foreign_key_violations']
Path('tmp/faz11-preservation-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='counts'},ensure_ascii=False))
assert report['passed']

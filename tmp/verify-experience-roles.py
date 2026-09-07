import httpx,json
from pathlib import Path
clients={}
report={}
try:
    for role in ['employee','analyst','technical','engineering']:
        c=httpx.Client(base_url='http://127.0.0.1:8011',timeout=20); clients[role]=c
        r=c.post('/api/auth/login',json={'username':'preview_'+role,'password':'1234'});r.raise_for_status()
        endpoint='/api/requests/mine' if role=='employee' else '/api/admin/requests'
        r=c.get(endpoint);r.raise_for_status(); rows=r.json()['items']
        report[role]={'visible_ids':sorted(x['request_id'] for x in rows)}
        for row in rows:
            path=('/api/requests/' if role=='employee' else '/api/admin/requests/')+str(row['request_id'])
            detail=c.get(path);detail.raise_for_status()
            assert row['current_owner']==detail.json()['process']['current_owner']
    assert report['technical']['visible_ids']==[3]
    assert report['engineering']['visible_ids']==[2]
    assert report['employee']['visible_ids']==[1,2,3]
    assert clients['technical'].get('/api/admin/requests/2').status_code==404
    assert clients['engineering'].get('/api/admin/requests/3').status_code==404
    assert clients['employee'].get('/api/admin/requests').status_code==403
    report['wrong_department_direct_detail']=404
    report['list_detail_owner_aligned']=True
    report['synthetic_only']=True
    Path('tmp/experience-preview/role-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))
finally:
    for c in clients.values(): c.post('/api/auth/logout');c.close()

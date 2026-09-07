from pathlib import Path
p=Path('app/learning.py');s=p.read_text(encoding='utf-8')
a=s.index('    if not flow:',s.index('def record_decision('));b=s.index('    snapshot = public_result(result)',a)
s=s[:a]+'''    from .workflow_core import lock_flow
    version = expected_version + 1
    transition = {"status": next_status, "public_note": reason} if advance else {}
    flow = lock_flow(db, record, flow, expected_version, **transition)
'''+s[b:]
s=s.replace('scope="NEEDS_ANALYST")','scope="NEEDS_ANALYST", from_status=ctx["state"])')
p.write_text(s,encoding='utf-8')
p=Path('app/workflow.py');s=p.read_text(encoding='utf-8')
a=s.index('    if not flow:',s.index('def refer_request('));b=s.index('    transition_effects(db, record',a)
s=s[:a]+'''    from .workflow_core import lock_flow, transition_effects, plan_payload
    from .models import RequestSolutionPlan
    previous_plan = plan_payload(db, db.get(RequestSolutionPlan, record.id))
    note = analysis_summary.strip()
    flow = lock_flow(db, record, flow, expected_version, status="REFERRED", public_note=note)
'''+s[b:]
s=s.replace('details={"department": department})','details={"department": department, "plan": {"before": previous_plan, "after": plan_payload(db, plan)}})')
p.write_text(s,encoding='utf-8')
p=Path('app/static/js/portal.js');s=p.read_text(encoding='utf-8').replace("if(fixedStatus){PORTAL.filter=fixedStatus;", "if(fixedStatus){PORTAL.view='';PORTAL.filter=fixedStatus;")
p.write_text(s,encoding='utf-8')
p=Path('tests/frontend.test.cjs');s=p.read_text(encoding='utf-8').replace("{status:'REFERRED',sort:'oldest'});", "{status:'REFERRED',sort:'oldest',view:''});")
s+='''
test('status actions are supplied by backend and missing policy fails closed',()=>{
  const c=livePortalContext();
  const empty=c.portalStatusEditor({request_id:99,version:1,status:'IN_REVIEW'},false);
  assert.ok(!empty.includes('<form'));assert.ok(!empty.includes('İhtiyacım karşılandı'));
  const html=c.portalStatusEditor({request_id:99,version:1,status:'NEEDS_INFO',process:{available_actions:[
    {code:'PROVIDE_INFO',channel:'action',label:'Ek bilgiyi gönder',target:'IN_REVIEW'},
    {code:'REVIEW',channel:'review',label:'İnsan değerlendirmesi'}]}},false);
  assert.ok(html.includes('value="PROVIDE_INFO"'));assert.ok(!html.includes('value="RESOLVE"'));assert.ok(!html.includes('value="REVIEW"'));
});
test('solution plan and assignment use real backend data and escape content',()=>{
  const c=livePortalContext();
  assert.equal(c.portalPlan({request_id:98,version:1,process:{available_actions:[]}}),'');
  const html=c.portalPlan({request_id:98,version:1,process:{available_actions:[],plan:{summary:'<script>plan</script>',state:'planned',responsible_unit_label:'Analiz',created_by:{display_name:'Analist'}}}});
  assert.ok(html.includes('&lt;script&gt;'));assert.ok(!html.includes('<script>'));assert.ok(!html.includes('Hedef tarih'));
  assert.equal(c.portalAssignment({process:{available_actions:[]}}),'');
});
'''
p.write_text(s,encoding='utf-8')

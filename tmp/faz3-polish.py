from pathlib import Path
p=Path('app/static/js/portal.js')
s=p.read_text(encoding='utf-8')
s=s.replace("sort:PORTAL.sort,view:PORTAL.view||''||'newest'", "sort:PORTAL.sort||'newest',view:PORTAL.view||''")
s=s.replace("PORTAL.filter=WORKFLOW_CONFIG[saved.status]", "PORTAL.view=['actionable','unit','assigned','info','planned','completed'].indexOf(saved.view)>=0?saved.view:'';PORTAL.filter=WORKFLOW_CONFIG[saved.status]")
s=s.replace("PORTAL.fixedList=false;", "PORTAL.fixedList=false;PORTAL.view='';")
s=s.replace("PORTAL.filter=fixedStatus||'';", "PORTAL.filter=fixedStatus||'';PORTAL.view='';")
lines=s.splitlines()
lines=[line for line in lines if not line.startswith('  statusActions:')]
s='\n'.join(lines)+'\n'
s=s.replace("<th scope=\"col\">Oluşturulma</th>", "<th scope=\"col\">Son işlem / aşama süresi</th>")
s=s.replace("+esc(owner||'Birim bilgisi yok')+'</td><td class=\"request-date\">'+portalDate(item.created_at)", "+esc(owner||'Birim bilgisi yok')+(item.assignee?'<span class=\"request-table-category\">'+esc(item.assignee.display_name)+'</span>':'')+'</td><td class=\"request-date\"><span title=\"'+esc((item.last_action||{}).note||'Talep oluşturuldu')+'\">'+portalDateTime((item.last_action||{}).at||item.created_at)+'</span><span class=\"request-table-category\">Aşamada: '+portalAge((item.aging||{}).current_stage_seconds)+((item.aging||{}).sla&&item.aging.sla.state!=='normal'?' · '+esc(item.aging.sla.state==='overdue'?'SLA aşıldı':'SLA yaklaşıyor'):'')+'</span>'")
s=s.replace("if(event.status&&WORKFLOW_CONFIG[event.status]){", "if(event.from_status&&WORKFLOW_CONFIG[event.from_status])previousStatus=event.from_status;\n    if(event.status&&WORKFLOW_CONFIG[event.status]){")
p.write_text(s,encoding='utf-8')

# Previous unrestricted-transition assertions are replaced with the now-required plan step.
p=Path('tests/test_portal_workflow.py')
s=p.read_text(encoding='utf-8')
s=s.replace('        self.assertEqual(resolved.status_code, 200)\n        self.assertEqual(len(resolved.json()["events"]), 2)', '''        self.assertEqual(resolved.status_code, 422)
        self.refer(identifier).raise_for_status()
        self.clients["technical"].post(f'/api/admin/requests/{identifier}/actions', json={
            "action": "SAVE_PLAN", "summary": "Sentetik eğitim ve uygulama planı", "responsible_unit": "TECHNICAL_DESIGN",
            "expected_version": 2}).raise_for_status()
        resolved = self.owner.patch(f'/api/requests/{identifier}/status', json={"status": "RESOLVED", "note": "Eğitim uygulandı ve ihtiyaç karşılandı", "expected_version": 3})
        self.assertEqual(resolved.status_code, 200)
        self.assertEqual(len(resolved.json()["events"]), 5)''')
s=s.replace('"note": "Ek ihtiyaç oluştu", "expected_version": 2', '"note": "Ek ihtiyaç oluştu", "expected_version": 4')
p.write_text(s,encoding='utf-8')
p=Path('tests/test_review_advance.py')
s=p.read_text(encoding='utf-8')
a=s.index('        for status, expected_role, expected_action in (("ACTION_PLANNED"')
b=s.index('\n    def test_list_action_projection',a)
s=s[:a]+'''        designer = self.principals["TECHNICAL_DESIGN"]
        for status, expected_role, expected_action in (("ACTION_PLANNED", "TECHNICAL_DESIGN", "DELIVER_SOLUTION"),
                                                      ("RESOLVED", None, "COMPLETE")):
            change_status(self.db, self.record, self.flow, owner_hash=designer.token_hash, admin=True,
                          target=status, note="Sentetik süreç adımı güncellendi.", expected_version=self.flow.version,
                          role=designer.role, principal=designer)
            assert_alignment(expected_role, expected_action)
        change_status(self.db, self.record, self.flow, owner_hash=analyst.token_hash, admin=True,
                      target="IN_REVIEW", note="Ek ihtiyaç ile yeniden açıldı.", expected_version=self.flow.version,
                      role=analyst.role, principal=analyst)
        change_status(self.db, self.record, self.flow, owner_hash=analyst.token_hash, admin=True,
                      target="NEEDS_INFO", note="Ek bilgi bekleniyor.", expected_version=self.flow.version,
                      role=analyst.role, principal=analyst)
        assert_alignment("EMPLOYEE", "PROVIDE_INFO")
''' + s[b:]
s=s.replace('for table in ("request_events", "request_decisions", "request_event_identities")', 'for table in ("original_ai_json", "request_event_identities", "request_event_actions")')
s=s.replace('test_list_action_projection_does_not_load_timeline_or_decision_audit', 'test_list_action_projection_loads_operational_fields_without_decision_audit')
p.write_text(s,encoding='utf-8')

p=Path('app/static/index_tusas_faz31.html')
s=p.read_text(encoding='utf-8').replace('20260907-6','20260907-7')
p.write_text(s,encoding='utf-8')

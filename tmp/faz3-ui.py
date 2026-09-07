from pathlib import Path
p = Path('app/static/js/portal.js')
s = p.read_text(encoding='utf-8')
s = s.replace("sort:'newest',drafts:{}", "sort:'newest',view:'',drafts:{}")
# Keep visual status labels, remove the old client-side transition catalogue.
s = s.replace(",\n  statusActions:{IN_REVIEW:'İhtiyaç analizine geri gönder',ACTION_PLANNED:'Çözüm planlandı olarak kaydet',NEEDS_INFO:'Talep sahibinden ek bilgi iste',RESOLVED:'Tamamlandı olarak kaydet'}", '')
a = s.index('function portalStatusEditor(')
b = s.index('\nfunction portalRouting(', a)
s = s[:a] + '''function portalActions(result,channel){return ((result.process||{}).available_actions||[]).filter(function(action){return action.channel===channel})}
function portalAge(seconds){if(seconds==null)return 'Süre bilgisi yok';if(seconds<60)return 'Az önce';var minutes=Math.floor(seconds/60);if(minutes<60)return minutes+' dk';var hours=Math.floor(minutes/60);if(hours<24)return hours+' sa '+minutes%60+' dk';return Math.floor(hours/24)+' gün '+hours%24+' sa'}
function portalAging(result){var age=(result.process||{}).aging||{},sla=age.sla;return '<dl><dt>Mevcut aşamada</dt><dd>'+portalAge(age.current_stage_seconds)+'</dd><dt>Son işlemden beri</dt><dd>'+portalAge(age.last_action_seconds)+'</dd><dt>Talep yaşı</dt><dd>'+portalAge(age.created_seconds)+'</dd></dl>'+(sla?'<p class="notice '+(sla.state==='normal'?'':'warning')+'">'+esc({normal:'SLA süresi içinde',approaching:'SLA süresi yaklaşıyor',overdue:'SLA süresi aşıldı'}[sla.state])+'</p>':'')}
function portalStatusEditor(result,admin){
  var actions=portalActions(result,'action'),draft=portalDraft(result,'status');
  if(!actions.length)return '<section id="portalStatusForm" class="status-editor"><p class="caption">Bu aşamada hesabınız için açık durum işlemi bulunmuyor.</p></section>';
  return '<section class="card status-editor"><h2>Süreç işlemi</h2><form id="portalStatusForm">'+(draft.version!==result.version?'<p class="notice warning">Talep güncellendi. Açıklamanız korundu; güncel durumu kontrol edin.</p>':'')+'<div class="field"><label for="nextRequestStatus">Yapılacak işlem</label><select id="nextRequestStatus" required>'+actions.map(function(action){return '<option value="'+esc(action.code)+'" '+(draft.status===action.code?'selected':'')+'>'+esc(action.label)+'</option>'}).join('')+'</select></div><div class="field"><label for="requestStatusNote">Açıklama · Zorunlu</label><textarea id="requestStatusNote" required minlength="3" maxlength="1500" rows="3">'+esc(draft.note||'')+'</textarea></div><div id="portalStatusError" role="alert"></div><button class="btn primary" type="submit">'+esc(actions.find(function(action){return action.code===draft.status})?.label||actions[0].label)+'</button></form></section>';
}
function portalAssigneeOptions(result,selected){return '<option value="">Kişisel atama yok · Birim iş kuyruğu</option>'+((result.process||{}).assignment_options||[]).map(function(user){return '<option value="'+Number(user.id)+'" '+(Number(selected)===user.id?'selected':'')+'>'+esc(user.display_name)+'</option>'}).join('')}
function portalPlan(result){
  var process=result.process||{},plan=process.plan,allowed=portalActions(result,'plan').length,draft=portalDraft(result,'plan'),values=Object.assign({},plan||{},draft.values||{}),assignee=values.assignee_id!==undefined?values.assignee_id:(values.assignee||{}).id;
  var shown=plan?'<section class="card"><div class="section-title"><h2>Çözüm planı</h2><span class="badge">'+esc({planned:'Planlandı',completed:'Tamamlandı',superseded:'Önceki plan'}[plan.state]||plan.state)+'</span></div><p>'+esc(plan.summary)+'</p><dl class="request-facts"><div><dt>Sorumlu birim</dt><dd>'+esc(plan.responsible_unit_label)+'</dd></div>'+(plan.assignee?'<div><dt>Atanan kişi</dt><dd>'+esc(plan.assignee.display_name)+'</dd></div>':'')+(plan.target_date?'<div><dt>Hedef tarih</dt><dd>'+portalDate(plan.target_date)+'</dd></div>':'')+'<div><dt>Oluşturan</dt><dd>'+esc((plan.created_by||{}).display_name)+'</dd></div><div><dt>Oluşturulma / güncelleme</dt><dd>'+portalDateTime(plan.created_at)+' / '+portalDateTime(plan.updated_at)+'</dd></div></dl></section>':'';
  if(!allowed)return shown;
  return shown+'<details class="card" '+(!plan?'open':'')+'><summary>'+(plan?'Çözüm planını güncelle':'Çözüm planı oluştur')+'</summary><form id="portalPlanForm"><p class="caption">Sorumlu: '+esc((process.current_owner||{}).label)+'</p><div class="field"><label for="planSummary">Plan özeti · Zorunlu</label><textarea id="planSummary" required minlength="10" maxlength="3000" rows="4">'+esc(values.summary||'')+'</textarea></div><div class="field"><label for="planAssignee">Atanan kişi · İsteğe bağlı</label><select id="planAssignee">'+portalAssigneeOptions(result,assignee)+'</select></div><div class="field"><label for="planTarget">Hedef tarih · İsteğe bağlı</label><input id="planTarget" type="date" value="'+esc(values.target_date||'')+'"></div><div class="action-error" role="alert"></div><button class="btn primary" type="submit">Planı kaydet</button></form></details>';
}
function portalAssignment(result){
  if(!portalActions(result,'assignment').length)return '';
  var process=result.process||{},draft=portalDraft(result,'assignment'),values=draft.values||{};
  return '<details class="card"><summary>Kişisel atama</summary><form id="portalAssignmentForm"><p class="caption">Birim sorumluluğu devam eder; yalnızca gerçek ve aktif birim kullanıcıları atanabilir.</p><div class="field"><label for="caseAssignee">Atanan kişi</label><select id="caseAssignee">'+portalAssigneeOptions(result,values.assignee_id!==undefined?values.assignee_id:(process.assignee||{}).id)+'</select></div><div class="field"><label for="assignmentNote">Atama açıklaması · Zorunlu</label><textarea id="assignmentNote" required minlength="3" maxlength="1500">'+esc(values.note||'')+'</textarea></div><div class="action-error" role="alert"></div><button class="btn" type="submit">Atamayı kaydet</button></form></details>';
}
function bindPortalCore(result,epoch){
  [{id:'portalPlanForm',type:'plan',read:function(){return {action:'SAVE_PLAN',summary:$('#planSummary').value,responsible_unit:result.process.responsible_scope,assignee_id:Number($('#planAssignee').value)||null,target_date:$('#planTarget').value||null}}},{id:'portalAssignmentForm',type:'assignment',read:function(){return {action:'ASSIGN',assignee_id:Number($('#caseAssignee').value)||null,note:$('#assignmentNote').value}}}].forEach(function(config){
    var form=$('#'+config.id);if(!form)return;var busy=false,draft=portalDraft(result,config.type);
    form.addEventListener('input',function(){draft.values=config.read()});form.addEventListener('change',function(){draft.values=config.read()});
    form.addEventListener('submit',async function(event){event.preventDefault();if(busy)return;busy=true;var button=form.querySelector('button[type="submit"]');button.disabled=true;draft.values=config.read();
      try{await apiRequest('/api/admin/requests/'+result.request_id+'/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(Object.assign({},draft.values,{expected_version:result.version}))});if(epoch!==PORTAL.epoch)return;portalDropDraft(result,config.type);toast('İşlem ve geçmiş kaydı güncellendi.');render()}
      catch(error){if(epoch===PORTAL.epoch)form.querySelector('.action-error').innerHTML=portalError(error)+(error.status===409?'<button class="btn" type="button" data-portal="reload-detail">Güncel talebi yükle · Taslağım korunsun</button>':'')}
      finally{busy=false;button.disabled=false}
    });
  });
}
''' + s[b:]
s = s.replace("if(!draft)return false;if(type==='status')", "if(!draft)return false;if(type==='plan'||type==='assignment')return !!draft.values;if(type==='status')")
s = s.replace("<dt>Aksiyon sahibi</dt><dd>'+esc((process.current_owner||{}).label||config.owner)+'</dd></dl>", "<dt>Sorumlu birim / rol</dt><dd>'+esc((process.current_owner||{}).label||'Bilgi mevcut değil')+'</dd><dt>Atanan kişi</dt><dd>'+esc((process.assignee||{}).display_name||'Henüz kişisel atama yapılmadı')+'</dd></dl>'+portalAging(result)+'")
s = s.replace("+brief+referral+(firstReview?status:'')", "+brief+portalPlan(result)+portalAssignment(result)+referral+(firstReview?status:'')")
s = s.replace("    if(admin)bindPortalDecision(result,epoch);", "    if(admin){bindPortalDecision(result,epoch);bindPortalCore(result,epoch)}")
s = s.replace("    function captureStatus(){", "    if(!statusForm||statusForm.tagName!=='FORM')return;\n    function captureStatus(){")
s = s.replace("if(admin)statusDraft.status=$('#nextRequestStatus').value", "statusDraft.status=$('#nextRequestStatus').value")
s = s.replace("statusForm.addEventListener('change',captureStatus);", "statusForm.addEventListener('change',function(){captureStatus();var action=portalActions(result,'action').find(function(item){return item.code===statusDraft.status});if(action)statusForm.querySelector('button[type=\"submit\"]').textContent=action.label});")
s = s.replace("var target=admin?$('#nextRequestStatus').value:button.dataset.target;", "var code=$('#nextRequestStatus').value,action=portalActions(result,'action').find(function(item){return item.code===code}),target=action&&action.target;")
s = s.replace("+result.request_id+'/status',{method:'PATCH'", "+result.request_id+'/actions',{method:'POST'")
s = s.replace("JSON.stringify({status:target,note:", "JSON.stringify({action:code,note:")
# Existing controls remain, operational choices come solely from the backend.
s = s.replace("+'&status='+encodeURIComponent(PORTAL.filter)", "+'&view='+encodeURIComponent(PORTAL.view||'')+'&status='+encodeURIComponent(PORTAL.filter)")
s = s.replace("PORTAL.list=data;$('#portalListContent')", "PORTAL.list=data;portalQueueControls(data,admin);$('#portalListContent')")
a = s.index("+(!fixed?'<div class=\"quick-filters\"")
b = s.index(";\n}", a)
s = s[:a] + "+(!fixed?'<div id=\"portalQueueViews\" class=\"quick-filters\" role=\"group\" aria-label=\"İş kuyrukları\"></div>':'')" + s[b:]
s = s.replace("PORTAL.filter=button.dataset.status;PORTAL.offset=0;", "PORTAL.filter=button.dataset.status;PORTAL.view='';PORTAL.offset=0;")
# Reset a queue selection whenever the user intentionally changes the status.
s = s.replace("status.addEventListener('change',apply)", "status.addEventListener('change',function(){PORTAL.view='';apply()})")
s += '''
function portalQueueControls(data,admin){var container=$('#portalQueueViews');if(!container)return;container.innerHTML=(data.queue_views||[]).map(function(view){return '<button class="quick-filter '+((PORTAL.view||'')===view.id?'active':'')+'" type="button" data-view="'+esc(view.id)+'" aria-pressed="'+((PORTAL.view||'')===view.id)+'">'+esc(view.label)+'</button>'}).join('');container.querySelectorAll('button').forEach(function(button){button.addEventListener('click',function(){PORTAL.view=button.dataset.view;PORTAL.filter='';PORTAL.offset=0;var field=$('#portalStatus');if(field)field.value='';portalSaveFilters(admin);loadPortalList(admin)})})}
'''
# Preserve all previously remembered settings, add queue scope where applicable.
s = s.replace("sort:PORTAL.sort", "sort:PORTAL.sort,view:PORTAL.view||''")
s = s.replace("PORTAL.sort=value.sort", "PORTAL.view=value.view||'';PORTAL.sort=value.sort")
p.write_text(s, encoding='utf-8')

from pathlib import Path
p=Path('app/static/js/app.js');s=p.read_text(encoding='utf-8')
s=s.replace('if(button)button.disabled=LIVE_AI.status!=="connected"||LIVE_REQUEST.busy;', 'if(button)button.disabled=!!LIVE_REQUEST.busy;')
s=s.replace('esc(LIVE_AI.message)+\n      (LIVE_AI.status', 'esc(LIVE_AI.message)+" Talebinizi yine de kaydedebilirsiniz; analiz durumu talep detayında izlenir."+\n      (LIVE_AI.status')
p.write_text(s,encoding='utf-8')

p=Path('app/static/js/portal.js');s=p.read_text(encoding='utf-8')
s=s.replace("LIVE_REQUEST.text='';LIVE_REQUEST.result=null;", "LIVE_REQUEST.submissionKey=null;LIVE_REQUEST.submissionText=null;LIVE_REQUEST.text='';LIVE_REQUEST.result=null;")
s=s.replace("Talebiniz değerlendiriliyor…", "Talebiniz kaydediliyor…")
s=s.replace("    LIVE_REQUEST.text=text;LIVE_REQUEST.result=null;", "    if(LIVE_REQUEST.submissionText!==text||!LIVE_REQUEST.submissionKey){LIVE_REQUEST.submissionKey=crypto.randomUUID();LIVE_REQUEST.submissionText=text}\n    LIVE_REQUEST.text=text;LIVE_REQUEST.result=null;")
a=s.index('    try{await ensurePortalIndex(generation);',s.index('function bindPortalRequest'))
b=s.index('\n    catch(error)',a)
s=s[:a]+'''    try{var analysisResult=await apiRequest('/api/requests/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text,idempotency_key:LIVE_REQUEST.submissionKey})});if(generation!==PORTAL.accountGeneration)return;LIVE_REQUEST.result=analysisResult;toast('Talebiniz kaydedildi. Analiz durumu talep detayında izlenebilir.');openPortalRequest(analysisResult.request_id,false)}'''+s[b:]
# Every pending/failed result is explicitly distinguished from a completed course assessment.
s=s.replace("function renderEmployeeResult(result){", "function renderEmployeeResult(result){\n  if(result.analysis_state&&!result.analysis_state.latest_completed&&!result.analysis_state.legacy_result)return '<section class=\"card\">'+portalAnalysisState(result)+'<button class=\"btn\" data-portal=\"open-request\" data-id=\"'+Number(result.request_id)+'\">Kaydedilen talebi aç</button></section>';")
s=s.replace("return '<article class=\"case-file\">'+portalCaseHeader(result)+portalProcessSteps(result)", "return '<article class=\"case-file\">'+portalCaseHeader(result)+portalAnalysisState(result)+portalProcessSteps(result)")
s=s.replace("    PORTAL.detail=result;$('#portalDetailContent').innerHTML=portalDetailBody(result,admin);", "    PORTAL.detail=result;$('#portalDetailContent').innerHTML=portalDetailBody(result,admin);bindPortalAnalysis(result,epoch,admin);")
s=s.replace("return !!(decision&&(Number(decision.request_version)", "var current=((result.analysis_state||{}).latest_completed||{}).id,reference=(decision||{}).analysis_version||{};if(current&&reference.id!==current&&!((result.analysis_state.latest_completed||{}).imported&&reference.legacy))return false;return !!(decision&&(Number(decision.request_version)")
s=s.replace('İLK YAPAY ZEKÂ ÖNERİSİ</span>', 'KARARA ESAS AI DEĞERLENDİRMESİ</span>')
s=s.replace("esc((item.reviewer||{}).display_name||'Yetkili kullanıcı')+'</span>", "esc((item.reviewer||{}).display_name||'Yetkili kullanıcı')+((item.analysis_version||{}).sequence?' · Analiz v'+Number(item.analysis_version.sequence):' · Önceki kayıtlı analiz')+'</span>")
s+='''

function portalAnalysisState(result){
  var state=result.analysis_state;if(!state)return '';var latest=state.latest_run,completed=state.latest_completed;
  var status=latest?latest.status_label:state.legacy_result?'Önceki kayıtlı analiz':'Analiz sürümü bulunmuyor';
  var info=latest&&latest.error_message?'Talebiniz kaydedildi ancak analiz şu anda tamamlanamadı. '+latest.error_message:latest&&['PENDING','PROCESSING'].includes(latest.status)?'Talebiniz kalıcı olarak kayıtlı. Analiz tamamlandığında bu alan güncellenecek.':'';
  return '<section class="card" aria-labelledby="analysisStateTitle"><div class="section-title"><h2 id="analysisStateTitle">'+esc(status)+'</h2>'+(latest?'<span class="caption">Analiz sürümü '+Number(latest.sequence)+'</span>':'')+'</div>'+(info?'<p role="status">'+esc(info)+'</p>':'')+(completed?'<p class="caption">Gösterilen son başarılı analiz: v'+Number(completed.sequence)+' · '+(completed.completed_at?portalDateTime(completed.completed_at):'Tamamlanma zamanı eski kayıtta mevcut değil')+(latest&&latest.id!==completed.id?' · Önceki başarılı sonuç korunuyor.':'')+'</p>':'')+(state.result_is_current_input===false&&completed?'<p class="caption">Güncel talep girdisinin analizi henüz doğrulanmadı; önceki sonuç yeni ek bilgilerin değerlendirmesi sayılmaz.</p>':'')+'<div id="portalAnalysisError" role="alert"></div>'+(state.available_actions||[]).map(function(action){return '<button class="btn" type="button" data-analysis-action="'+esc(action.code)+'">'+esc(action.label)+'</button>'}).join('')+'</section>';
}
function bindPortalAnalysis(result,epoch,admin){
  var state=result.analysis_state;if(!state)return;
  document.querySelectorAll('[data-analysis-action]').forEach(function(button){var busy=false,key=crypto.randomUUID();button.addEventListener('click',async function(){if(busy)return;busy=true;button.disabled=true;try{await apiRequest((admin?'/api/admin/requests/':'/api/requests/')+result.request_id+'/analysis',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_version:result.version,idempotency_key:key})});if(epoch===PORTAL.epoch)render()}catch(error){if(epoch===PORTAL.epoch)$('#portalAnalysisError').innerHTML=portalError(error)+(error.status===409?'<button class="btn" type="button" data-portal="reload-detail">Güncel kaydı aç</button>':'')}finally{busy=false;button.disabled=false}})});
  if(state.latest_run&&['PENDING','PROCESSING'].includes(state.latest_run.status)){
    var poll=async function(){if(epoch!==PORTAL.epoch||!PORTAL.user)return;try{var fresh=await apiRequest((admin?'/api/admin/requests/':'/api/requests/')+result.request_id);if(epoch!==PORTAL.epoch)return;var run=(fresh.analysis_state||{}).latest_run;if(!run||run.status!==state.latest_run.status||fresh.version!==result.version){render();return}}catch(error){if(epoch!==PORTAL.epoch)return;var errorNode=$('#portalAnalysisError');if(errorNode)errorNode.innerHTML=portalError(error)+'<button class="btn" type="button" data-portal="reload-detail">Kaydı yeniden yükle</button>';return}setTimeout(poll,2500)};setTimeout(poll,2500);
  }
}
'''
p.write_text(s,encoding='utf-8')

p=Path('app/static/index_tusas_faz31.html');s=p.read_text(encoding='utf-8').replace('20260907-7','20260907-8');p.write_text(s,encoding='utf-8')

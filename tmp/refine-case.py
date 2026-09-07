from pathlib import Path

p = Path('app/static/js/portal.js')
s = p.read_text(encoding='utf-8')
def section(start, end, replacement):
    global s
    a, b = s.index(start), s.index(end, s.index(start))
    s = s[:a] + replacement + '\n' + s[b:]

section('function portalTimeline(result){', 'function portalStatusEditor(result,admin){', r'''
var CASE_PRESENTATION={
  actors:{SYSTEM:'Sistem',EMPLOYEE:'Çalışan',ADMIN:'Önceki yönetici',NEEDS_ANALYST:'İhtiyaç analizi',TECHNICAL_DESIGN:'Teknik eğitim tasarım',ENGINEERING_DESIGN:'Mühendislik eğitim tasarım'},
  outcomes:{APPROVED:'Onaylandı',MODIFIED:'Düzeltildi',REJECTED:'Tamamen yanlış'},
  steps:{completed:{css:'complete',label:'Tamamlandı',marker:'✓'},complete:{css:'complete',label:'Tamamlandı',marker:'✓'},active:{css:'current',label:'Aktif'},current:{css:'current',label:'Aktif'},pending:{css:'pending',label:'Bekliyor'},skipped:{css:'skipped',label:'Gerekmedi',marker:'—'}},
  statusActions:{IN_REVIEW:'İhtiyaç analizine geri gönder',ACTION_PLANNED:'Çözüm planını kaydet',NEEDS_INFO:'Talep sahibinden ek bilgi iste',RESOLVED:'Tamamlandı olarak kaydet'}
};
function portalActivityEvents(result){
  var events=(result.process||{}).timeline;
  if(!Array.isArray(events))events=(result.events||[]).map(function(event,index){return {id:'event-'+index,kind:'status',label:event.label,status:event.status,actor:{role:event.actor},note:event.note,at:event.at}}).concat((result.decisions||[]).map(function(decision){return {id:'decision-'+decision.id,kind:'decision',label:CASE_PRESENTATION.outcomes[decision.outcome]||'İnsan değerlendirmesi',actor:decision.reviewer||{},note:decision.reason,at:decision.created_at,outcome:decision.outcome}}));
  return events.slice().sort(function(a,b){return (Date.parse(a.at)||0)-(Date.parse(b.at)||0)});
}
function portalActorName(actor){return typeof actor==='string'?(CASE_PRESENTATION.actors[actor]||'Kullanıcı bilgisi kaydedilmemiş'):(actor||{}).display_name||CASE_PRESENTATION.actors[(actor||{}).role]||'Kullanıcı bilgisi kaydedilmemiş'}
function portalTimeline(result){
  var events=portalActivityEvents(result),previousStatus=null;
  return '<section class="process-timeline case-history" aria-labelledby="caseHistoryTitle"><div class="section-title"><div><div class="eyebrow">ACTIVITY HISTORY</div><h2 id="caseHistoryTitle">İşlem geçmişi</h2></div><span class="caption">'+events.length+' kayıt · Eskiden yeniye</span></div><ol class="portal-timeline">'+events.map(function(event){
    var actor=event.actor||{},role=CASE_PRESENTATION.actors[actor.role],transition='';
    if(event.status&&WORKFLOW_CONFIG[event.status]){
      transition='<span class="activity-status">'+(previousStatus&&previousStatus!==event.status?esc(WORKFLOW_LABELS[previousStatus])+' <span aria-label="yeni durum">→</span> ':'Durum: ')+esc(WORKFLOW_LABELS[event.status])+'</span>';
      previousStatus=event.status;
    }
    return '<li class="activity-item '+(event.outcome==='REJECTED'?'activity-rejected':'activity-complete')+'"><span class="activity-marker" aria-hidden="true">'+(event.outcome==='REJECTED'?'!':event.outcome?'✓':'·')+'</span><div><div class="activity-head"><strong>'+esc(event.label||WORKFLOW_LABELS[event.status]||'İşlem kaydedildi')+'</strong><time '+(event.at?'datetime="'+esc(event.at)+'"':'')+'>'+portalDateTime(event.at)+'</time></div><span class="activity-actor">'+esc(portalActorName(actor))+(actor.display_name&&role?' · '+esc(role):'')+'</span><div class="activity-tags">'+transition+(event.outcome?'<span class="workflow-badge decision-'+esc(CASE_PRESENTATION.outcomes[event.outcome]?event.outcome:'UNKNOWN')+'">'+esc(CASE_PRESENTATION.outcomes[event.outcome]||'Değerlendirildi')+'</span>':'')+'</div>'+(event.note?'<p class="activity-note">'+esc(event.note)+'</p>':'')+'</div></li>';
  }).join('')+'</ol>'+(!events.length?'<p class="caption">Bu kayıt için tarihçeye işlenmiş bir olay bulunmuyor.</p>':'')+'</section>';
}
function portalProcessSteps(result){
  var process=result.process||{},steps=process.steps||[],active=steps.filter(function(step){return ['current','active'].indexOf(step.state)>=0}).map(function(step){return step.label}).join(' · ');
  return '<section class="process-overview case-process" aria-labelledby="caseProcessTitle"><div class="section-title"><div><div class="eyebrow">PROCESS OVERVIEW</div><h2 id="caseProcessTitle">Süreç görünümü</h2></div><span class="process-stage">'+esc(result.status==='RESOLVED'?'Tamamlandı':active||'Aşama bilgisi kayıtlı değil')+'</span></div>'+(steps.length?'<ol class="workflow-steps" style="--workflow-step-count:'+steps.length+'" aria-label="Talep değerlendirme adımları">'+steps.map(function(step,index){var view=CASE_PRESENTATION.steps[step.state]||CASE_PRESENTATION.steps.pending;return '<li class="'+view.css+'" '+(view.css==='current'?'aria-current="step"':'')+'><span aria-hidden="true">'+(view.marker||String(index+1).padStart(2,'0'))+'</span><strong>'+esc(step.label)+'</strong><small>'+view.label+'</small></li>'}).join('')+'</ol>':'<p class="caption">Bu kaydın süreç adımları mevcut değil. Güncel durum: '+esc(WORKFLOW_LABELS[result.status]||'Bilinmiyor')+'.</p>')+'</section>';
}
function portalRequestFacts(result){
  var process=result.process||{},creator=process.creator||{},org=process.organization||{};
  return '<dl class="request-facts">'+[['Oluşturan',creator.display_name||'Kullanıcı bilgisi kaydedilmemiş'],['Organizasyon',org.name||org.label||'Organizasyon bilgisi tanımlanmamış'],['Birim / şeflik',[org.unit,org.chiefdom].filter(function(value){return typeof value==='string'&&value.trim()}).join(' / ')||'Birim / şeflik bilgisi kayıtlı değil'],['Oluşturulma',portalDateTime(result.created_at)]].map(function(item){return '<div><dt>'+item[0]+'</dt><dd>'+esc(item[1])+'</dd></div>'}).join('')+'</dl>';
}
function portalCaseHeader(result){
  var process=result.process||{},config=WORKFLOW_CONFIG[result.status]||WORKFLOW_CONFIG.LEGACY;
  return '<header class="case-header"><div class="case-title-line"><div><div class="eyebrow">TALEP DOSYASI · #'+Number(result.request_id)+'</div><h1>'+esc(result.topic||(result.classification||{}).topic||'Talep #'+Number(result.request_id))+'</h1></div>'+workflowBadge(result.status)+'</div><div class="case-owner-line"><span>Aksiyon şu anda</span><strong>'+esc((process.current_owner||{}).label||config.owner)+'</strong></div>'+portalRequestFacts(result)+'</header>';
}
function portalCurrentAction(result,actionId){
  var process=result.process||{},config=WORKFLOW_CONFIG[result.status]||WORKFLOW_CONFIG.LEGACY,events=portalActivityEvents(result),last=events[events.length-1];
  return '<aside class="case-context" aria-labelledby="caseActionTitle"><div class="eyebrow">CURRENT ACTION</div><h2 id="caseActionTitle">'+(result.status==='RESOLVED'?'Süreç tamamlandı':'Sıradaki işlem')+'</h2><p class="case-next">'+esc((process.next_action||{}).label||config.next)+'</p><dl><dt>Aksiyon sahibi</dt><dd>'+esc((process.current_owner||{}).label||config.owner)+'</dd></dl><a class="btn" href="#'+actionId+'">'+(actionId==='portalDecisionForm'?'Değerlendirmeye git':'İşlem alanına git')+' '+navIcon('arrow')+'</a><div class="case-last"><span class="eyebrow">SON YAPILAN İŞLEM</span>'+(last?'<strong>'+esc(last.label||WORKFLOW_LABELS[last.status]||'İşlem kaydedildi')+'</strong><span>'+esc(portalActorName(last.actor))+'</span><time>'+portalDateTime(last.at)+'</time>':'<p>İşlem kaydı bulunmuyor.</p>')+'</div></aside>';
}
''')
section('function portalDetailBody(result,admin){', 'function portalReviewEditor(result){', r'''function portalDetailBody(result,admin){
  var ref=result.referral,canReview=result.permissions&&result.permissions.can_review&&result.status!=='RESOLVED',reviewed=admin&&portalReviewAlreadyRecorded(result),firstReview=canReview&&!reviewed;
  var review=canReview?portalReviewEditor(result):'';
  if(reviewed&&review)review='<details class="card review-repeat" '+(portalDraftDirty(portalDraft(result,'decision'),'decision')?'open':'')+'><summary>Değerlendirmeyi güncelle</summary><p class="caption">Biriminizin değerlendirmesi kayıtlı. Gerekirse gerekçesiyle güncelleyin.</p>'+review+'</details>';
  var original='<section class="portal-original"><div class="section-title"><div><div class="eyebrow">TALEBİN KAPSAMI</div><h2>İhtiyaç açıklaması</h2></div></div><p class="original-request">'+esc(result.text||'Açıklama kaydı yok')+'</p>'+(admin?portalReviewReadiness(result):'')+'</section>';
  var brief=admin?'<details class="card ai-result-details" id="portalAnalysisDetails"><summary>Analiz dosyası ve ders kanıtları</summary>'+portalAnalysisBrief(result)+'<details class="ai-result-evidence"><summary>İlk YZ sonucunu ve ihtiyaç bazında ders uyumunu aç</summary>'+renderEmployeeResult(result)+'</details></details>':renderEmployeeResult(result);
  var referral=ref?'<section class="referral-summary"><div><div class="eyebrow">KAYITLI YÖNLENDİRME</div><h2>'+esc(ref.department_label)+'</h2><p>'+esc(ref.analysis_summary)+'</p></div><span class="badge b-blue">'+(ref.active?'Birimde değerlendirme aktif':'Yönlendirme kapatıldı')+'</span></section>':'';
  var status=portalStatusEditor(result,admin);
  if(firstReview)status='<details class="case-secondary-actions" '+(portalDraftDirty(portalDraft(result,'status'),'status')?'open':'')+'><summary>Diğer süreç işlemleri</summary>'+status+'</details>';
  return '<article class="case-file">'+portalCaseHeader(result)+portalProcessSteps(result)+'<div class="case-layout"><div class="case-main">'+original+(firstReview?review:status+review)+brief+referral+(firstReview?status:'')+'</div>'+portalCurrentAction(result,firstReview?'portalDecisionForm':'portalStatusForm')+'</div>'+portalTimeline(result)+(admin?'<details class="card decision-audit"><summary>İnsan kararlarını ilk YZ önerisiyle karşılaştır</summary>'+portalDecisionHistory(result)+'</details>':'')+'</article>';
}
''')
s=s.replace("var statuses=['IN_REVIEW','ACTION_PLANNED','NEEDS_INFO','RESOLVED']", "var statuses=Object.keys(CASE_PRESENTATION.statusActions)")
s=s.replace("({IN_REVIEW:'İhtiyaç analizine geri gönder',ACTION_PLANNED:'Çözüm planını kaydet',NEEDS_INFO:'Talep sahibinden ek bilgi iste',RESOLVED:'Tamamlandı olarak kaydet'}[key])", "CASE_PRESENTATION.statusActions[key]")
section('function portalRouting(result){', 'function portalReviewAction(result,', r'''function portalRouting(result){
  var routing=Object.assign({},result.routing||{resolved:false,requires_selection:true,department:null,reason:'Talebin hedef birimi henüz doğrulanmadı.',options:[{id:'TECHNICAL_DESIGN',label:portalDepartmentLabel('TECHNICAL_DESIGN')},{id:'ENGINEERING_DESIGN',label:portalDepartmentLabel('ENGINEERING_DESIGN')}]}),options=routing.options||[];
  if(!routing.department&&options.length===1){routing.department=options[0].id;routing.department_label=options[0].label;routing.auto_selected=true;routing.requires_selection=false;}
  return routing;
}
''')
s=s.replace("if(action.advance&&$('#decisionRoutingDepartment').required)payload.routing_department=$('#decisionRoutingDepartment').value;", "if(action.advance&&$('#decisionRoutingDepartment').required)payload.routing_department=$('#decisionRoutingDepartment').value;else if(action.advance&&routing.auto_selected&&(outcome==='APPROVED'||!payload.actual_department))payload.routing_department=routing.department;")
s=s.replace("'<div data-no-translate>'+pageHead('Talep #'+PORTAL.selectedId,'İhtiyaç, değerlendirme ve işlem geçmişi.','<button class=\"btn\" data-portal=\"back-to-list\">Talep listesine dön</button>')+'<div id=\"portalDetailContent\">'", "'<div data-no-translate><nav class=\"case-breadcrumb\" aria-label=\"Talep gezinme\"><button class=\"link-btn\" data-portal=\"back-to-list\">← Talep listesi</button><span>/</span><span>#'+Number(PORTAL.selectedId)+'</span></nav><div id=\"portalDetailContent\">'")
p.write_text(s,encoding='utf-8')

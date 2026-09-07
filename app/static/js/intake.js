/* Optional page-local interview. Only the existing request form can submit. */
var INTAKE;
function resetIntake(){INTAKE={mode:'direct',messages:[],answer:'',token:null,response:null,draft:'',directText:'',busy:false,error:'',refining:false,revision:0}}
resetIntake();
function intakeSubmissionToken(){return INTAKE.mode==='ai'&&INTAKE.response&&INTAKE.response.status==='ready'&&!INTAKE.refining?INTAKE.token:null}
function intakeCanSubmit(){return INTAKE.mode==='direct'||!!intakeSubmissionToken()}
function intakeMarkup(){
  var s=INTAKE,r=s.response,ready=r&&r.status==='ready'&&!s.refining;
  return '<div class="intake-modes" role="group" aria-label="Talep hazırlama yöntemi"><button type="button" class="btn '+(s.mode==='direct'?'primary':'')+'" data-intake-mode="direct" aria-pressed="'+(s.mode==='direct')+'">Doğrudan Talep</button><button type="button" class="btn '+(s.mode==='ai'?'primary':'')+'" data-intake-mode="ai" aria-pressed="'+(s.mode==='ai')+'">AI ile Netleştir</button></div>'+(s.mode==='ai'?'<section class="card intake-panel" aria-label="İhtiyaç ön görüşmesi"><div class="section-title"><div><div class="eyebrow">İSTEĞE BAĞLI ÖN GÖRÜŞME</div><h2>'+(ready?'Talebiniz hazır':'İhtiyacınızı birlikte netleştirelim')+'</h2></div><span class="caption">'+(r?r.question_count:0)+' / 4 takip sorusu</span></div><p class="hint">Kısa bir ön görüşmeyle talep taslağınızı hazırlayın. Sınıflandırma ve içerik eşleştirme, siz talebi gönderdikten sonra yapılır.</p><div class="intake-messages" aria-live="polite">'+s.messages.map(function(m){return '<div class="intake-message '+(m.role==='user'?'intake-user':'')+'"><strong>'+(m.role==='user'?'Siz':'İhtiyaç asistanı')+'</strong><p>'+esc(m.text)+'</p></div>'}).join('')+'</div>'+(s.error?'<div class="notice warning" role="alert">'+esc(s.error)+' <button type="button" class="link-btn" data-intake-mode="direct">Doğrudan talebe geç</button></div>':'')+(s.busy?'<p role="status"><span class="spinner"></span> İhtiyacınız netleştiriliyor…</p>':'')+(ready?'<p class="notice">Taslağı aşağıda kontrol edip düzenleyin. Talep yalnızca “Talebi gönder” düğmesine bastığınızda kaydedilir.</p><div class="inline-actions"><button class="btn" type="button" id="intakeEdit">Düzenle</button><button class="btn" type="button" id="intakeRefine" '+(r.question_count>=4?'disabled':'')+'>AI ile biraz daha netleştir</button></div>':'<form id="intakeForm"><div class="field"><label for="intakeAnswer">'+(s.refining?'Neyi değiştirmek veya eklemek istersiniz?':r&&r.question?esc(r.question):'İhtiyacınızı kısaca anlatın')+'</label>'+(r&&r.question_reason&&!s.refining?'<p class="hint">'+esc(r.question_reason)+'</p>':'')+'<textarea id="intakeAnswer" rows="3" maxlength="5000" '+(s.busy?'disabled':'')+'>'+esc(s.answer)+'</textarea></div>'+(!s.refining&&r&&r.suggestions.length?'<div class="inline-actions">'+r.suggestions.map(function(t,i){return '<button type="button" class="btn sm" data-intake-answer="'+i+'" '+(s.busy?'disabled':'')+'>'+esc(t)+'</button>'}).join('')+'</div>':'')+'<p class="caption">Bu görüşmedeki bilgiler mevcut dış AI hizmetinde işlenir. Yalnızca paylaşımı onaylı bilgi kullanın.</p><div class="inline-actions"><button type="submit" class="btn primary" '+(s.busy?'disabled':'')+'>Yanıtı değerlendir</button>'+(s.token?'<button type="button" class="btn" id="intakeFinish" '+(s.busy?'disabled':'')+'>Eldeki bilgilerle taslak hazırla</button>':'')+'</div></form>')+'</section>':'');
}
function mountIntake(){
  var form=$('#submitterRequestForm');if(!form)return;
  var card=form.closest('section'),host=document.createElement('div');host.id='intakeHost';host.innerHTML=intakeMarkup();card.before(host);
  card.hidden=!intakeCanSubmit();
  host.querySelectorAll('[data-intake-mode]').forEach(function(b){b.addEventListener('click',function(){
    if(LIVE_REQUEST.busy||PORTAL_PDF.busy)return;
    if(INTAKE.mode!==b.dataset.intakeMode){
      if(INTAKE.mode==='direct'){INTAKE.directText=LIVE_REQUEST.text;if(!INTAKE.messages.length&&!INTAKE.answer)INTAKE.answer=LIVE_REQUEST.text}
      else {
        if(intakeSubmissionToken())INTAKE.draft=LIVE_REQUEST.text;
        INTAKE.directText=INTAKE.draft||INTAKE.messages.filter(function(m){return m.role==='user'}).map(function(m){return m.text}).concat(INTAKE.answer?[INTAKE.answer]:[]).join('\n\n').slice(0,5000)||INTAKE.directText;
      }
      INTAKE.mode=b.dataset.intakeMode;LIVE_REQUEST.text=INTAKE.mode==='direct'?INTAKE.directText:INTAKE.draft;LIVE_REQUEST.error='';
      if(INTAKE.mode==='direct'&&!LIVE_REQUEST.text)LIVE_REQUEST.text=INTAKE.draft||INTAKE.messages.filter(function(m){return m.role==='user'}).map(function(m){return m.text}).join('\n\n').slice(0,5000)||INTAKE.answer;
    }
    renderPortalRequest();
  })});
  var answer=$('#intakeAnswer');if(answer)answer.addEventListener('input',function(){INTAKE.answer=answer.value});
  host.querySelectorAll('[data-intake-answer]').forEach(function(b){b.addEventListener('click',function(){INTAKE.answer=INTAKE.response.suggestions[Number(b.dataset.intakeAnswer)];answer.value=INTAKE.answer;answer.focus()})});
  var interview=$('#intakeForm');if(interview)interview.addEventListener('submit',function(e){e.preventDefault();runIntake(false)});
  var finish=$('#intakeFinish');if(finish)finish.addEventListener('click',function(){runIntake(true)});
  var edit=$('#intakeEdit');if(edit)edit.addEventListener('click',function(){$('#submitterRequestText').focus()});
  var refine=$('#intakeRefine');if(refine)refine.addEventListener('click',function(){INTAKE.draft=LIVE_REQUEST.text;INTAKE.refining=true;INTAKE.answer='';renderPortalRequest();$('#intakeAnswer').focus()});
}
async function runIntake(finish){
  if(INTAKE.busy||LIVE_REQUEST.busy)return;
  var message=INTAKE.answer.trim();if(!message&&!finish)return;
  var s=INTAKE,generation=PORTAL.accountGeneration,revision=++s.revision;
  s.busy=true;s.error='';renderPortalRequest();
  try{
    var result=await apiRequest('/api/intake',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:message,token:s.token,finish:finish,edited_draft:s.draft||null})},70000);
    if(generation!==PORTAL.accountGeneration||INTAKE!==s||revision!==s.revision)return;
    if(message)s.messages.push({role:'user',text:message});
    if(result.question)s.messages.push({role:'assistant',text:result.question});
    s.response=result;s.token=result.token;s.answer='';s.refining=false;
    if(result.status==='ready'){s.draft=result.draft;if(s.mode==='ai')LIVE_REQUEST.text=s.draft}
  }catch(error){if(generation!==PORTAL.accountGeneration||INTAKE!==s)return;s.error=error.status===409?error.message:'AI ile netleştirme şu anda kullanılamıyor. Metniniz korunuyor; talebinizi doğrudan yazabilirsiniz.'}
  finally{if(generation===PORTAL.accountGeneration&&INTAKE===s){s.busy=false;if(state.currentPage==='submitter-request')renderPortalRequest()}}
}

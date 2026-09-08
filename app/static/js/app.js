/* TUSAŞ live portal: shared rendering, API access and accessible navigation. */
var state={currentRole:'submitter',currentPage:'submitter-home'};
var LIVE_AI={status:'checking',message:'Yapay zekâ bağlantısı kontrol ediliyor.',health:null};
// Request content and unsent drafts stay in memory only.
var LIVE_REQUEST={text:'',result:null,busy:false,error:''};
var DOC_INDEX={report:null,error:'',syncing:false,promise:null,timer:null,offset:0};
/* ---------------- SELECTORS / FORMATTERS ---------------- */
function $(selector){return document.querySelector(selector)}
function originalText(value){return '<span data-no-translate>'+esc(value)+'</span>'}
function esc(value){return String(value==null?"":value).replace(/[&<>"']/g,function(char){return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[char]})}
function fmtDate(value){
  if(!value)return "—";
  try{return new Intl.DateTimeFormat("tr-TR",{day:"2-digit",month:"short",year:"numeric"}).format(new Date(String(value).slice(0,10)+"T12:00:00"))}catch(error){return value}
}
function badge(text){
  var value=String(text||"—"),cls="b-gray";
  if(/Critical|Kritik|Acil|Low Coverage|IMMEDIATE/i.test(value))cls="b-red";
  else if(/High|Yüksek|Watch|Review|İnceleme|Partial|Kısmen|REVISE|HUMAN/i.test(value))cls="b-amber";
  else if(/Healthy|Accepted|Published|Received|Strong|Resolved|USE_EXISTING/i.test(value))cls="b-green";
  else if(/Suggestion|CREATE|Smart|AI/i.test(value))cls="b-purple";
  else if(/Survey|Captured|Ready|Analys/i.test(value))cls="b-blue";
  return '<span class="badge '+cls+'">'+esc(value)+'</span>'
}
function pct(value,total){return total?Math.round(value/total*100):0}
function toast(message){var node=$("#toast");node.textContent=message;node.classList.add("show");setTimeout(function(){node.classList.remove("show")},2800)}
function humanizeEnum(value){
  var labels={
    EGITIM:"Eğitim",PERFORMANS_DESTEGI:"Performans Desteği",SUREC_ARAC:"Süreç / Araç",BILGI:"Bilgi",
    KRITIK_ICERIK:"Kritik İçerik",KARMA:"Karma",DUSUK:"Düşük",ORTA:"Orta",YUKSEK:"Yüksek",ACIL:"Acil",
    BIREYSEL:"Bireysel",EKIP:"Ekip",BIRIM:"Birim",BIRDEN_FAZLA_BIRIM:"Birden Fazla Birim",KURUMSAL:"Kurumsal",
    BELIRSIZ:"Belirsiz",NORMAL:"Normal",YUKSELTILMIS:"Yükseltilmiş",KRITIK:"Kritik",
    KATALOG_ARAMASI:"Katalog Araması",EGITIM_DISI_COZUM:"Eğitim Dışı Çözüm",ACIL_INCELEME:"Acil İnceleme",
    ANALIST_DOGRULAMASI:"Analist Doğrulaması",VAR:"Var",KISMEN_VAR:"Kısmen Var",YOK:"Yok",
    GUCLU:"Güçlü"
  };
  return labels[value]||String(value||"—").replaceAll("_"," ");
}
async function apiRequest(path,options,timeoutMs){
  var controller=new AbortController(),timer=setTimeout(function(){controller.abort()},timeoutMs||30000);
  var requestOptions=Object.assign({},options||{},{signal:controller.signal});
  if(typeof operationsHeaders==='function')requestOptions.headers=operationsHeaders(path,requestOptions.headers);
  try{
    var response;
    try{response=await fetch(path,requestOptions)}catch(networkError){
      if(networkError&&networkError.name==="AbortError")throw networkError;
      LIVE_AI={status:"server_error",message:"Uygulama sunucusuna ulaşılamadı. Sunucunun açık olduğunu kontrol edin; yazdığınız metin korunuyor.",health:null};
      applyAIStatusToCurrentPage();
      throw new Error(LIVE_AI.message);
    }
    var payload=null;
    try{payload=await response.json()}catch(parseError){if(parseError&&parseError.name==="AbortError")throw parseError}
    if(!response.ok){
      if(response.status===401&&path!=='/api/auth/login'&&path!=='/api/admin/login'&&typeof PORTAL!=='undefined'&&PORTAL.user)portalSessionExpired();
      var detail=payload&&typeof payload.detail==="string"?payload.detail:"İstek tamamlanamadı (HTTP "+response.status+").";
      if(payload&&payload.ai_status){
        LIVE_AI={status:payload.ai_status,message:aiStatusMessage(payload),health:payload};
        applyAIStatusToCurrentPage();detail=LIVE_AI.message;
      }
      var failure=new Error(detail);failure.status=response.status;failure.code=payload&&payload.error_code;throw failure;
    }
    if(payload===null)throw new Error("Sunucu yanıtı okunamadı. Sayfayı yenileyip bağlantıyı kontrol edin.");
    return payload;
  }catch(error){
    if(error&&error.name==="AbortError")throw new Error("İşlem zaman aşımına uğradı.");
    throw error;
  }finally{clearTimeout(timer)}
}
function aiStatusMessage(payload){
  var detail=payload.detail||"Yapay zekâ bağlantısı doğrulanamadı.";
  if(payload.quota_limit!=null&&payload.quota_remaining!=null)detail+=' Sınır: '+payload.quota_limit+' istek; kalan: '+payload.quota_remaining+'.';
  if(payload.retry_at){
    var reset=new Date(payload.retry_at);
    if(!Number.isNaN(reset.getTime()))detail+=' Sağlayıcının bildirdiği yeniden deneme zamanı: '+reset.toLocaleString('tr-TR',{timeZone:'Europe/Istanbul'})+' (Türkiye saati).';
  }
  return detail;
}
function renderAIConnectionStatus(){
  var badgeNode=$("#aiConnectionBadge");if(!badgeNode)return;
  var statusMap={
    checking:{text:"YZ kontrol ediliyor",cls:"b-gray"},
    connected:{text:"YZ bağlı",cls:"b-green"},
    off:{text:"YZ kapalı",cls:"b-amber"},
    quota:{text:"YZ kullanım sınırı",cls:"b-amber"},
    credit:{text:"YZ kredi gerekli",cls:"b-amber"},
    server_error:{text:"Sunucuya erişilemiyor",cls:"b-red"},
    error:{text:"YZ bağlantı hatası",cls:"b-red"}
  };
  var item=statusMap[LIVE_AI.status]||statusMap.error;
  badgeNode.className="badge connection-badge "+item.cls;badgeNode.textContent=item.text;badgeNode.title=LIVE_AI.message;
}
function applyAIStatusToCurrentPage(){
  renderAIConnectionStatus();
  var notice=$("#aiAvailabilityNotice"),button=$("#submitterAnalyzeButton");
  if(notice){
    notice.className="notice "+(LIVE_AI.status==="connected"?"success":LIVE_AI.status==="checking"?"":"warning");
    notice.innerHTML="<strong>"+esc(LIVE_AI.status==="connected"?"Bağlantı kontrolü başarılı.":LIVE_AI.status==="checking"?"Bağlantı kontrol ediliyor.":"Analiz şu anda kullanılamıyor.")+"</strong> "+esc(LIVE_AI.message)+" Talebinizi yine de kaydedebilirsiniz; analiz durumu talep detayında izlenir."+
      (LIVE_AI.status!=="checking"&&LIVE_AI.status!=="connected"?' <button type="button" class="link-btn" data-action="retry-ai">Durumu yeniden kontrol et</button>':'');
  }
  // The same failure belongs in one alert, not both the service and form areas.
  var formError=$("#submitterFormError");
  if(formError)formError.innerHTML=LIVE_REQUEST.error&&!(notice&&LIVE_AI.status!=="connected"&&LIVE_AI.status!=="checking"&&LIVE_REQUEST.error===LIVE_AI.message)?'<div class="notice warning">'+esc(LIVE_REQUEST.error)+'</div>':'';
  if(button)button.disabled=!!LIVE_REQUEST.busy;
}
async function checkAIHealth(force){
  LIVE_AI={status:"checking",message:"Yapay zekâ bağlantısı kontrol ediliyor.",health:null};applyAIStatusToCurrentPage();
  try{
    var healthPath=typeof portalIsAdminPage==='function'&&portalIsAdminPage()?'/api/health':'/api/portal/health';
    var health=await apiRequest(healthPath+(force?'?refresh=true':''),{},35000);
    LIVE_AI.health=health;
    LIVE_AI={status:health.ai_status||"error",message:aiStatusMessage(health),health:health};
  }catch(error){LIVE_AI={status:LIVE_AI.status==="server_error"?"server_error":"error",message:error.message||"Bağlantı kontrolü başarısız.",health:null}}
  applyAIStatusToCurrentPage();
}
function pageHead(title,description,actions,crumb){
  return '<div class="breadcrumb">'+esc(crumb||"Kurumsal Öğrenme")+' / '+esc(title)+'</div>'+
    '<div class="page-head"><div><h1>'+esc(title)+'</h1><p>'+description+'</p></div><div class="actions no-print">'+(actions||"")+'</div></div>'
}
function kpi(label,value,sub){
  return '<div class="kpi"><div class="label">'+esc(label)+'</div><div class="value">'+esc(value)+'</div><div class="sub">'+sub+'</div></div>'
}
function barList(rows,maxValue){
  var max=maxValue||Math.max.apply(null,[1].concat(rows.map(function(row){return row.value})));
  return '<div class="bar-list">'+rows.map(function(row){
    return '<div class="bar-row"><span>'+esc(row.label)+'</span><div class="bar-track" aria-hidden="true"><div class="bar-fill '+(row.color||"")+'" style="width:'+Math.max(0,Math.min(100,Math.round(row.value/max*100)))+'%"></div></div><strong>'+esc(row.display==null?row.value:row.display)+'</strong></div>'
  }).join("")+'</div>'
}
function navIcon(name){
  var paths={OV:'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    GD:'<path d="M4 4h7l1 2 1-2h7v15h-7l-1 2-1-2H4zM12 6v15"/>',
    ND:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="4"/><path d="m15 9 6-6"/>',
    SV:'<path d="M4 20V10h4v10m3 0V4h4v16m3 0v-7h4v7M2 20h21"/>',
    RM:'<path d="M5 21V3l7 2 7-2v16l-7 2-7-2M12 5v16"/>',
    SG:'<path d="M3 12h4l3-7 4 14 3-7h4"/>',
    AI:'<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z"/>',
    CR:'<path d="m12 3 10 17H2zM12 9v5m0 3v.1"/>',
    DC:'<path d="M8 3h8l4 4v14H4V3zM8 13l3 3 6-7"/>',
    AU:'<path d="M4 7a9 9 0 1 1-1 8M4 3v5h5M12 7v5l4 2"/>',
    HM:'<path d="m3 10 9-7 9 7v11h-7v-7h-4v7H3z"/>',
    FT:'<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
    NS:'<path d="M12 5v14M5 12h14"/>',
    MR:'<path d="M5 3h14v18H5zM9 8h6M9 12h6M9 16h4"/>',
    CT:'<path d="M4 3h12v17H4zM16 6h4v15H7M7 7h6"/>',
    HQ:'<path d="M3 4h7l2 3h9v13H3zM8 13h8m-3-3 3 3-3 3"/>',
    TL:'<path d="m3 11 18-8-6 18-4-7zM11 14 21 3"/>',
    arrow:'<path d="M5 12h14m-5-5 5 5-5 5"/>'};
  return '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">'+(paths[name==='DB'?'OV':name]||paths.ND)+'</svg>';
}
function renderShell(){return renderPortalShell()}
/* ---------------- ROUTING ---------------- */
function render(){
  if(!PORTAL.user)state.currentPage='portal-login';
  else if(state.currentPage==='portal-delegations')state.currentPage='portal-inbox';
  else if(PORTAL.isAdmin&&state.currentPage!=='admin-panel'&&!/^portal-(inbox|notifications|development|development-detail|catalog|course|publication|training|training-detail|training-create|evaluations|evaluation|skills|skill|my-skills|my-skill|positions|position|my-role|position-planning)$/.test(state.currentPage)){state.currentPage='admin-panel';PORTAL.adminTab='requests'}
  else if(!PORTAL.isAdmin&&!/^(submitter-|portal-)/.test(state.currentPage))state.currentPage='submitter-home';
  renderShell();
  if(renderPortalRoute(state.currentPage))return;
  state.currentPage=PORTAL.user?(PORTAL.isAdmin?'admin-panel':'submitter-home'):'portal-login';
  renderPortalRoute(state.currentPage);
}
function paintDocumentIndex(){
  var node=$("#documentIndexNotice");if(!node)return;
  var report=DOC_INDEX.report,progress=report&&report.progress||{};
  var labels={ready:"Aramada hazır",pending:"İşlenmeyi bekliyor",error:"İşlenemedi"};
  var busy=DOC_INDEX.syncing||progress.running;
  var wasOpen=!!node.querySelector('details[open]');
  var files=report?(report.documents||[]).filter(function(file){return file.status!=="missing"}):[];
  var total=report&&(report.documents_total??files.length)||0,offset=report&&report.offset||0,limit=report&&report.limit||20;
  node.className="notice "+(DOC_INDEX.error||report&&!report.complete&&!busy?"warning":"");
  node.innerHTML='<div class="inline-actions"><strong>Eğitim bilgi kaynakları</strong><button type="button" class="btn sm" data-action="sync-documents" '+(busy||LIVE_REQUEST.busy?'disabled':'')+'>'+(busy?'Klasör eşitleniyor…':'PDF klasörünü eşitle')+'</button></div>'+
    '<p class="caption">Yalnızca aramada hazır dosyalar yeni analizlerde kullanılır. Değişen içerikleri eşitleyerek bilgi havuzunu güncel tutun.</p>'+
    (report?'<p style="margin-top:10px">Klasörde <strong>'+report.files_on_disk+'</strong> PDF · Aramada hazır <strong>'+report.ready_count+'</strong> · Bekleyen '+report.pending_count+' · Hatalı '+report.error_count+'</p>':'<p style="margin-top:10px">Dosyalar kontrol ediliyor…</p>')+
    (busy?'<p role="status">'+(progress.file?esc(progress.file)+' · '+progress.completed_chunks+' / '+progress.total_chunks+' metin parçası':'Klasördeki yeni ve değişmiş dosyalar aramaya hazırlanıyor. İlk eşitleme birkaç dakika sürebilir.')+'</p>':'')+
    (DOC_INDEX.error?'<p role="alert">'+esc(DOC_INDEX.error)+'</p>':'')+
    (report?'<details '+(wasOpen?'open':'')+'><summary>Dosya durumlarını göster</summary><ul class="index-file-list">'+files.map(function(file){return '<li><strong>'+esc(file.file)+'</strong><span>'+esc(labels[file.status]||file.status)+(file.chunks?' · '+file.chunks+' parça':'')+'</span>'+(file.error?'<p>'+esc(file.error)+'</p>':'')+'</li>'}).join('')+'</ul>'+
      (total>limit?'<div class="inline-actions"><button type="button" class="btn sm" data-action="documents-prev" '+(offset===0?'disabled':'')+'>Önceki</button><span>'+Math.min(offset+1,total)+'–'+Math.min(offset+files.length,total)+' / '+total+'</span><button type="button" class="btn sm" data-action="documents-next" '+(offset+limit>=total?'disabled':'')+'>Sonraki</button></div>':'')+
      (!total?'<p>PDF klasöründe dosya bulunmuyor.</p>':'')+'</details>':'');
}
async function loadDocumentStatus(){
  DOC_INDEX.report=await apiRequest('/api/documents/status?offset='+DOC_INDEX.offset+'&limit=20',{},30000);
  DOC_INDEX.offset=DOC_INDEX.report.offset;DOC_INDEX.error="";
  if(DOC_INDEX.timer){clearTimeout(DOC_INDEX.timer);DOC_INDEX.timer=null}
  // Also follow a job started by another tab or resumed after a page reload.
  if(DOC_INDEX.report.progress.running&&!DOC_INDEX.syncing&&$("#documentIndexNotice")){
    DOC_INDEX.timer=setTimeout(function(){loadDocumentStatus().catch(function(error){DOC_INDEX.error=error.message;paintDocumentIndex()})},2000);
  }
  paintDocumentIndex();return DOC_INDEX.report;
}
function mountDocumentIndex(){
  var anchor=$("#aiAvailabilityNotice");if(!anchor)return;
  anchor.insertAdjacentHTML('afterend','<div id="documentIndexNotice" class="notice" data-no-translate style="margin-top:14px"></div>');
  paintDocumentIndex();
  loadDocumentStatus().catch(function(error){DOC_INDEX.error=error.message;paintDocumentIndex()});
}
function ensureDocumentIndex(){
  if(DOC_INDEX.promise)return DOC_INDEX.promise;
  DOC_INDEX.syncing=true;DOC_INDEX.error="";paintDocumentIndex();
  DOC_INDEX.promise=(async function(){
    try{
      await apiRequest('/api/documents/sync',{method:'POST'},30000);
      var deadline=Date.now()+20*60*1000,report;
      do{
        report=await loadDocumentStatus();
        if(!report.progress.running)break;
        if(Date.now()>deadline)throw new Error('PDF hazırlığı sunucuda devam ediyor. Bir süre sonra klasör durumunu tekrar kontrol edin; talebiniz henüz gönderilmedi.');
        await new Promise(function(resolve){setTimeout(resolve,2000)});
      }while(true);
      if(report.progress.error)throw new Error(report.progress.error);
      if(!report.complete){
        var failed=report.documents.filter(function(d){return d.status==='error'||d.status==='pending'});
        throw new Error('PDF dizini tamamlanamadı. '+failed.slice(0,2).map(function(d){return d.file+': '+(d.error||'İşlenmeyi bekliyor')}).join(' · '));
      }
      return report;
    }catch(error){DOC_INDEX.error=error.message;throw error}
    finally{DOC_INDEX.syncing=false;DOC_INDEX.promise=null;paintDocumentIndex()}
  })();
  return DOC_INDEX.promise;
}

var lastFocus=null;
function openModal(content){
  setMobileMenu(false);
  lastFocus=document.activeElement;$("#modal").innerHTML=content;$("#modalBackdrop").classList.add("open");
  $(".app").inert=true;document.body.style.overflow="hidden";
  setTimeout(function(){var focusable=$("#modal").querySelector("button,input,select,textarea");if(focusable)focusable.focus()},0)
}
function closeModal(){
  if(!$("#modalBackdrop").classList.contains("open"))return;
  $("#modalBackdrop").classList.remove("open");$("#modal").innerHTML="";$(".app").inert=false;document.body.style.overflow="";
  if(lastFocus&&lastFocus.isConnected&&lastFocus.focus)lastFocus.focus();lastFocus=null;
}
document.addEventListener('click',function(event){
  var pageButton=event.target.closest('[data-page]');
  if(pageButton){
    if(pageButton.dataset.page==='admin-panel'){PORTAL.adminTab='requests';portalRestoreFilters(true);PORTAL.search='';PORTAL.offset=0}
    state.currentPage=pageButton.dataset.page;render();focusPageStart();return;
  }
  var button=event.target.closest('[data-action]');if(!button)return;
  var action=button.dataset.action;
  if(action==='retry-ai'){checkAIHealth(true);return}
  if(action==='documents-prev'||action==='documents-next'){
    DOC_INDEX.offset=Math.max(0,DOC_INDEX.offset+(action==='documents-next'?20:-20));
    loadDocumentStatus().catch(function(error){DOC_INDEX.error=error.message;paintDocumentIndex()});return;
  }
  if(action==='sync-documents'){ensureDocumentIndex().then(function(){toast('PDF klasörü güncel. Yeni analizler hazır dosyaları kullanacak.')}).catch(function(error){toast(error.message)});return}
  if(action==='close-modal'){closeModal();return}
  if(action==='print')window.print();
});
function setMobileMenu(open){
  $("#sidebar").classList.toggle("open",open);$("#navBackdrop").hidden=!open;
  $("#mobileMenu").setAttribute("aria-expanded",String(open));
  $("#mobileMenu").setAttribute("aria-label",open?"Menüyü kapat":"Menüyü aç");
  document.body.style.overflow=open?"hidden":"";
  $(".main").inert=open;
  if(open){var first=$("#sidebar .nav button");if(first)first.focus()}
}
function focusPageStart(){setMobileMenu(false);$("#appView").focus({preventScroll:true});window.scrollTo({top:0,behavior:"auto"})}
$("#mobileMenu").addEventListener("click",function(){setMobileMenu(!$("#sidebar").classList.contains("open"))});
$("#navBackdrop").addEventListener("click",function(){setMobileMenu(false);$("#mobileMenu").focus()});
window.matchMedia("(min-width:801px)").addEventListener("change",function(event){if(event.matches)setMobileMenu(false)});
$("#modalBackdrop").addEventListener("click",function(event){if(event.target===$("#modalBackdrop"))closeModal()});
document.addEventListener("keydown",function(event){
  if(event.key==="Escape"){
    var wasOpen=$("#sidebar").classList.contains("open");setMobileMenu(false);closeModal();if(wasOpen)$("#mobileMenu").focus();
  }
  var container=$("#modalBackdrop").classList.contains("open")?$("#modal"):$("#sidebar").classList.contains("open")?$("#sidebar"):null;
  if(event.key==="Tab"&&container){
    var items=Array.from(container.querySelectorAll('button:not([disabled]),a[href],input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]')).filter(function(el){return el.getClientRects().length});
    if(!items.length)return;
    if(event.shiftKey&&document.activeElement===items[0]){event.preventDefault();items[items.length-1].focus()}
    else if(!event.shiftKey&&document.activeElement===items[items.length-1]){event.preventDefault();items[0].focus()}
  }
});

document.addEventListener('DOMContentLoaded',function(){initPortal()});

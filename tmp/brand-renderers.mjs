import fs from 'node:fs';
const path = 'C:/Users/Administrator/Desktop/kurumsal-ai-poc/app/static/js/app.js';
const source = fs.readFileSync(path, 'utf8');
const replacements = [
  ['function renderExecutiveOverview(){', 'function renderGuidedDemo(){', String.raw`function renderExecutiveOverview(){
  var signalCounts=DemoDB.aggregate("learningSignals","sourceType"),total=state.learningSignals.length;
  var openReview=state.learningSignals.filter(function(s){return s.openText&&(s.humanStatus==="REVIEW_REQUIRED"||s.humanStatus==="UNCLASSIFIED")}).length;
  var campaign=state.surveyCampaigns[0];
  var lowUnits=campaign.units.filter(function(u){return coverageStatus(u)==="Low Coverage"}).length;
  var critical=state.learningSignals.filter(function(s){return s.riskLevel==="Critical"&&s.status!=="RESOLVED"}).length;
  var activeNeeds=state.needs.filter(function(n){return n.status!=="CLOSED"}).length;
  var existingSolved=state.decisions.filter(function(d){return d.type==="USE_EXISTING"}).length+state.learningSignals.filter(function(s){return s.resolution==="RESOLVED_EXISTING_SOLUTION"}).length;
  var pipeline=state.handoffs.filter(function(h){return h.solutionType==="REVISE_EXISTING"||h.solutionType==="CREATE_NEW"}).length;
  var sourceRows=["Annual Survey","Manual Request","Course Feedback","Instructor Feedback","External Learning Platform","Content / Critical"].map(function(source){return {label:SOURCE_META[source].short,value:signalCounts[source]||0}});
  var topNeeds=state.needs.slice().sort(function(a,b){return b.signalIds.length-a.signalIds.length}).slice(0,5).map(function(n){return {label:n.title,value:n.signalIds.length}});
  var target=campaign.units.reduce(function(sum,u){return sum+u.target},0),responses=campaign.units.reduce(function(sum,u){return sum+u.responses},0);
  var outcomes=[{label:"Mevcut eğitimle çözüm",value:state.decisions.filter(function(d){return d.type==="USE_EXISTING"}).length},{label:"İçerik revizyonu",value:state.decisions.filter(function(d){return d.type==="REVISE_EXISTING"}).length},{label:"Yeni çözüm tasarımı",value:state.decisions.filter(function(d){return d.type==="CREATE_NEW"}).length},{label:"Analiz devam ediyor",value:state.needs.filter(function(n){return n.status==="ANALYSING"||n.status==="READY_FOR_DECISION"}).length}];
  function priority(number,title,sub,page,risk){return '<button class="priority-link '+(risk?'risk':'')+'" data-page="'+page+'"><span class="priority-number">'+number+'</span><span>'+title+'<small>'+sub+'</small></span>'+navIcon('arrow')+'</button>'}
  $("#appView").innerHTML='<div data-no-translate><section class="hero"><div><div class="eyebrow">Kurumsal öğrenme · Yönetim özeti</div><h1>Geleceğin yetkinliklerini<br>bugünden görün.</h1><p>Öğrenme ihtiyaçlarını ortak bir görünümde değerlendirin. Kanıtları izleyin, öncelikleri belirleyin ve gelişime yön veren kararlar alın.</p><div class="inline-actions"><button class="btn primary" data-page="needs">İhtiyaçları incele '+navIcon('arrow')+'</button><button class="btn" data-page="guided-demo">Platformu keşfet</button></div></div><aside class="hero-aside"><h2>İnceleme gündemi</h2>'+priority(openReview,'Sınıflandırma bekleyen','Açık uçlu öğrenme sinyali','open-analysis')+priority(lowUnits,'Katılımı düşük birim','Anket kapsamını değerlendirin','survey')+priority(critical,'Kritik inceleme','Öncelikli içerik kontrolü','critical',true)+'</aside></section>'+
    '<div class="grid kpis">'+kpi('Öğrenme sinyali',total,'farklı kaynaklardan kayıt')+kpi('Aktif ihtiyaç',activeNeeds,'ortak ihtiyaç başlığı')+kpi('İnceleme bekleyen',openReview,'açık uçlu sinyal')+kpi('Düşük katılımlı birim',lowUnits,'kapsam değerlendirmesi')+kpi('Mevcut çözüm',existingSolved,'kayıtlı insan kararı')+kpi('Tasarım aktarımı',pipeline,'revizyon veya yeni çözüm')+'</div>'+
    '<div class="grid chart-grid"><section class="card"><div class="section-title"><div><div class="eyebrow">Veri kaynakları</div><h2>Öğrenme sinyalleri nereden geliyor?</h2></div></div>'+barList(sourceRows)+'<p class="caption">'+total+' gösterim kaydı. Kayıt sayısı, tekil çalışan sayısını ifade etmez.</p></section>'+
    '<section class="card"><div class="section-title"><div><div class="eyebrow">İhtiyaç görünümü</div><h2>Öne çıkan öğrenme alanları</h2></div><button class="link-btn" data-page="needs">Tümünü gör →</button></div>'+barList(topNeeds)+'<p class="caption">Sinyal hacmine göre sıralanır. Nihai öncelik, insan değerlendirmesiyle belirlenir.</p></section>'+
    '<section class="card"><div class="section-title"><h2>Anket katılım kapsamı</h2><button class="link-btn" data-page="survey">Detaya git →</button></div><div class="metric-row"><div class="mini-metric"><div class="n">%'+pct(responses,target)+'</div><div class="t">Genel yanıt oranı</div></div><div class="mini-metric"><div class="n">'+campaign.units.length+'</div><div class="t">İzlenen birim</div></div></div><div class="progress" aria-hidden="true"><span style="width:'+pct(responses,target)+'%"></span></div><p class="caption">'+target+' hedef katılımcıdan '+responses+' yanıt.</p><div class="notice warning"><strong>Sinyal olmaması, ihtiyaç olmadığı anlamına gelmez.</strong> Katılımı düşük '+lowUnits+' birimi analiz kapsamıyla birlikte değerlendirin.</div></section>'+
    '<section class="card"><div class="section-title"><h2>Çözüm ve karar görünümü</h2></div>'+barList(outcomes)+'<p class="caption">Mevcut bir eğitimin bulunması, ihtiyacı tamamen karşıladığı anlamına gelmez.</p></section></div>'+
    '<section class="card" style="margin-top:24px"><div class="section-title"><div><div class="eyebrow">Kanıttan karara</div><h2>Her kararın bir dayanağı var.</h2></div><button class="btn sm" data-need-id="NEED-0028">Örnek kanıt zinciri '+navIcon('arrow')+'</button></div><div class="grid three-grid"><div><h3>01 · Ortak ihtiyaç</h3><p>Anket, talep ve geri bildirimlerden gelen benzer sinyaller aynı ihtiyaç altında bir araya gelir.</p></div><div><h3>02 · İnsan değerlendirmesi</h3><p>Kanıt, içerik kapsamı ve kritik riskler birlikte incelenir. Öneri ile nihai karar ayrı tutulur.</p></div><div><h3>03 · İzlenebilir aktarım</h3><p>Kararın gerekçesi ve kaynakları, eğitim tasarım birimine yapılan aktarımla birlikte korunur.</p></div></div></section></div>';
}

`],
  ['function renderSubmitterHome(){', 'function renderRealAIResult(result){', String.raw`function renderSubmitterHome(){
  $("#appView").innerHTML='<div data-no-translate><section class="hero"><div><div class="eyebrow">Çalışan işlem merkezi</div><h1>Gelişiminiz, bir ihtiyaçla başlar.</h1><p>Eğitim, süreç, araç veya bilgi ihtiyacınızı kendi cümlelerinizle paylaşın. Yapay zekâ ilk analizi hazırlasın, kaynakları göstersin ve uygun değerlendirme adımını önersin.</p><div class="inline-actions"><button class="btn primary" data-page="submitter-request">İhtiyacımı paylaş '+navIcon('arrow')+'</button></div></div><div class="brand-illustration"><img src="/static/assets/brand/emblem.svg" alt="TUSAŞ amblemi" width="91" height="121"><span>BİLGİDEN GELİŞİME, BİRLİKTE.</span></div></section><div id="aiAvailabilityNotice" class="notice"></div><div class="three-grid" style="margin-top:24px"><article class="card process-card"><div class="step-number">01 / PAYLAŞIN</div><h2>İhtiyacınızı anlatın</h2><p>Yaptığınız işi, karşılaştığınız güçlüğü ve ulaşmak istediğiniz sonucu kısa bir metinle açıklayın.</p></article><article class="card process-card"><div class="step-number">02 / KEŞFEDİN</div><h2>İçerikle eşleştirin</h2><p>İndekslenmiş eğitim PDF’leri taranır. İlgili sayfalar, kapsam ve eksik kalan konular görünür olur.</p></article><article class="card process-card"><div class="step-number">03 / DEĞERLENDİRİN</div><h2>Kanıtla ilerleyin</h2><p>İlk analiz bir öneridir. Kritik, belirsiz veya eğitim dışı ihtiyaçlar için uygun inceleme adımı belirtilir.</p></article></div></div>';
  applyAIStatusToCurrentPage();
}
function renderSubmitterRequest(){
  $("#appView").innerHTML='<div data-no-translate>'+pageHead("İhtiyacınızı paylaşın","İlk analiz için bağlamı ve beklediğiniz sonucu anlatmanız yeterli.",'<button class="btn" data-page="submitter-home">Ana sayfaya dön</button>')+
    '<div class="request-layout"><section class="card request-form-card"><form id="submitterRequestForm"><div class="field"><label for="submitterRequestText">Hangi konuda desteğe ihtiyacınız var? <span aria-hidden="true">*</span></label><textarea id="submitterRequestText" required minlength="3" maxlength="5000" rows="8" aria-describedby="requestHint requestPrivacy" placeholder="Örneğin: Haftalık raporlarda veriyi elle birleştiriyoruz. Ekip olarak daha hızlı ve hatasız rapor hazırlamak için uygulamalı desteğe ihtiyacımız var." '+(LIVE_REQUEST.busy?'disabled':'')+'>'+esc(LIVE_REQUEST.text)+'</textarea><div class="field-foot"><p class="hint" id="requestHint">İşiniz · Yaşadığınız güçlük · Beklediğiniz sonuç</p><span class="character-count" id="requestCharacterCount">'+LIVE_REQUEST.text.length.toLocaleString('tr-TR')+' / 5.000</span></div></div><div id="aiAvailabilityNotice" class="notice"></div><div id="submitterFormError" class="notice warning" style="'+(LIVE_REQUEST.error?'':'display:none;')+'margin-top:14px" role="alert">'+esc(LIVE_REQUEST.error)+'</div><div class="form-actions"><button class="btn primary" id="submitterAnalyzeButton" type="submit" disabled>'+(LIVE_REQUEST.busy?'<span class="spinner" aria-hidden="true"></span>Analiz hazırlanıyor…':'Gönder ve analiz et '+navIcon('arrow'))+'</button></div><p class="caption">Talebiniz analiz için sunucuya gönderilir ve kayıt altına alınır.</p></form></section><aside class="card request-help"><h2>İyi bir analiz için</h2><ol><li><strong>Bağlamı ekleyin</strong>Ne yapmaya çalıştığınızı ve güçlüğün nerede oluştuğunu yazın.</li><li><strong>Sonucu tarif edin</strong>Hangi beceriye, bilgiye veya iş yapış değişikliğine ihtiyaç duyduğunuzu belirtin.</li><li><strong>Kapsamı açıklayın</strong>İhtiyaç yalnızca sizi mi, ekibinizi mi etkiliyor? Acil bir durum var mı?</li></ol><div class="notice warning" id="requestPrivacy"><strong>Bilgi güvenliği</strong><br>Bu geliştirme ortamında yalnızca sentetik veya dış servisle paylaşımı onaylı bilgi kullanın. Kişisel veri, gizli proje ve kurum sırrı paylaşmayın.</div></aside></div><div id="submitterAnalysisResult" class="request-result" tabindex="-1" aria-busy="'+LIVE_REQUEST.busy+'">'+(LIVE_REQUEST.result?renderRealAIResult(LIVE_REQUEST.result):'')+'</div></div>';
  bindSubmitterRequestForm();applyAIStatusToCurrentPage();
}
`],
  ['function bindSubmitterRequestForm(){', '/* ---------------- MODALS ---------------- */', String.raw`function bindSubmitterRequestForm(){
  var form=$("#submitterRequestForm");if(!form)return;
  $("#submitterRequestText").addEventListener("input",function(event){
    LIVE_REQUEST.text=event.target.value;
    $("#requestCharacterCount").textContent=LIVE_REQUEST.text.length.toLocaleString('tr-TR')+' / 5.000';
  });
  form.addEventListener("submit",async function(event){
    event.preventDefault();if(LIVE_REQUEST.busy)return;
    var requestText=String($("#submitterRequestText").value||"").trim();
    LIVE_REQUEST.error="";
    if(requestText.length<3){LIVE_REQUEST.error="Lütfen ihtiyacınızı en az üç karakterle açıklayın.";renderSubmitterRequest();$("#submitterRequestText").focus();return}
    if(LIVE_AI.status!=="connected"){LIVE_REQUEST.error="Yapay zekâ bağlantısı hazır değil. Bağlantı durumunu kontrol edip tekrar deneyin.";renderSubmitterRequest();return}
    LIVE_REQUEST.text=requestText;LIVE_REQUEST.result=null;LIVE_REQUEST.busy=true;renderSubmitterRequest();
    try{
      LIVE_REQUEST.result=await apiRequest("/api/requests/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text:requestText})},195000);
      toast("İlk analiz hazır. Sonuçları ve kaynakları inceleyebilirsiniz.");
    }catch(error){LIVE_REQUEST.error=error.message||"Analiz yapılamadı. Lütfen tekrar deneyin."}
    finally{
      LIVE_REQUEST.busy=false;
      if(state.currentPage==="submitter-request"){
        renderSubmitterRequest();
        var target=$(LIVE_REQUEST.result?"#submitterAnalysisResult":"#submitterRequestText");
        if(target){target.focus({preventScroll:true});target.scrollIntoView({block:"start",behavior:"auto"})}
      }
    }
  });
}

`]
];
let patch = `*** Begin Patch\n*** Update File: ${path}\n`;
for (const [start, end, replacement] of replacements) {
  const a = source.indexOf(start), b = source.indexOf(end,a+start.length);
  if (a < 0 || b < 0) throw new Error('Missing renderer boundary: '+start);
  const old = source.slice(a,b).replace(/\r/g,'').trimEnd();
  patch += '@@\n' + old.split('\n').map(l=>'-'+l).join('\n')+'\n'+replacement.trimEnd().split('\n').map(l=>'+'+l).join('\n')+'\n';
}
process.stdout.write(patch+'*** End Patch\n');

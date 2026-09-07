(function(){
"use strict";

/* Eski tarayıcı-içi kural/anahtar kelime motoru devre dışıdır.
   Canlı analiz ana uygulamadaki /api/requests/analyze akışından yapılır. */
return;

/* ============================================================
   TUSAŞ FAZ 3.1 — ODAKLI ARAYÜZ + 5. ROL + GELİŞMİŞ YZ
   - Mevcut Faz 1/2/3 katmanlarını kaldırmaz.
   - Üstlerine güvenli override olarak eklenir.
   ============================================================ */

if (typeof state==="undefined" || typeof DemoDB==="undefined") {
  console.error("TUSAŞ Faz 3.1: ana uygulama bulunamadı.");
  return;
}

/* ---------------- 1) BEŞİNCİ ROL: TALEP İLETME ---------------- */

PERSONAS.submitter = {
  label:"Talep İletme — Çalışan",
  name:"Demo Talep Sahibi",
  personRole:"Talep İletme",
  org:"Kurumsal Çalışan Görünümü"
};

var _defaultPage31 = defaultPage;
defaultPage = function(role){
  if(role==="submitter") return "submitter-home";
  return _defaultPage31(role);
};

var _listNav31 = listNav;
listNav = function(){
  if(state.currentRole==="submitter"){
    return [
      ["submitter-home","HM","Ana Sayfa"],
      ["submitter-request","TL","Talep İlet"],
      ["find-training","EA","Eğitim Ara"],
      ["my-requests","TK","Taleplerim"]
    ];
  }
  return _listNav31();
};

/* ---------------- 2) ODAK MODU ---------------- */

function ensureFocusStyles(){
  if(document.getElementById("tusas-focus-styles")) return;
  var style=document.createElement("style");
  style.id="tusas-focus-styles";
  style.textContent=`
    body.tusas-focus .demo-strip{display:none!important}
    body.tusas-focus .breadcrumb{display:none!important}
    body.tusas-focus .side-card{display:none!important}
    body.tusas-focus .page-head{margin-bottom:12px}
    body.tusas-focus .page-head p{display:none!important}
    body.tusas-focus .hero .north-star{display:none!important}
    body.tusas-focus .story-grid{display:none!important}
    body.tusas-focus .caption.focus-optional,
    body.tusas-focus .focus-optional{display:none!important}
    body.tusas-focus .card{padding:16px}
    body.tusas-focus .hero{padding:20px 22px}
    body.tusas-focus .content{padding-top:16px}
    .focus-toggle{white-space:nowrap}
    .quick-action-btn{background:#DD140E!important;border-color:#DD140E!important;color:#fff!important}
    .quick-action-btn:hover{filter:brightness(.95)}
    .ai-confidence{font-weight:850}
    .submitter-shell{max-width:1040px;margin:0 auto}
    .submitter-hero{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:16px;align-items:stretch}
    .submitter-actions{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:14px}
    .submitter-action{min-height:150px;display:flex;flex-direction:column}
    .submitter-action .btn{margin-top:auto;align-self:flex-start}
    .ai-result-compact{border-top:4px solid #263685}
    .ai-result-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
    .ai-chip{border:1px solid var(--line);background:#fafcfd;border-radius:8px;padding:10px}
    .ai-chip .k{font-size:9px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);font-weight:850}
    .ai-chip .v{font-size:13px;font-weight:800;margin-top:4px}
    .quick-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
    @media(max-width:920px){
      .submitter-hero,.submitter-actions,.quick-grid,.ai-result-grid{grid-template-columns:1fr}
    }
  `;
  document.head.appendChild(style);
}

function focusEnabled(){
  return localStorage.getItem("tusas-focus-mode")!=="off";
}
function applyFocusMode(){
  document.body.classList.toggle("tusas-focus",focusEnabled());
  var btn=document.querySelector("[data-focus-toggle]");
  if(btn) btn.textContent=focusEnabled()?"Detayları Göster":"Odak Modu";
}
function toggleFocusMode(){
  localStorage.setItem("tusas-focus-mode",focusEnabled()?"off":"on");
  applyFocusMode();
}
function addTopActions31(){
  var top=document.querySelector(".top-actions");
  if(!top) return;
  if(!top.querySelector("[data-quick-action]")){
    var q=document.createElement("button");
    q.className="btn sm quick-action-btn";
    q.setAttribute("data-quick-action","1");
    q.textContent="+ Yeni İşlem";
    top.insertBefore(q,top.firstChild);
  }
  if(!top.querySelector("[data-focus-toggle]")){
    var f=document.createElement("button");
    f.className="btn sm focus-toggle";
    f.setAttribute("data-focus-toggle","1");
    f.textContent=focusEnabled()?"Detayları Göster":"Odak Modu";
    top.insertBefore(f,top.firstChild);
  }
  applyFocusMode();
}

/* ---------------- 3) GELİŞMİŞ YZ MOTORU ---------------- */

var AI31 = {
  version:31,
  autoThreshold:84,
  reviewThreshold:68,
  domains:[
    {
      name:"Veri Analitiği ve Raporlama",
      phrases:[
        ["power bi",10],["dashboard",9],["dax",10],["power query",9],["excel",7],["pivot",8],
        ["raporlama",7],["rapor",5],["görselleştirme",7],["grafik",4],["veri analizi",8],["büyük veri",6]
      ],
      sub:[
        ["Power BI ve Gösterge Paneli",["power bi","dashboard","dax"]],
        ["Excel ve Pivot Analizi",["excel","pivot"]],
        ["Power Query ve Veri Hazırlama",["power query","veri temiz"]],
        ["Raporlama ve Görselleştirme",["rapor","görselleştirme","grafik"]]
      ]
    },
    {
      name:"Teknik Emniyet ve Güvenlik",
      phrases:[
        ["kimyasal dökülme",12],["güvenlik",8],["emniyet",8],["acil durum",9],["prosedür",6],
        ["saha güvenliği",10],["tehlike",9],["iş güvenliği",10],["riskli",7],["olay bildirimi",7]
      ],
      sub:[
        ["Kimyasal ve Acil Durum Güvenliği",["kimyasal","dökülme","acil durum"]],
        ["Saha Emniyeti",["saha","güvenlik","emniyet"]],
        ["Prosedür ve Olay Bildirimi",["prosedür","olay bildirimi"]]
      ]
    },
    {
      name:"Proje Yönetimi",
      phrases:[
        ["proje",8],["proje riski",10],["risk yönetimi",10],["paydaş",8],["planlama",6],
        ["takvim",5],["iş paketi",7],["kapsam yönetimi",7]
      ],
      sub:[
        ["Proje Risk Yönetimi",["risk"]],
        ["Planlama ve Takvim",["planlama","takvim","iş paketi"]],
        ["Paydaş Yönetimi",["paydaş"]]
      ]
    },
    {
      name:"Dijital Araçlar ve AI",
      phrases:[
        ["yapay zek",10],["üretken yapay",11],[" ai ",7],["prompt",8],["istem",7],
        ["copilot",9],["otomasyon",6],["dijital araç",7],["llm",10],["doğrulama",5]
      ],
      sub:[
        ["Üretken Yapay Zekâ",["yapay zek","üretken","llm","copilot"]],
        ["İstem Tasarımı",["prompt","istem"]],
        ["Dijital Otomasyon",["otomasyon","dijital araç"]],
        ["Doğrulama ve Güvenli Kullanım",["doğrulama","güvenli"]]
      ]
    },
    {
      name:"Teknik Operasyon",
      phrases:[
        ["ekipman",8],["operasyon",8],["standart iş",10],["teknik kayıt",9],["bakım",7],
        ["iş talimatı",9],["kontrol kaydı",8],["operasyon adımı",9]
      ],
      sub:[
        ["Ekipman ve Kontrol",["ekipman","kontrol","bakım"]],
        ["Standart İş",["standart iş","iş talimatı"]],
        ["Operasyonel Kayıt",["teknik kayıt","kontrol kaydı"]]
      ]
    },
    {
      name:"Liderlik ve İletişim",
      phrases:[
        ["liderlik",9],["lider",7],["geri bildirim",10],["zor görüşme",10],["iletişim",8],
        ["çatışma",8],["koçluk",7],["ekip yönetimi",9]
      ],
      sub:[
        ["Geri Bildirim ve Zor Görüşmeler",["geri bildirim","zor görüşme"]],
        ["Ekip Liderliği",["lider","koçluk","ekip yönetimi"]],
        ["İletişim ve Çatışma",["iletişim","çatışma"]]
      ]
    },
    {
      name:"Kalite ve Süreç",
      phrases:[
        ["kök neden",11],["problem çöz",10],["kalite",9],["süreç iyileştirme",10],["8d",10],
        ["fmea",10],["uygunsuzluk",8],["hata analizi",9],["iyileştirme",6]
      ],
      sub:[
        ["Kök Neden ve Problem Çözme",["kök neden","problem çöz","8d"]],
        ["Kalite Araçları",["kalite","fmea","uygunsuzluk"]],
        ["Süreç İyileştirme",["süreç iyileştirme","iyileştirme"]]
      ]
    },
    {
      name:"Çalışma Verimliliği",
      phrases:[
        ["zaman yönetimi",10],["zaman kaybı",8],["iş akışı",8],["bilgi paylaşımı",8],
        ["doküman yönetimi",8],["verimlilik",9],["günlük planlama",8]
      ],
      sub:[
        ["Zaman ve İş Akışı Yönetimi",["zaman","iş akışı","günlük planlama"]],
        ["Bilgi ve Doküman Yönetimi",["bilgi paylaşımı","doküman yönetimi"]]
      ]
    }
  ]
};

function lower31(v){return String(v||"").toLocaleLowerCase("tr-TR");}
function hash31(s){
  var h=2166136261,str=String(s||"");
  for(var i=0;i<str.length;i++){h^=str.charCodeAt(i);h=Math.imul(h,16777619)}
  return Math.abs(h>>>0);
}
function phraseHits31(text,domain){
  var v=" "+lower31(text)+" ",score=0,hits=[];
  domain.phrases.forEach(function(p){
    var term=p[0],w=p[1];
    if(v.indexOf(term)>-1){score+=w;hits.push(term)}
  });
  return {score:score,hits:hits};
}
function chooseSub31(text,domain){
  var v=lower31(text),best=domain.name,n=-1;
  domain.sub.forEach(function(row){
    var c=row[1].reduce(function(sum,t){return sum+(v.indexOf(t)>-1?1:0)},0);
    if(c>n){n=c;best=row[0]}
  });
  return n>0?best:domain.name;
}
function sourceBoost31(signal){
  if(signal.sourceType==="Content / Critical")return 7;
  if(signal.sourceType==="Manual Request")return 4;
  if(signal.sourceType==="Course Feedback")return 3;
  if(signal.sourceType==="Instructor Feedback")return 3;
  return 1;
}
function classify31(signal){
  var text=signal.rawText||signal.summary||"";
  var ranked=AI31.domains.map(function(d){
    var x=phraseHits31(text,d);
    return {domain:d,score:x.score,hits:x.hits};
  }).sort(function(a,b){return b.score-a.score});

  var top=ranked[0],second=ranked[1];
  if(!top||top.score<=0){
    return {
      category:"Genel Gelişim / Analist İncelemesi",
      subtopic:"Belirsiz gelişim konusu",
      confidence:52 + (hash31(signal.id)%7),
      hits:[]
    };
  }

  var margin=top.score-(second?second.score:0);
  var specificity=Math.min(20,top.hits.length*4);
  var base=54 + Math.min(25,top.score*1.35) + Math.min(12,margin*1.2) + specificity + sourceBoost31(signal);
  var tieJitter=(hash31(signal.id+"|"+text)%7)-3;  // yalnızca aynı skorlu kayıtların birebir aynı görünmesini engeller
  var confidence=Math.max(55,Math.min(98,Math.round(base+tieJitter)));

  return {
    category:top.domain.name,
    subtopic:chooseSub31(text,top.domain),
    confidence:confidence,
    hits:top.hits.slice(0,6)
  };
}
function words31(text){
  var stop=new Set(["ve","veya","ile","için","bir","bu","da","de","çok","daha","gibi","olan","olarak","eğitim","eğitimi","istiyorum","istiyoruz","gerekiyor","gerekli"]);
  return lower31(text).replace(/[^\p{L}\p{N}\s]/gu," ").split(/\s+/).filter(function(w){return w.length>3&&!stop.has(w)});
}
function similarity31(a,b){
  var A=new Set(words31(a)),B=new Set(words31(b));
  if(!A.size||!B.size)return 0;
  var i=0;A.forEach(function(x){if(B.has(x))i++});
  return i/Math.max(A.size,B.size);
}
function similar31(signal){
  return state.learningSignals.filter(function(s){return s.id!==signal.id})
    .map(function(s){return {id:s.id,score:similarity31(signal.rawText||signal.summary,s.rawText||s.summary)} })
    .filter(function(x){return x.score>=.28})
    .sort(function(a,b){return b.score-a.score})
    .slice(0,5);
}
function request31(signal){return signal.requestId?DemoDB.findById("requests",signal.requestId):null;}
function risk31(signal){
  var v=lower31(signal.rawText||signal.summary),req=request31(signal);
  if(signal.riskLevel==="Critical"||(req&&req.issueFlag))return {level:"Kritik",score:100};
  if(/yanlış prosedür|yanlış olabilir|kimyasal dökülme|tehlikeli|yaralanma|kaza riski|güvenlik açığı/.test(v))return {level:"Kritik",score:93};
  if(/güvenlik|emniyet|kimyasal|prosedür|saha/.test(v))return {level:"Yükseltilmiş",score:64+(hash31(signal.id)%9)};
  return {level:"Normal",score:15+(hash31(signal.id)%13)};
}
function urgency31(signal){
  var req=request31(signal),v=lower31((signal.rawText||"")+" "+(req?req.desiredPeriod:""));
  if(/acil|hemen|ivedi|mümkün olan en kısa/.test(v))return "Yüksek";
  if(/gelecek dönem|acil değil/.test(v))return "Düşük";
  return "Orta";
}
function impact31(signal){
  var req=request31(signal),a=req?lower31(req.affected):"";
  if(signal.riskLevel==="Critical"||(req&&req.issueFlag))return "Kritik";
  if(a.indexOf("birden fazla")>-1||a.indexOf("bölüm")>-1)return "Yüksek";
  if(a.indexOf("ekib")>-1)return "Orta";
  if(a.indexOf("sadece")>-1)return "Düşük";
  return "Orta";
}
function courseMatch31(signal,cls){
  var v=lower31(signal.rawText||signal.summary);
  return state.courses.map(function(c){
    var score=18,why=[];
    if(c.topic===cls.category){score+=43;why.push("konu alanı eşleşiyor")}
    (c.skills||[]).concat(c.tags||[]).forEach(function(t){
      var tl=lower31(t);
      if(tl.length>2&&v.indexOf(tl)>-1){score+=8;why.push(t+" eşleşiyor")}
    });

    if(c.id==="CRS-003"&&/power bi|dashboard|dax/.test(v)){
      score=/dax|ileri|yönetim dashboard|yönetim rapor/.test(v)?58:82;
      why=["Power BI konusu eşleşiyor",score<70?"ileri seviye kapsam açığı var":"temel ihtiyaçla güçlü eşleşme"];
    }
    if(c.id==="CRS-002"&&/excel|pivot|power query/.test(v)){
      score=/power query|ileri excel|pivot/.test(v)?76:67;
      why=["Excel veri analiziyle ilişkili"];
    }

    score=Math.max(20,Math.min(95,score+(hash31(signal.id+c.id)%5)-2));
    return {
      courseId:c.id,
      score:score,
      coverage:score>=78?"Güçlü":score>=48?"Kısmi":"Düşük",
      reason:why.length?Array.from(new Set(why)).slice(0,3).join(" · "):"doğrudan beceri eşleşmesi sınırlı"
    };
  }).sort(function(a,b){return b.score-a.score}).slice(0,3);
}
function recommendation31(ai){
  if(ai.risk.level==="Kritik")return {code:"IMMEDIATE_REVIEW",label:"Acil insan incelemesine al"};
  if(ai.confidence<AI31.reviewThreshold)return {code:"REVIEW",label:"Analist doğrulamasına gönder"};
  var best=ai.courseMatches[0];
  if(best&&best.score>=78)return {code:"USE_EXISTING",label:"Mevcut eğitime yönlendir"};
  if(best&&best.score>=48)return {code:"REVISE_EXISTING",label:"Mevcut eğitimin kapsamını güncelle"};
  return {code:"CREATE_NEW",label:"Yeni çözüm ihtiyacını değerlendir"};
}
function analyzeSignal31(signal){
  var cls=classify31(signal),risk=risk31(signal),courses=courseMatch31(signal,cls),sim=similar31(signal);
  var need=findNeedByTitle(cls.category);
  var ai={
    version:AI31.version,
    analyzedAt:new Date().toISOString(),
    category:cls.category,
    subtopic:cls.subtopic,
    confidence:cls.confidence,
    matchedTerms:cls.hits,
    risk:risk,
    urgency:urgency31(signal),
    impact:impact31(signal),
    similarSignals:sim,
    similarCount:sim.length,
    courseMatches:courses,
    recommendedNeedId:need?need.id:null
  };
  ai.recommendation=recommendation31(ai);
  ai.summary="Kategori: "+ai.category+" · Alt konu: "+ai.subtopic+" · Güven: %"+ai.confidence+
    " · "+(courses[0]?(courseName(courses[0].courseId)+" için "+courses[0].coverage.toLocaleLowerCase("tr-TR")+" kapsam"):"uygun eğitim eşleşmesi yok")+
    " · Öneri: "+ai.recommendation.label+".";
  ai.explainability=[];
  if(ai.matchedTerms.length)ai.explainability.push("Metinde belirleyici ifadeler: "+ai.matchedTerms.join(", "));
  if(ai.similarCount)ai.explainability.push(ai.similarCount+" benzer geçmiş kayıt bulundu.");
  if(courses[0])ai.explainability.push("En güçlü eğitim eşleşmesi: "+courseName(courses[0].courseId)+" (%"+courses[0].score+").");
  signal.aiAnalysis=ai;
  signal.suggestedCluster=ai.category;
  signal.suggestionConfidence=ai.confidence;
  signal.suggestedNeedId=ai.recommendedNeedId;
  return ai;
}
function applyAI31(signal){
  var ai=signal.aiAnalysis||analyzeSignal31(signal);
  if(ai.risk.level==="Kritik"){
    signal.status="IMMEDIATE_REVIEW";
    signal.humanStatus="REVIEW_REQUIRED";
    signal.riskLevel="Critical";
    return;
  }
  if(ai.confidence>=AI31.autoThreshold && ai.recommendedNeedId){
    signal.topicHint=ai.category;
    signal.humanStatus="ACCEPTED";
    signal.status="CLASSIFIED";
    if(signal.linkedNeedIds.indexOf(ai.recommendedNeedId)===-1){
      var n=DemoDB.findById("needs",ai.recommendedNeedId);
      if(n){
        signal.linkedNeedIds.push(ai.recommendedNeedId);
        if(n.signalIds.indexOf(signal.id)===-1)n.signalIds.push(signal.id);
        signal.status="LINKED";
      }
    }
  } else if(ai.confidence>=AI31.reviewThreshold){
    signal.humanStatus="REVIEW_REQUIRED";
    signal.status="HUMAN_REVIEW";
  } else {
    signal.humanStatus="UNCLASSIFIED";
    signal.status="UNCLASSIFIED";
  }
}
function reanalyzeAll31(){
  state.learningSignals.forEach(function(s){analyzeSignal31(s);applyAI31(s)});
  state.requests.forEach(function(r){
    var s=DemoDB.findById("learningSignals",r.signalId);
    if(s&&s.aiAnalysis){
      r.aiAnalysis=clone(s.aiAnalysis);
      if(s.linkedNeedIds.length)r.needId=s.linkedNeedIds[0];
      r.status=s.aiAnalysis.risk.level==="Kritik"?"Acil İnceleme":
        s.humanStatus==="ACCEPTED"?"Yapay Zekâ Tarafından Analiz Edildi":"Analist Doğrulaması Bekleniyor";
    }
  });
  state.aiEngineMeta=state.aiEngineMeta||{};
  state.aiEngineMeta.phase31=true;
  state.aiEngineMeta.lastPhase31Run=new Date().toISOString();
  saveState();
}

/* Önceki Faz 3 fonksiyonlarını yeni motorla değiştir. */
analyzeSignal = analyzeSignal31;
if(typeof runAiAutomation==="function"){
  runAiAutomation = function(){
    reanalyzeAll31();
    DemoDB.audit("Yapay zekâ analizleri yeniden hesaplandı","TUSAS-YZ-31","Eski analiz","Faz 3.1 analiz modeli");
    saveState();
  };
}
runOpenTextAnalysis = function(){
  state.learningSignals.filter(function(s){return s.openText}).forEach(function(s){analyzeSignal31(s);applyAI31(s)});
  state.analysisRunAt=new Date().toLocaleString("tr-TR");
  state.analysisRunCount=(state.analysisRunCount||0)+1;
  DemoDB.audit("Açık uçlu yanıtlar yapay zekâ tarafından analiz edildi","YZ-ACIK-"+state.analysisRunCount,"Bekleyen","Tamamlandı");
  saveState();
};

/* capture/create fonksiyonlarını da doğrudan Faz 3.1 motoruna bağla. */
var _capture31 = captureLearningSignal;
captureLearningSignal = function(data){
  var rec=_capture31(data);
  analyzeSignal31(rec);applyAI31(rec);saveState();
  return rec;
};
var _create31 = createRequestRecord;
createRequestRecord = function(data){
  var req=_create31(data);
  var s=DemoDB.findById("learningSignals",req.signalId);
  if(s){
    analyzeSignal31(s);applyAI31(s);
    req.aiAnalysis=clone(s.aiAnalysis);
    if(s.linkedNeedIds.length)req.needId=s.linkedNeedIds[0];
    req.status=s.aiAnalysis.risk.level==="Kritik"?"Acil İnceleme":
      s.humanStatus==="ACCEPTED"?"Yapay Zekâ Tarafından Analiz Edildi":"Analist Doğrulaması Bekleniyor";
    saveState();
  }
  return req;
};

/* ---------------- 4) TALEP İLETME EKRANLARI ---------------- */

function submitterMiniStats(){
  var mine=state.requests.filter(function(r){
    return r.submittedBy==="Demo Kullanıcı" || r.submittedBy==="Demo Talep Sahibi";
  });
  return {
    total:mine.length,
    review:mine.filter(function(r){return /Doğrulama|İnceleme/.test(r.status)}).length,
    done:mine.filter(function(r){return /Analiz Edildi|ilişkilendirildi|Çözüldü/.test(r.status)}).length
  };
}
function renderSubmitterHome31(){
  var st=submitterMiniStats();
  $("#appView").innerHTML=
    '<div class="submitter-shell">'+
      '<section class="hero submitter-hero"><div>'+
        '<div class="eyebrow">Çalışan İşlem Merkezi</div>'+
        '<h1>İhtiyacınızı iletin, gerisini sistem analiz etsin.</h1>'+
        '<p class="focus-optional">Talebinizi yazın. Yapay zekâ kategori, risk, benzer kayıt ve mevcut eğitim kapsamını otomatik değerlendirsin.</p>'+
        '<div class="inline-actions" style="margin-top:14px"><button class="btn primary" data-page="submitter-request">Talep İlet</button><button class="btn" data-page="my-requests">Taleplerimi Gör</button></div>'+
      '</div>'+
      '<div class="card" style="box-shadow:none"><div class="metric-row" style="grid-template-columns:1fr">'+
        '<div class="mini-metric"><div class="n">'+st.total+'</div><div class="t">Toplam talebim</div></div>'+
        '<div class="mini-metric"><div class="n">'+st.review+'</div><div class="t">İnceleme bekliyor</div></div>'+
        '<div class="mini-metric"><div class="n">'+st.done+'</div><div class="t">Analizi tamamlandı</div></div>'+
      '</div></div></section>'+
      '<div class="submitter-actions">'+
        '<article class="card submitter-action"><h2>Talep İlet</h2><p>Yeni gelişim veya eğitim ihtiyacınızı gönderin.</p><button class="btn primary" data-page="submitter-request">Yeni Talep</button></article>'+
        '<article class="card submitter-action"><h2>Eğitim Ara</h2><p>Önce mevcut katalogda çözüm olup olmadığını kontrol edin.</p><button class="btn" data-page="find-training">Eğitim Ara</button></article>'+
        '<article class="card submitter-action"><h2>Taleplerim</h2><p>Gönderdiğiniz taleplerin analiz ve yönlendirme durumunu izleyin.</p><button class="btn" data-page="my-requests">Durumu Gör</button></article>'+
      '</div>'+
    '</div>';
}
function renderSubmitterRequest31(){
  $("#appView").innerHTML=
    pageHead("Talep İlet","",'<button class="btn" data-page="submitter-home">Vazgeç</button>')+
    '<section class="card" style="max-width:900px;margin:auto">'+
      '<form id="submitterRequestForm">'+
        '<div class="field"><label for="srText">İhtiyacınızı yazın *</label>'+
          '<textarea id="srText" name="description" required placeholder="Örn. Power BI ile ileri seviye yönetim gösterge paneli hazırlamak istiyorum."></textarea>'+
        '</div>'+
        '<div class="form-grid">'+
          '<div class="field"><label for="srPeriod">Aciliyet</label><select id="srPeriod" name="period">'+
            '<option>Bu dönem</option><option>Gelecek dönem</option><option>Mümkün olan en kısa zamanda</option><option>Acil değil / öneri</option>'+
          '</select></div>'+
          '<div class="field"><label for="srAffected">Etkilenen kapsam</label><select id="srAffected" name="affected">'+
            '<option>Sadece beni</option><option>Ekibimi</option><option>Bölümümü</option><option>Birden fazla birimi</option>'+
          '</select></div>'+
        '</div>'+
        '<div class="form-grid">'+
          '<div class="field"><label for="srCourse">İlgili mevcut eğitim</label><select id="srCourse" name="course"><option value="">Bilmiyorum / ilgili eğitim yok</option>'+
            state.courses.map(function(c){return '<option value="'+c.id+'">'+esc(c.title)+'</option>'}).join("")+
          '</select></div>'+
          '<div class="field"><label>Kritik içerik şüphesi</label><div class="radio-row">'+
            '<div class="radio-pill"><input id="srCriticalNo" type="radio" name="critical" value="no" checked><label for="srCriticalNo">Hayır</label></div>'+
            '<div class="radio-pill"><input id="srCriticalYes" type="radio" name="critical" value="yes"><label for="srCriticalYes">Evet</label></div>'+
          '</div></div>'+
        '</div>'+
        '<div class="form-actions"><button class="btn primary" type="submit">Gönder ve Yapay Zekâ ile Analiz Et</button></div>'+
      '</form>'+
    '</section>';
  bindSubmitterForm31();
}
function renderAIResultCard31(req,signal){
  var ai=signal.aiAnalysis,best=ai.courseMatches[0];
  return '<section class="card ai-result-compact" style="max-width:900px;margin:14px auto 0">'+
    '<div class="tags"><span class="badge b-green">Analiz Tamamlandı</span><span class="badge b-blue">Güven %'+ai.confidence+'</span>'+badge(ai.risk.level)+'</div>'+
    '<h2 style="margin-top:12px">Yapay Zekâ Sonucu</h2>'+
    '<div class="ai-result-grid">'+
      '<div class="ai-chip"><div class="k">Kategori</div><div class="v">'+esc(ai.category)+'</div></div>'+
      '<div class="ai-chip"><div class="k">Alt Konu</div><div class="v">'+esc(ai.subtopic)+'</div></div>'+
      '<div class="ai-chip"><div class="k">Aciliyet</div><div class="v">'+esc(ai.urgency)+'</div></div>'+
      '<div class="ai-chip"><div class="k">Etki</div><div class="v">'+esc(ai.impact)+'</div></div>'+
    '</div>'+
    '<div class="meta" style="margin-top:10px"><div class="k">Önerilen İşlem</div><div class="v">'+esc(ai.recommendation.label)+'</div></div>'+
    (best?'<div class="notice" style="margin-top:10px"><strong>En iyi mevcut eğitim:</strong> '+esc(courseName(best.courseId))+' · %'+best.score+' eşleşme · '+esc(best.coverage)+' kapsam</div>':'')+
    '<div class="inline-actions" style="margin-top:12px"><button class="btn primary" data-page="my-requests">Talebi Takip Et</button><button class="btn" data-page="submitter-request">Yeni Talep Gönder</button></div>'+
  '</section>';
}
function bindSubmitterForm31(){
  var form=$("#submitterRequestForm");if(!form)return;
  form.addEventListener("submit",function(e){
    e.preventDefault();
    var fd=new FormData(form),desc=String(fd.get("description")||"").trim();
    if(!desc){toast("Talebinizi yazın.");return}
    var title=desc.split(/[.!?]/)[0].slice(0,75)||"Yeni gelişim ihtiyacı";
    var req=createRequestRecord({
      title:title,
      description:desc,
      relatedCourseId:fd.get("course")||null,
      desiredPeriod:fd.get("period"),
      affected:fd.get("affected"),
      critical:fd.get("critical")==="yes"
    });
    req.submittedBy="Demo Talep Sahibi";
    req.personRole="Çalışan";
    saveState();
    var signal=DemoDB.findById("learningSignals",req.signalId);
    $("#appView").innerHTML=
      '<section class="card success-screen" style="max-width:900px;margin:auto"><div class="success-icon">✓</div><h1>Talep kaydedildi</h1><p class="focus-optional">Yapay zekâ ilk analizi tamamladı.</p><div style="font-size:20px;font-weight:850;margin:12px">'+req.id+'</div></section>'+
      renderAIResultCard31(req,signal);
    toast("Talep kaydedildi ve analiz edildi.");
  });
}

/* ---------------- 5) HIZLI YENİ İŞLEM ---------------- */

function openQuickAction31(){
  openModal(
    '<div class="modal-head"><div><h2>Yeni İşlem</h2><div class="subtle">Ne yapmak istiyorsunuz?</div></div><button class="close" data-action="close-modal">✕</button></div>'+
    '<div class="quick-grid">'+
      '<article class="card"><h3>Talep İlet</h3><p>Yeni eğitim veya gelişim ihtiyacı gönder.</p><button class="btn primary" data-quick-go="request">Talep İlet</button></article>'+
      '<article class="card"><h3>Eğitim Ara</h3><p>Mevcut katalogda çözüm ara.</p><button class="btn" data-quick-go="training">Eğitim Ara</button></article>'+
      '<article class="card"><h3>Kritik Bildirim</h3><p>Yanlış veya riskli içerik şüphesi bildir.</p><button class="btn danger" data-quick-go="critical">Kritik Bildir</button></article>'+
    '</div>'
  );
}

/* ---------------- 6) YZ MERKEZİNDE ÇEŞİTLİ SONUÇLARI GÖSTER ---------------- */

function aiStats31(){
  var a=state.learningSignals.map(function(s){return s.aiAnalysis||analyzeSignal31(s)});
  return {
    analyzed:a.length,
    auto:a.filter(function(x){return x.confidence>=AI31.autoThreshold&&x.risk.level!=="Kritik"}).length,
    review:a.filter(function(x){return x.confidence<AI31.autoThreshold&&x.risk.level!=="Kritik"}).length,
    critical:a.filter(function(x){return x.risk.level==="Kritik"}).length,
    revise:a.filter(function(x){return x.recommendation.code==="REVISE_EXISTING"}).length,
    create:a.filter(function(x){return x.recommendation.code==="CREATE_NEW"}).length
  };
}
if(typeof renderAiCenter==="function"){
  renderAiCenter=function(){
    var st=aiStats31(),rows=state.learningSignals.slice().reverse();
    $("#appView").innerHTML=
      pageHead("Yapay Zekâ Analiz Merkezi","",'<button class="btn primary" data-ai31-action="reanalyze">Analizleri Yenile</button>')+
      '<div class="grid kpis">'+
        kpi("Analiz Edilen",st.analyzed,"öğrenme sinyali")+
        kpi("Otomatik Tamamlanan",st.auto,"yüksek güven")+
        kpi("İnsan Doğrulaması",st.review,"kontrol gerekli")+
        kpi("Kritik",st.critical,"acil inceleme")+
        kpi("Kapsam Güncelleme",st.revise,"mevcut eğitim yetersiz")+
        kpi("Yeni Çözüm",st.create,"katalog eşleşmesi zayıf")+
      '</div>'+
      '<div class="table-wrap"><table style="min-width:1500px"><thead><tr>'+
        '<th>Sinyal</th><th>Ham Yanıt</th><th>Kategori</th><th>Alt Konu</th><th>Güven</th><th>Risk</th><th>Aciliyet</th><th>Benzer</th><th>En İyi Eğitim</th><th>Kapsam</th><th>Öneri</th>'+
      '</tr></thead><tbody>'+
      rows.map(function(s){
        var ai=s.aiAnalysis||analyzeSignal31(s),b=ai.courseMatches[0];
        return '<tr class="clickable" data-ai31-detail="'+s.id+'">'+
          '<td><strong>'+s.id+'</strong></td>'+
          '<td class="table-title">'+esc(s.rawText)+'</td>'+
          '<td>'+badge(ai.category)+'</td>'+
          '<td>'+esc(ai.subtopic)+'</td>'+
          '<td class="ai-confidence">%'+ai.confidence+'</td>'+
          '<td>'+badge(ai.risk.level)+'</td>'+
          '<td>'+badge(ai.urgency)+'</td>'+
          '<td>'+ai.similarCount+'</td>'+
          '<td>'+(b?esc(courseName(b.courseId)):"—")+'</td>'+
          '<td>'+(b?badge(b.coverage):"—")+'</td>'+
          '<td class="table-title">'+esc(ai.recommendation.label)+'</td>'+
        '</tr>';
      }).join("")+
      '</tbody></table></div>';
  };
}

/* ---------------- ROUTING ---------------- */

var _render31=render;
render=function(){
  if(state.currentPage==="submitter-home"){renderShell();renderSubmitterHome31();addTopActions31();return}
  if(state.currentPage==="submitter-request"){renderShell();renderSubmitterRequest31();addTopActions31();return}
  var r=_render31();
  addTopActions31();
  return r;
};

/* ---------------- EVENTLER ---------------- */

document.addEventListener("click",function(e){
  var ft=e.target.closest("[data-focus-toggle]");
  if(ft){toggleFocusMode();return}

  var qa=e.target.closest("[data-quick-action]");
  if(qa){openQuickAction31();return}

  var qg=e.target.closest("[data-quick-go]");
  if(qg){
    var go=qg.dataset.quickGo;closeModal();
    if(go==="request"){
      state.currentRole="submitter";state.currentPage="submitter-request";
    }else if(go==="training"){
      state.currentRole="submitter";state.currentPage="find-training";
    }else if(go==="critical"){
      state.currentRole="submitter";state.currentPage="submitter-request";
      state._phase31CriticalPrefill=true;
    }
    saveState();render();
    if(go==="critical"){
      setTimeout(function(){
        var yes=$("#srCriticalYes");if(yes)yes.checked=true;
        var tx=$("#srText");if(tx&&!tx.value)tx.placeholder="Örn. Teknik eğitimdeki prosedür yanlış veya riskli olabilir.";
      },0);
    }
    return;
  }

  var re=e.target.closest("[data-ai31-action='reanalyze']");
  if(re){
    re.disabled=true;re.innerHTML='<span class="spinner"></span>Analiz ediliyor…';
    setTimeout(function(){reanalyzeAll31();toast("Yapay zekâ analizleri yenilendi.");renderAiCenter();addTopActions31()},CONFIG.simulatedDelay||320);
    return;
  }

  var det=e.target.closest("[data-ai31-detail]");
  if(det && typeof openAiDetail==="function"){openAiDetail(det.dataset.ai31Detail);return}
});

/* ---------------- İLK ÇALIŞTIRMA ---------------- */

ensureFocusStyles();

/* Eski tekdüze sonuçları zorla yenile. */
var needsRefresh=!state.aiEngineMeta || !state.aiEngineMeta.phase31;
if(needsRefresh){
  state.learningSignals.forEach(function(s){delete s.aiAnalysis});
  reanalyzeAll31();
  DemoDB.audit("Faz 3.1 yapay zekâ modeli etkinleştirildi","TUSAS-YZ-31","Faz 3","Çeşitlendirilmiş analiz modeli");
  saveState();
}

render();
addTopActions31();

})();

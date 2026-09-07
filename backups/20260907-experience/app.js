/* ============================================================
   TUSAŞ — APPLICATION LOGIC / DEMO + LIVE REQUEST FLOW
   CONFIG / SEED / DATA STORE / DOMAIN / SELECTORS / ROUTING
   COMPONENTS / PAGE RENDERERS / MODALS / EVENTS / INIT
   ============================================================ */

/* ---------------- CONFIG ---------------- */
var CONFIG={
  storageKey:"learning-lifecycle-mvp-v2",
  version:4,
  coverage:{healthy:60,watch:40},
  displayLimit:100,
  simulatedDelay:320
};
var LIVE_AI={status:"checking",message:"Yapay zekâ bağlantısı kontrol ediliyor.",health:null};
// Live request content stays in memory, never in the demo localStorage.
var LIVE_REQUEST={text:"",result:null,busy:false,error:""};
var DOC_INDEX={report:null,error:"",syncing:false,promise:null,timer:null,offset:0};
var ORGS=[
 {id:"ORG-01",name:"Mühendislik",type:"business"},
 {id:"ORG-02",name:"Üretim",type:"business"},
 {id:"ORG-03",name:"Kalite",type:"business"},
 {id:"ORG-04",name:"Teknik Operasyonlar",type:"business"},
 {id:"ORG-05",name:"Ar-Ge",type:"business"},
 {id:"ORG-06",name:"Proje Yönetimi",type:"business"},
 {id:"ORG-07",name:"Bilgi Teknolojileri",type:"business"},
 {id:"ORG-08",name:"Kurumsal Hizmetler",type:"business"},
 {id:"ORG-09",name:"İnsan ve Organizasyon",type:"business"},
 {id:"ORG-10",name:"Destek Operasyonları",type:"business"},
 {id:"MU-NA",name:"İhtiyaç Analizi Birimi",type:"process"},
 {id:"TU-DESIGN",name:"Eğitim Tasarım Birimi",type:"process"},
 {id:"CENTRAL",name:"Learning Analytics / Yönetim",type:"process"}
];
var COURSES=[
 {id:"CRS-001",title:"Teknik Emniyet ve Güvenlik",topic:"Teknik Emniyet ve Güvenlik",level:"Temel",summary:"Temel saha güvenliği, olay bildirimi ve acil durum uygulamaları.",skills:["güvenlik","acil durum","prosedür"],audience:["Teknik Personel"],status:"Published",tags:["güvenlik","prosedür"]},
 {id:"CRS-002",title:"Excel ile Veri Analizi",topic:"Veri Analitiği ve Raporlama",level:"Orta",summary:"Pivot, veri temizleme ve düzenli raporlama için uygulamalı Excel.",skills:["pivot","excel","veri analizi"],audience:["Uzman","Mühendis"],status:"Published",tags:["excel","pivot","raporlama"]},
 {id:"CRS-003",title:"Power BI Temelleri",topic:"Veri Analitiği ve Raporlama",level:"Başlangıç",summary:"Veri içe aktarma, temel grafikler ve filtrelerle Power BI başlangıcı.",skills:["veri içe aktarma","temel grafikler","filtreler"],audience:["Tüm Çalışanlar"],status:"Published",tags:["power bi","grafik","filtre"]},
 {id:"CRS-004",title:"Proje Yönetimine Giriş",topic:"Proje Yönetimi",level:"Başlangıç",summary:"Planlama, risk ve paydaş koordinasyonunun temelleri.",skills:["planlama","risk","paydaş"],audience:["Proje Ekibi"],status:"Published",tags:["proje","risk","planlama"]},
 {id:"CRS-005",title:"Dijital Araçlar ve Sorumlu AI",topic:"Dijital Araçlar ve AI",level:"Temel",summary:"Üretken AI araçlarını güvenli, doğrulanabilir ve verimli kullanma.",skills:["ai okuryazarlığı","doğrulama","veri güvenliği"],audience:["Tüm Çalışanlar"],status:"Published",tags:["ai","dijital araçlar"]},
 {id:"CRS-006",title:"Teknik Operasyonlarda Standardizasyon",topic:"Teknik Operasyon",level:"Orta",summary:"Standart iş, ekipman kontrolü ve operasyonel kayıt uygulamaları.",skills:["standart iş","ekipman","operasyon"],audience:["Teknik Personel"],status:"Published",tags:["teknik","operasyon","ekipman"]},
 {id:"CRS-007",title:"Etkili Liderlik ve Geri Bildirim",topic:"Liderlik ve İletişim",level:"Orta",summary:"Ekip yönlendirme, geri bildirim ve zor görüşme pratikleri.",skills:["liderlik","geri bildirim","iletişim"],audience:["Yönetici","Takım Lideri"],status:"Published",tags:["liderlik","iletişim"]},
 {id:"CRS-008",title:"Kalite Araçlarıyla Problem Çözme",topic:"Kalite ve Süreç",level:"Orta",summary:"Kök neden analizi ve süreç iyileştirme araçları.",skills:["kök neden","kalite","süreç"],audience:["Kalite Uzmanı","Mühendis"],status:"Published",tags:["kalite","problem çözme"]}
];
var PERSONAS={
 executive:{label:"Yönetici Görünümü",name:"Yönetici Görünümü",personRole:"Learning Intelligence",org:"Toplulaştırılmış Kurumsal Görünüm"},
 analyst:{label:"İhtiyaç Analisti — Demo Analist",name:"Demo Analist",personRole:"İhtiyaç Analisti",org:"İhtiyaç Analizi Birimi"},
 requester:{label:"Çalışan — Demo Kullanıcı",name:"Demo Kullanıcı",personRole:"Çalışan",org:"Mühendislik"},
 designer:{label:"Eğitim Tasarım Birimi",name:"Demo Tasarım Uzmanı",personRole:"Eğitim Tasarım Uzmanı",org:"Eğitim Tasarım Birimi"},
 submitter:{label:"Talep İletme — Çalışan",name:"Demo Talep Sahibi",personRole:"Talep İletme",org:"Kurumsal Çalışan Görünümü"}
};
var SOURCE_META={
 "Annual Survey":{short:"Yıllık anket",color:"#263685",className:"b-blue"},
 "Manual Request":{short:"Çalışan talebi",color:"#4D4D4D",className:"b-gray"},
 "Course Feedback":{short:"Eğitim geri bildirimi",color:"#1E1A34",className:"b-purple"},
 "Instructor Feedback":{short:"Eğitmen geri bildirimi",color:"#D29F13",className:"b-amber"},
 "External Learning Platform":{short:"Dış öğrenme platformu",color:"#767682",className:"b-gray"},
 "Content / Critical":{short:"Kritik içerik",color:"#DD140E",className:"b-red"},
 "Other":{short:"Diğer",color:"#767682",className:"b-gray"}
};
var CLUSTERS=[
 "Veri Analitiği ve Raporlama","Teknik Emniyet ve Güvenlik","Proje Yönetimi",
 "Dijital Araçlar ve AI","Teknik Operasyon","Liderlik ve İletişim","Kalite ve Süreç"
];
var NEED_RECIPES=[
 {id:"NEED-0028",title:"Veri Analitiği ve Raporlama",summary:"Excel, Pivot, Power Query, Power BI, dashboard ve raporlama görevleri çevresinde farklı birimlerden tekrar eden öğrenme ihtiyacı.",impact:"High",urgency:"Medium",strategic:"Var",risk:"None",priority:"High",status:"DECIDED"},
 {id:"NEED-0031",title:"Dijital Araçlar ve AI",summary:"Dijital araçları ve üretken AI çözümlerini güvenli, doğrulanabilir ve verimli kullanma ihtiyacı.",impact:"High",urgency:"Medium",strategic:"Var",risk:"None",priority:"High",status:"ANALYSING"},
 {id:"NEED-0034",title:"Teknik Emniyet ve Güvenlik",summary:"Güvenlik içeriği, prosedür güncelliği ve uygulama tazeleme ihtiyacı.",impact:"Critical",urgency:"High",strategic:"Var",risk:"Critical",priority:"Critical",status:"IMMEDIATE_REVIEW"},
 {id:"NEED-0037",title:"Proje Yönetimi",summary:"Planlama, risk ve paydaş koordinasyonunda ortak çalışma yöntemi ihtiyacı.",impact:"High",urgency:"Medium",strategic:"Var",risk:"None",priority:"Medium",status:"DECIDED"},
 {id:"NEED-0040",title:"Liderlik ve İletişim",summary:"Takım yönlendirme, geri bildirim ve paydaş iletişimi pratikleri.",impact:"Medium",urgency:"Low",strategic:"Var",risk:"None",priority:"Medium",status:"ANALYSING"},
 {id:"NEED-0042",title:"Kalite ve Süreç",summary:"Kök neden, problem çözme ve süreç iyileştirme araçlarının ortak kullanımı.",impact:"High",urgency:"Medium",strategic:"Var",risk:"Elevated",priority:"High",status:"DECIDED"},
 {id:"NEED-0046",title:"Teknik Operasyon",summary:"Standart iş, ekipman kullanımı ve teknik kayıt becerileri.",impact:"High",urgency:"High",strategic:"Yok",risk:"Elevated",priority:"High",status:"READY_FOR_DECISION"},
 {id:"NEED-0051",title:"Çalışma Verimliliği",summary:"Günlük planlama, dijital iş akışı ve bilgi paylaşımı pratikleri.",impact:"Medium",urgency:"Low",strategic:"Yok",risk:"None",priority:"Low",status:"ANALYSING"}
];
var MAIN_TEXTS=[
 "Pivot tablo konusunda eğitim almak istiyorum.",
 "İleri Excel eğitimi faydalı olur.",
 "Power Query kullanmayı öğrenmem gerekiyor.",
 "Power BI dashboard hazırlamayı öğrenmek istiyorum.",
 "Raporlama tarafında daha ileri bir eğitim gerekiyor.",
 "Excel ile büyük veri tablolarını analiz etmekte zorlanıyoruz.",
 "Dashboard ve veri görselleştirme konusunda uygulamalı çalışma lazım.",
 "Pivot kullanımında ilerlemek istiyorum.",
 "Power Query öğrenmemiz gerekiyor.",
 "Mevcut Power BI eğitimi dashboard ihtiyacımızı karşılamadı.",
 "Düzenli rapor hazırlamakta zorlanıyoruz.",
 "Yönetim raporlarını daha anlaşılır görselleştirmek istiyoruz."
];
var OTHER_TEXTS={
 "NEED-0031":["Günlük işlerimde AI araçlarını daha güvenli kullanmak istiyorum.","Üretken yapay zekâ çıktılarının nasıl doğrulanacağını öğrenmeliyiz."],
 "NEED-0034":["Kimyasal dökülme prosedürü konusunda uygulamalı tazeleme gerekiyor.","Saha güvenliği örnekleri güncellenmeli."],
 "NEED-0037":["Proje risklerini ortak yöntemle takip etmek istiyoruz.","Paydaş planlamasında uygulamalı örneğe ihtiyacımız var."],
 "NEED-0040":["Zor görüşmelerde yapıcı geri bildirim vermeyi geliştirmek istiyorum.","Ekip içi iletişim için vaka çalışması faydalı olur."],
 "NEED-0042":["Kök neden analizini gerçek örneklerle çalışmak istiyoruz.","Süreç iyileştirme araçlarında ortak yaklaşım gerekli."],
 "NEED-0046":["Teknik ekipman kontrol kayıtlarını standartlaştırmalıyız.","Operasyon adımlarında uygulamalı tazeleme gerekiyor."],
 "NEED-0051":["Dijital iş akışlarında zaman kaybını azaltmak istiyoruz.","Bilgiyi ekip içinde daha düzenli paylaşmalıyız."]
};

/* ---------------- DETERMINISTIC SEED DATA ---------------- */
function clone(value){return JSON.parse(JSON.stringify(value))}
function isoDay(offset){
  var day=1+(offset%28);
  return "2026-08-"+String(day).padStart(2,"0");
}
function makeSignal(id,type,source,needId,text,index,extra){
  var org=ORGS[index%10];
  var role=["Mühendis","Teknik Personel","Uzman","Takım Lideri","İdari Personel"][index%5];
  var base={
    id:id,signalType:type,sourceType:source,summary:text,rawText:text,topicHint:null,
    suggestedCluster:null,suggestionConfidence:null,organizationId:org.id,personRole:role,
    relatedCourseId:null,anonymous:source==="Annual Survey",privacyMode:source==="Annual Survey"?"AGGREGATE":"ROLE_CONTEXT",
    riskLevel:"None",status:"CAPTURED",linkedNeedIds:needId?[needId]:[],suggestedNeedId:needId,
    requestId:null,resolution:null,openText:false,humanStatus:"NOT_APPLICABLE",
    createdAt:isoDay(index),updatedAt:isoDay(index)
  };
  if(extra)Object.keys(extra).forEach(function(k){base[k]=extra[k]});
  return base;
}
function buildInitialState(){
  var signals=[],requests=[],signalNo=1,requestNo=1;
  function sid(){var v="SIG-2026-"+String(signalNo).padStart(4,"0");signalNo++;return v}
  function rid(){var v="REQ-2026-"+String(requestNo).padStart(4,"0");requestNo++;return v}
  var mainNeed="NEED-0028";
  for(var i=0;i<42;i++){
    var mainText=MAIN_TEXTS[i%MAIN_TEXTS.length];
    var mainHuman=i<7?"REVIEW_REQUIRED":"ACCEPTED";
    signals.push(makeSignal(sid(),"SURVEY_RESPONSE","Annual Survey",mainNeed,mainText,i,{
      openText:true,humanStatus:mainHuman,status:mainHuman==="ACCEPTED"?"CLASSIFIED":"HUMAN_REVIEW",
      suggestedCluster:"Veri Analitiği ve Raporlama",suggestionConfidence:87+(i%8),
      topicHint:mainHuman==="ACCEPTED"?"Veri Analitiği ve Raporlama":null,organizationId:ORGS[i%4].id
    }));
  }
  for(var j=0;j<14;j++){
    var requestText=MAIN_TEXTS[(j+2)%MAIN_TEXTS.length];
    var requestId=rid();
    var signalId=sid();
    var submitted=j<3?"Demo Kullanıcı":"Demo Kullanıcı "+String(j+11).padStart(2,"0");
    var request={
      id:requestId,signalId:signalId,title:"Veri analitiği gelişim ihtiyacı",description:requestText,
      submittedBy:submitted,personRole:["Mühendis","Uzman","Teknik Personel"][j%3],
      organizationId:ORGS[j%4].id,source:"Manual Request",relatedCourseId:j%3===0?"CRS-003":null,
      issueFlag:false,riskLevel:"None",desiredPeriod:["Bu dönem","Gelecek dönem","Acil değil / öneri"][j%3],
      affected:["Sadece beni","Ekibimi","Bölümümü"][j%3],status:"Need ile ilişkilendirildi",
      needId:mainNeed,createdAt:isoDay(j+5),updatedAt:isoDay(j+5)
    };
    requests.push(request);
    signals.push(makeSignal(signalId,"REQUEST","Manual Request",mainNeed,requestText,j+42,{
      requestId:requestId,anonymous:false,privacyMode:"ROLE_CONTEXT",status:"LINKED",topicHint:"Veri Analitiği ve Raporlama",organizationId:ORGS[j%4].id
    }));
  }
  for(var k=0;k<8;k++){
    var feedback=k===0?"Temel içerik faydalıydı ancak ileri dashboard ihtiyacını karşılamadı.":"Mevcut Power BI eğitimi başlangıç düzeyinde kaldı; ileri raporlama örnekleri gerekli.";
    signals.push(makeSignal(sid(),"COURSE_FEEDBACK","Course Feedback",mainNeed,feedback,k+58,{relatedCourseId:"CRS-003",status:"LINKED",topicHint:"Veri Analitiği ve Raporlama",organizationId:ORGS[k%4].id}));
  }
  for(var m=0;m<6;m++){
    signals.push(makeSignal(sid(),"EXTERNAL_LEARNING","External Learning Platform",mainNeed,"Sentetik dış öğrenme verisinde dashboard ve raporlama içeriğine tekrar eden ilgi görüldü.",m+70,{status:"LINKED",topicHint:"Veri Analitiği ve Raporlama",privacyMode:"AGGREGATE",organizationId:ORGS[m%4].id}));
  }
  var distribution=[
    {type:"SURVEY_RESPONSE",source:"Annual Survey",count:72},
    {type:"REQUEST",source:"Manual Request",count:32},
    {type:"COURSE_FEEDBACK",source:"Course Feedback",count:24},
    {type:"INSTRUCTOR_FEEDBACK",source:"Instructor Feedback",count:16},
    {type:"EXTERNAL_LEARNING",source:"External Learning Platform",count:12},
    {type:"CONTENT_ISSUE",source:"Content / Critical",count:4}
  ];
  var surveyOpenIndex=0;
  distribution.forEach(function(group){
    for(var q=0;q<group.count;q++){
      var need=NEED_RECIPES[1+(q%7)];
      var texts=OTHER_TEXTS[need.id];
      var txt=texts[q%texts.length];
      var extra={status:"LINKED",topicHint:need.title};
      if(group.type==="SURVEY_RESPONSE"&&surveyOpenIndex<32){
        extra.openText=true;
        if(surveyOpenIndex<26){extra.humanStatus="ACCEPTED";extra.status="CLASSIFIED";extra.suggestedCluster=need.title;extra.suggestionConfidence=82+(q%12)}
        else if(surveyOpenIndex<28){extra.humanStatus="REVIEW_REQUIRED";extra.status="HUMAN_REVIEW";extra.suggestedCluster=need.title;extra.suggestionConfidence=76+(q%8);extra.topicHint=null}
        else{extra.humanStatus="UNCLASSIFIED";extra.status="UNCLASSIFIED";extra.suggestedCluster=null;extra.suggestionConfidence=null;extra.topicHint=null}
        surveyOpenIndex++;
      }
      if(group.type==="REQUEST"){
        var rId=rid(),sId=sid();
        var req={
          id:rId,signalId:sId,title:need.title+" gelişim ihtiyacı",description:txt,
          submittedBy:"Demo Kullanıcı "+String(requestNo+20).padStart(2,"0"),personRole:"Uzman",
          organizationId:ORGS[q%10].id,source:"Manual Request",relatedCourseId:null,issueFlag:false,
          riskLevel:"None",desiredPeriod:"Bu dönem",affected:"Ekibimi",status:"Need ile ilişkilendirildi",
          needId:need.id,createdAt:isoDay(q+10),updatedAt:isoDay(q+10)
        };
        requests.push(req);
        extra.requestId=rId;
        signals.push(makeSignal(sId,group.type,group.source,need.id,txt,signals.length,extra));
      }else{
        if(group.type==="CONTENT_ISSUE"&&q===0){
          txt="Teknik Emniyet ve Güvenlik eğitiminde kimyasal dökülme prosedürü yanlış olabilir.";
          need=NEED_RECIPES[2];
          extra.riskLevel="Critical";extra.status="IMMEDIATE_REVIEW";extra.relatedCourseId="CRS-001";
          extra.topicHint=need.title;
        }else if(group.type==="CONTENT_ISSUE"){
          extra.riskLevel="Elevated";extra.status="REVIEW";extra.relatedCourseId="CRS-006";
        }
        signals.push(makeSignal(sid(),group.type,group.source,need.id,txt,signals.length,extra));
      }
    }
  });
  var criticalSignal=signals.filter(function(s){return s.riskLevel==="Critical"})[0];
  var criticalRequest={
    id:"REQ-2026-0093",signalId:criticalSignal.id,title:"Kimyasal dökülme prosedürü için kritik inceleme",
    description:criticalSignal.rawText,submittedBy:"Demo Kullanıcı",personRole:"Teknik Personel",
    organizationId:"ORG-04",source:"Manual Request",relatedCourseId:"CRS-001",issueFlag:true,riskLevel:"Critical",
    desiredPeriod:"Mümkün olan en kısa zamanda",affected:"Birden fazla birimi",status:"Acil İnceleme",
    needId:"NEED-0034",createdAt:"2026-08-23",updatedAt:"2026-08-23"
  };
  criticalSignal.requestId=criticalRequest.id;
  requests.push(criticalRequest);
  var needs=NEED_RECIPES.map(function(recipe){
    var ids=signals.filter(function(s){return s.linkedNeedIds.indexOf(recipe.id)>-1}).map(function(s){return s.id});
    return {
      id:recipe.id,title:recipe.title,summary:recipe.summary,ownerUnit:"MU-NA",signalIds:ids,
      impact:recipe.impact,urgency:recipe.urgency,strategic:recipe.strategic,contentRisk:recipe.risk,
      suggestedPriority:recipe.priority,humanPriority:recipe.priority,status:recipe.status,
      decisionId:recipe.id==="NEED-0028"?"DCS-2026-0008":recipe.id==="NEED-0037"?"DCS-2026-0006":recipe.id==="NEED-0042"?"DCS-2026-0005":null,
      handoffId:recipe.id==="NEED-0028"?"HND-2026-0008":recipe.id==="NEED-0037"?"HND-2026-0006":null,createdAt:"2026-07-01",updatedAt:"2026-08-27"
    };
  });
  var decisions=[
    {id:"DCS-2026-0008",needId:"NEED-0028",type:"REVISE_EXISTING",relatedCourseId:"CRS-003",decisionMaker:"Demo Analist",decisionDate:"2026-08-27",rationale:"Mevcut eğitim başlangıç seviyesinde kalıyor. Farklı kaynaklardan gelen sinyaller dashboard tasarımı ve ileri raporlama seviyesinde yoğunlaşıyor.",evidenceSummary:"4 kaynak türü ve 4 organizasyondan tekrar eden sentetik kanıt.",createdAt:"2026-08-27",updatedAt:"2026-08-27"},
    {id:"DCS-2026-0006",needId:"NEED-0037",type:"CREATE_NEW",relatedCourseId:null,decisionMaker:"Demo Analist",decisionDate:"2026-08-22",rationale:"Mevcut katalog proje risk yönetimi ve paydaş koordinasyonu ihtiyacını yeterli uygulama derinliğinde karşılamıyor.",evidenceSummary:"Proje planlama ve risk sinyallerinden sentetik kanıt özeti.",createdAt:"2026-08-22",updatedAt:"2026-08-22"},
    {id:"DCS-2026-0005",needId:"NEED-0042",type:"USE_EXISTING",relatedCourseId:"CRS-008",decisionMaker:"Demo Analist",decisionDate:"2026-08-24",rationale:"Mevcut problem çözme eğitimi ihtiyaç kapsamıyla yeterli düzeyde eşleşiyor.",evidenceSummary:"Farklı birimlerden tekrar eden kalite sinyalleri.",createdAt:"2026-08-24",updatedAt:"2026-08-24"}
  ];
  var handoffs=[
    {id:"HND-2026-0008",sourceNeedId:"NEED-0028",decisionId:"DCS-2026-0008",solutionType:"REVISE_EXISTING",relatedCourseId:"CRS-003",proposedTitle:"İleri Veri Görselleştirme ve Dashboard",targetAudience:["Mühendis","Teknik Personel","Uzman"],evidenceSummary:"42 survey sinyali, 14 manuel talep, 8 eğitim geri bildirimi ve 6 dış öğrenme sinyali.",needSummary:NEED_RECIPES[0].summary,expectedOutcome:"İleri dashboard tasarımı, veri hikâyeleştirme ve yönetim raporlaması alanının tasarım birimi tarafından ele alınması.",status:"READY_FOR_DESIGN",createdAt:"2026-08-27",receivedAt:null},
    {id:"HND-2026-0006",sourceNeedId:"NEED-0037",decisionId:"DCS-2026-0006",solutionType:"CREATE_NEW",relatedCourseId:null,proposedTitle:"Uygulamalı Proje Risk Yönetimi",targetAudience:["Proje Ekibi","Takım Lideri"],evidenceSummary:"Proje planlama ve risk sinyallerinden yapılandırılmış sentetik özet.",needSummary:NEED_RECIPES[3].summary,expectedOutcome:"Uygulamalı proje senaryolarının eğitim tasarım ekibi tarafından değerlendirilmesi.",status:"RECEIVED_BY_DESIGN",createdAt:"2026-08-22",receivedAt:"2026-08-25"}
  ];
  var surveyCampaigns=[{
    id:"SRV-2026-01",title:"2026 Yıllık Eğitim İhtiyaç Analizi",period:"2026",status:"Analysis Open",
    units:[
      {organizationId:"ORG-01",target:180,responses:124,openResponses:83,reminderStatus:"Not Required"},
      {organizationId:"ORG-04",target:120,responses:27,openResponses:19,reminderStatus:"Not Planned"},
      {organizationId:"ORG-03",target:80,responses:52,openResponses:37,reminderStatus:"Not Required"},
      {organizationId:"ORG-02",target:160,responses:68,openResponses:48,reminderStatus:"Not Planned"}
    ]
  }];
  return {
    version:CONFIG.version,currentRole:"executive",currentPage:"executive-overview",
    selectedNeedId:"NEED-0028",selectedSignalId:null,selectedHandoffId:"HND-2026-0008",selectedRequestId:null,
    needSignalFilter:"All",learningSignals:signals,requests:requests,needs:needs,courses:clone(COURSES),
    decisions:decisions,handoffs:handoffs,surveyCampaigns:surveyCampaigns,
    analysisRunAt:null,analysisRunCount:0,requestDraft:"",
    audit:[
      {id:"AUD-0003",timestamp:"2026-08-27 14:20",actor:"Demo Analist",entity:"NEED-0028",action:"Human decision recorded",before:"READY_FOR_DECISION",after:"REVISE_EXISTING"},
      {id:"AUD-0002",timestamp:"2026-08-27 14:21",actor:"Demo Analist",entity:"HND-2026-0008",action:"Training design handoff created",before:"—",after:"READY_FOR_DESIGN"},
      {id:"AUD-0001",timestamp:"2026-08-23 10:15",actor:"Demo Analist",entity:"REQ-2026-0093",action:"Critical review opened",before:"CAPTURED",after:"IMMEDIATE_REVIEW"}
    ]
  };
}

/* ---------------- DATA STORE ---------------- */
var state;
function loadState(){
  try{
    var saved=JSON.parse(localStorage.getItem(CONFIG.storageKey));
    if(saved&&saved.version===CONFIG.version)return saved;
  }catch(error){}
  return buildInitialState();
}
function saveState(){localStorage.setItem(CONFIG.storageKey,JSON.stringify(state))}
var DemoDB={
  select:function(collection,predicate){var rows=state[collection]||[];return predicate?rows.filter(predicate):rows.slice()},
  findById:function(collection,id){return (state[collection]||[]).find(function(row){return row.id===id})||null},
  insert:function(collection,record){state[collection].push(record);saveState();return record},
  update:function(collection,id,changes){
    var row=this.findById(collection,id);if(!row)return null;
    Object.keys(changes).forEach(function(key){row[key]=changes[key]});
    row.updatedAt=new Date().toISOString();saveState();return row
  },
  link:function(signalId,needId){
    var signal=this.findById("learningSignals",signalId),need=this.findById("needs",needId);
    if(!signal||!need)return false;
    if(signal.linkedNeedIds.indexOf(needId)===-1)signal.linkedNeedIds.push(needId);
    if(need.signalIds.indexOf(signalId)===-1)need.signalIds.push(signalId);
    signal.status="LINKED";signal.updatedAt=new Date().toISOString();need.updatedAt=new Date().toISOString();
    this.audit("Signal linked to Need",signalId,"Unlinked",needId);saveState();return true
  },
  aggregate:function(collection,key){
    return this.select(collection).reduce(function(acc,row){var value=row[key]||"Unknown";acc[value]=(acc[value]||0)+1;return acc},{})
  },
  audit:function(action,entity,before,after){
    var id="AUD-"+String((state.audit.length||0)+1).padStart(4,"0");
    state.audit.unshift({id:id,timestamp:new Date().toLocaleString("tr-TR"),actor:PERSONAS[state.currentRole].name,entity:entity,action:action,before:before||"—",after:after||"—"});
    state.audit=state.audit.slice(0,100);saveState()
  }
};

/* ---------------- DOMAIN FUNCTIONS ---------------- */
function nextId(prefix,collection){
  var nums=collection.map(function(row){var match=String(row.id).match(/(\d+)$/);return match?Number(match[1]):0});
  return prefix+String(Math.max.apply(null,[0].concat(nums))+1).padStart(4,"0")
}
function orgName(id){var row=ORGS.find(function(o){return o.id===id});return row?row.name:"—"}
function courseName(id){var row=state.courses.find(function(c){return c.id===id});return row?row.title:"—"}
function captureLearningSignal(data){
  var id=nextId("SIG-2026-",state.learningSignals);
  var record=makeSignal(id,data.signalType,data.sourceType,data.needId||null,data.rawText||data.summary,state.learningSignals.length,{
    summary:data.summary||data.rawText,organizationId:data.organizationId||"ORG-01",personRole:data.personRole||"Çalışan",
    relatedCourseId:data.relatedCourseId||null,anonymous:!!data.anonymous,privacyMode:data.anonymous?"AGGREGATE":"ROLE_CONTEXT",
    riskLevel:data.riskLevel||"None",status:data.status||"CAPTURED",resolution:data.resolution||null,
    requestId:data.requestId||null,openText:!!data.openText,humanStatus:data.openText?"REVIEW_REQUIRED":"NOT_APPLICABLE"
  });
  DemoDB.insert("learningSignals",record);
  if(data.needId){var need=DemoDB.findById("needs",data.needId);if(need&&need.signalIds.indexOf(id)===-1)need.signalIds.push(id)}
  DemoDB.audit("Learning signal captured",id,"—",record.sourceType);saveState();return record
}
function createRequestRecord(data){
  var requestId=nextId("REQ-2026-",state.requests);
  var signal=captureLearningSignal({
    signalType:data.critical?"CONTENT_ISSUE":"REQUEST",sourceType:data.critical?"Content / Critical":"Manual Request",
    rawText:data.description,summary:data.title,organizationId:"ORG-01",personRole:"Çalışan",
    relatedCourseId:data.relatedCourseId||null,riskLevel:data.critical?"Critical":"None",
    status:data.critical?"IMMEDIATE_REVIEW":"CAPTURED",anonymous:false
  });
  var request={
    id:requestId,signalId:signal.id,title:data.title,description:data.description,submittedBy:"Demo Kullanıcı",
    personRole:"Çalışan",organizationId:"ORG-01",source:"Manual Request",relatedCourseId:data.relatedCourseId||null,
    issueFlag:data.critical,riskLevel:data.critical?"Critical":"None",desiredPeriod:data.desiredPeriod,
    affected:data.affected,status:data.critical?"Acil İnceleme":"Alındı",needId:null,
    createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()
  };
  signal.requestId=requestId;DemoDB.insert("requests",request);DemoDB.audit("Request created with linked signal",requestId,"—",signal.id);saveState();return request
}
function suggestCluster(text){
  var value=String(text||"").toLocaleLowerCase("tr-TR");
  var rules=[
    {name:"Veri Analitiği ve Raporlama",terms:["pivot","excel","power query","power bi","dashboard","rapor","görselleştirme","büyük veri"]},
    {name:"Teknik Emniyet ve Güvenlik",terms:["güvenlik","emniyet","kimyasal","dökülme","acil durum","prosedür"]},
    {name:"Proje Yönetimi",terms:["proje","risk","paydaş","planlama"]},
    {name:"Dijital Araçlar ve AI",terms:["yapay zek"," ai ","üretken","dijital araç","prompt"]},
    {name:"Teknik Operasyon",terms:["ekipman","operasyon","standart iş","teknik kayıt"]},
    {name:"Liderlik ve İletişim",terms:["lider","geri bildirim","iletişim","zor görüşme"]},
    {name:"Kalite ve Süreç",terms:["kalite","kök neden","problem çöz","süreç iyileştirme"]}
  ];
  var best=null,score=0;
  rules.forEach(function(rule){
    var count=rule.terms.reduce(function(total,term){return total+(value.indexOf(term)>-1?1:0)},0);
    if(count>score){score=count;best=rule.name}
  });
  return best?{cluster:best,confidence:Math.min(96,76+score*7)}:{cluster:null,confidence:null}
}
function findNeedByTitle(title){return state.needs.find(function(n){return n.title===title})||null}
function runOpenTextAnalysis(){
  state.learningSignals.filter(function(s){return s.openText}).forEach(function(signal){
    var suggestion=suggestCluster(signal.rawText);
    signal.suggestedCluster=suggestion.cluster;signal.suggestionConfidence=suggestion.confidence;
    if(signal.humanStatus!=="ACCEPTED")signal.status=suggestion.cluster?"HUMAN_REVIEW":"UNCLASSIFIED"
  });
  state.analysisRunAt=new Date().toLocaleString("tr-TR");state.analysisRunCount++;
  DemoDB.audit("Open text analysis executed","OPEN-TEXT-RUN-"+state.analysisRunCount,"—",state.analysisRunAt);saveState()
}
function acceptClusterSuggestion(signalId,override){
  var signal=DemoDB.findById("learningSignals",signalId);if(!signal)return;
  var before=signal.topicHint||"Unclassified";
  var cluster=override||signal.suggestedCluster;
  if(!cluster)return;
  signal.topicHint=cluster;signal.suggestedCluster=cluster;signal.humanStatus="ACCEPTED";signal.status="CLASSIFIED";
  var need=findNeedByTitle(cluster);if(need)signal.suggestedNeedId=need.id;
  DemoDB.audit(override?"Cluster suggestion changed":"Cluster suggestion accepted",signalId,before,cluster);saveState()
}
function leaveUnclassified(signalId){
  var signal=DemoDB.findById("learningSignals",signalId);if(!signal)return;
  signal.topicHint=null;signal.humanStatus="UNCLASSIFIED";signal.status="UNCLASSIFIED";
  DemoDB.audit("Cluster suggestion left unclassified",signalId,signal.suggestedCluster||"—","UNCLASSIFIED");saveState()
}
function scheduleSurveyReminder(orgId){
  var campaign=state.surveyCampaigns[0],unit=campaign.units.find(function(row){return row.organizationId===orgId});
  if(!unit)return;var before=unit.reminderStatus;unit.reminderStatus="Planned";
  DemoDB.audit("Survey reminder planned",campaign.id+" / "+orgId,before,"Planned");saveState()
}
function signalSourceMix(need){
  var mix={};need.signalIds.forEach(function(id){var s=DemoDB.findById("learningSignals",id);if(s)mix[s.sourceType]=(mix[s.sourceType]||0)+1});return mix
}
function needEvidence(need){
  var signals=need.signalIds.map(function(id){return DemoDB.findById("learningSignals",id)}).filter(Boolean);
  var orgs=new Set(signals.map(function(s){return s.organizationId}));
  var roles=new Set(signals.map(function(s){return s.personRole}));
  var sources=new Set(signals.map(function(s){return s.sourceType}));
  return {signals:signals,orgCount:orgs.size,roleCount:roles.size,sourceCount:sources.size,mix:signalSourceMix(need)}
}
function coverageStatus(unit){
  var pct=Math.round(unit.responses/unit.target*100);
  if(pct>=CONFIG.coverage.healthy)return "Healthy";
  if(pct>=CONFIG.coverage.watch)return "Watch";
  return "Low Coverage"
}
function matchExistingCourses(need){
  if(need.id==="NEED-0028")return [
    {courseId:"CRS-003",match:58,coverage:"Partial",reason:"Temel grafik ve filtreleri kapsıyor; ileri dashboard, DAX ve yönetim raporlaması kapsam dışı."},
    {courseId:"CRS-002",match:44,coverage:"Partial",reason:"Pivot ve Excel analizi sağlıyor; Power BI dashboard hedefini tam karşılamıyor."}
  ];
  var title=need.title.toLocaleLowerCase("tr-TR");
  return state.courses.map(function(course){
    var hit=course.topic.toLocaleLowerCase("tr-TR")===title?1:course.tags.some(function(tag){return title.indexOf(tag)>-1})?0.7:0;
    return {courseId:course.id,match:Math.round(35+hit*50),coverage:hit===1?"Strong":hit?"Partial":"Low",reason:hit===1?"Konu ve hedef kitleyle güçlü eşleşme.":"İnsan incelemesi gerektiren sınırlı eşleşme."}
  }).sort(function(a,b){return b.match-a.match}).slice(0,2)
}
function recordHumanDecision(data){
  var need=DemoDB.findById("needs",data.needId);if(!need||!String(data.rationale||"").trim())return null;
  var decision=need.decisionId?DemoDB.findById("decisions",need.decisionId):null;
  var previous=decision?decision.type:"—";
  if(!decision){
    decision={id:nextId("DCS-2026-",state.decisions),needId:need.id,createdAt:new Date().toISOString()};
    state.decisions.push(decision);need.decisionId=decision.id
  }
  Object.assign(decision,{
    type:data.type,relatedCourseId:data.relatedCourseId||null,decisionMaker:"Demo Analist",
    decisionDate:new Date().toISOString().slice(0,10),rationale:data.rationale,
    evidenceSummary:evidenceSummaryText(need),updatedAt:new Date().toISOString()
  });
  need.status=data.type==="DEFER"?"ANALYSING":data.type==="REJECT"?"CLOSED":"DECIDED";
  if(data.type==="REVISE_EXISTING"||data.type==="CREATE_NEW")createTrainingHandoff(need,decision);
  else if(need.handoffId){
    var oldHandoff=DemoDB.findById("handoffs",need.handoffId);
    if(oldHandoff){
      state.handoffs=state.handoffs.filter(function(row){return row.id!==oldHandoff.id});
      DemoDB.audit("Training design handoff withdrawn",oldHandoff.id,oldHandoff.status,data.type)
    }
    need.handoffId=null
  }
  DemoDB.audit("Human decision recorded",decision.id,previous,data.type);saveState();return decision
}
function createTrainingHandoff(need,decision){
  var handoff=need.handoffId?DemoDB.findById("handoffs",need.handoffId):null;
  if(!handoff){
    handoff={id:nextId("HND-2026-",state.handoffs),sourceNeedId:need.id,decisionId:decision.id,status:"READY_FOR_DESIGN",createdAt:new Date().toISOString(),receivedAt:null};
    state.handoffs.push(handoff);need.handoffId=handoff.id
  }
  var mix=signalSourceMix(need);
  Object.assign(handoff,{
    solutionType:decision.type,relatedCourseId:decision.relatedCourseId||null,
    proposedTitle:decision.type==="REVISE_EXISTING"?(courseName(decision.relatedCourseId)+" — Kapsam Revizyonu"):(need.title+" Öğrenme Çözümü"),
    targetAudience:Array.from(new Set(needEvidence(need).signals.map(function(s){return s.personRole}))).slice(0,3),
    evidenceSummary:mixText(mix),needSummary:need.summary,
    expectedOutcome:"İhtiyaç ve kanıt bağlamının eğitim tasarım birimi tarafından doğrulanıp tasarım kapsamına dönüştürülmesi.",
    status:handoff.status||"READY_FOR_DESIGN"
  });
  DemoDB.audit("Training design handoff created",handoff.id,"—",handoff.status);saveState();return handoff
}
function receiveHandoff(handoffId){
  var handoff=DemoDB.findById("handoffs",handoffId);if(!handoff)return;
  var before=handoff.status;handoff.status="RECEIVED_BY_DESIGN";handoff.receivedAt=new Date().toISOString().slice(0,10);
  DemoDB.audit("Handoff received by design",handoffId,before,handoff.status);saveState()
}
function evidenceSummaryText(need){
  var ev=needEvidence(need);return "Bu ihtiyaç "+ev.orgCount+" organizasyon ve "+ev.sourceCount+" farklı veri kaynağından tekrar eden sentetik sinyallerle destekleniyor."
}
function mixText(mix){
  return Object.keys(mix).map(function(source){return mix[source]+" "+(SOURCE_META[source]?SOURCE_META[source].short:source)}).join(" · ")
}
function resolveWithExistingCourse(text,courseId,outcome){
  var needId=outcome==="COVERAGE_PROBLEM"&&/power bi|dashboard|excel|rapor/i.test(text)?"NEED-0028":null;
  var signal=captureLearningSignal({
    signalType:"DISCOVERY",sourceType:"Other",rawText:text,summary:"Akıllı eğitim bulma etkileşimi",
    organizationId:"ORG-01",personRole:"Çalışan",relatedCourseId:courseId,needId:needId,
    resolution:outcome,status:outcome==="RESOLVED_EXISTING_SOLUTION"?"RESOLVED":"CAPTURED"
  });
  if(needId)DemoDB.link(signal.id,needId);
  DemoDB.audit("Existing solution outcome recorded",signal.id,"Course match",outcome);saveState();return signal
}

/* ---------------- SELECTORS / FORMATTERS ---------------- */
function $(selector){return document.querySelector(selector)}
function originalText(value){return '<span data-no-translate>'+esc(value)+'</span>'}
function esc(value){return String(value==null?"":value).replace(/[&<>"']/g,function(char){return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#039;"}[char]})}
function fmtDate(value){
  if(!value)return "—";
  try{return new Intl.DateTimeFormat("tr-TR",{day:"2-digit",month:"short",year:"numeric"}).format(new Date(String(value).slice(0,10)+"T12:00:00"))}catch(error){return value}
}
function currentPersona(){return PERSONAS[state.currentRole]||PERSONAS.executive}
function sourceBadge(source){var meta=SOURCE_META[source]||SOURCE_META.Other;return '<span class="badge '+meta.className+'">'+esc(meta.short)+'</span>'}
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
    notice.innerHTML="<strong>"+esc(LIVE_AI.status==="connected"?"Bağlantı kontrolü başarılı.":LIVE_AI.status==="checking"?"Bağlantı kontrol ediliyor.":"Analiz şu anda kullanılamıyor.")+"</strong> "+esc(LIVE_AI.message)+
      (LIVE_AI.status!=="checking"&&LIVE_AI.status!=="connected"?' <button type="button" class="link-btn" data-action="retry-ai">Durumu yeniden kontrol et</button>':'');
  }
  // The same failure belongs in one alert, not both the service and form areas.
  var formError=$("#submitterFormError");
  if(formError)formError.innerHTML=LIVE_REQUEST.error&&!(notice&&LIVE_AI.status!=="connected"&&LIVE_AI.status!=="checking"&&LIVE_REQUEST.error===LIVE_AI.message)?'<div class="notice warning">'+esc(LIVE_REQUEST.error)+'</div>':'';
  if(button)button.disabled=LIVE_AI.status!=="connected"||LIVE_REQUEST.busy;
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
function sourceComposition(need){
  var mix=signalSourceMix(need),total=need.signalIds.length;
  return '<div class="source-stack" aria-label="Kaynak kompozisyonu">'+Object.keys(mix).map(function(source){
    return '<span title="'+esc((SOURCE_META[source]||SOURCE_META.Other).short)+': '+mix[source]+'" style="width:'+pct(mix[source],total)+'%;background:'+(SOURCE_META[source]||SOURCE_META.Other).color+'"></span>'
  }).join("")+'</div>'
}
function listNav(){
  var maps={
    executive:[["executive-overview","OV","Genel Bakış"],["guided-demo","GD","Platform Rehberi"],["needs","ND","Öğrenme İhtiyaçları"],["survey","SV","Anket Katılımı"],["roadmap","RM","Yol Haritası"]],
    analyst:[["analyst-dashboard","DB","Analiz Merkezi"],["signals","SG","Öğrenme Sinyalleri"],["open-analysis","AI","Açık Uçlu Analiz"],["survey","SV","Anket Katılımı"],["needs","ND","Öğrenme İhtiyaçları"],["critical","CR","Kritik İnceleme"],["decisions","DC","Kararlar"],["audit","AU","İşlem Geçmişi"]],
    requester:[["requester-home","HM","Ana Sayfa"],["find-training","FT","Akıllı Eğitim Bul"],["new-request","NS","Yeni Gelişim Sinyali"],["my-requests","MR","Taleplerim"],["catalog","CT","Eğitim Kataloğu"]],
    designer:[["handoffs","HQ","Tasarım Aktarımları"],["needs","NE","İhtiyaç Kanıtları"]],
    submitter:[["submitter-home","HM","Ana Sayfa"],["submitter-request","TL","Talep İlet"]]
  };
  return maps[state.currentRole]||maps.executive
}
function defaultPage(role){
  return {executive:"executive-overview",analyst:"analyst-dashboard",requester:"requester-home",designer:"handoffs",submitter:"submitter-home"}[role]||"executive-overview"
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
function renderShell(){
  if(typeof portalMode==='function'&&portalMode())return renderPortalShell();
  document.body.classList.remove('portal-employee','portal-admin','portal-detail');
  var persona=currentPersona();
  var activePage=state.currentPage==='need-detail'?'needs':state.currentPage==='handoff-detail'?'handoffs':state.currentPage;
  $("#roleSelect").innerHTML=Object.keys(PERSONAS).map(function(key){return '<option value="'+key+'" '+(state.currentRole===key?"selected":"")+'>'+esc(PERSONAS[key].label)+'</option>'}).join("");
  $("#roleContext").textContent=persona.personRole==="Learning Intelligence"?"Yönetim ve karar destek":persona.personRole+" · "+persona.org;
  $("#environmentContext").textContent=state.currentRole==="submitter"?"Canlı analiz servisi · Yalnızca sentetik veya paylaşımı onaylı bilgi kullanın.":"Bu görünümdeki kayıtlar sentetik gösterim verisidir. Canlı analiz, Talep İletme rolündedir.";
  $("#sidebar").innerHTML='<div class="brand" data-no-translate><div class="brand-lockup"><img class="brand-logo" src="/static/assets/brand/logo-white.png" alt="TUSAŞ — Türk Havacılık Uzay Sanayii" width="180" height="75"></div><div class="brand-title">Kurumsal Öğrenme<br>ve Yapay Zekâ</div><div class="brand-sub">Bilgiden gelişime, birlikte.</div></div>'+ 
    '<div class="nav-label">Çalışma alanı</div><nav class="nav" aria-label="Sayfalar" data-no-translate>'+listNav().map(function(item){
      return '<button data-page="'+item[0]+'" '+(activePage===item[0]?'aria-current="page"':'')+' class="'+(activePage===item[0]?"active":"")+'"><span class="nav-ico">'+navIcon(item[1])+'</span>'+esc(item[2])+'</button>'
    }).join("")+'</nav>'+
    '<div class="side-card"><strong><span class="persona-dot"></span>'+esc(persona.name)+'</strong>'+esc(persona.org)+'<span class="side-caption">İnsan kontrollü karar<br>İzlenebilir öğrenme yolculuğu</span></div>';
  renderAIConnectionStatus()
}

/* ---------------- ROUTING ---------------- */
function render(){
  if(typeof PORTAL!=='undefined'){
    if(!PORTAL.user)state.currentPage='portal-login';
    else if(PORTAL.isAdmin&&state.currentPage!=='admin-panel'){state.currentPage='admin-panel';PORTAL.adminTab='requests'}
    else if(!PORTAL.isAdmin&&!/^(submitter-|portal-)/.test(state.currentPage))state.currentPage='submitter-home';
  }
  renderShell();
  var route=state.currentPage;
  if(typeof renderPortalRoute==='function'&&renderPortalRoute(route))return;
  if(route==="executive-overview")return renderExecutiveOverview();
  if(route==="guided-demo")return renderGuidedDemo();
  if(route==="analyst-dashboard")return renderAnalystDashboard();
  if(route==="signals")return renderLearningSignals();
  if(route==="open-analysis")return renderOpenAnalysis();
  if(route==="survey")return renderSurveyCoverage();
  if(route==="needs")return renderNeeds();
  if(route==="need-detail")return renderNeedDetail();
  if(route==="critical")return renderCritical();
  if(route==="decisions")return renderDecisions();
  if(route==="audit")return renderAudit();
  if(route==="requester-home")return renderRequesterHome();
  if(route==="find-training")return renderFindTraining();
  if(route==="new-request")return renderNewRequest();
  if(route==="my-requests")return renderMyRequests();
  if(route==="catalog")return renderCatalog();
  if(route==="handoffs")return renderHandoffs();
  if(route==="handoff-detail")return renderHandoffDetail();
  if(route==="roadmap")return renderRoadmap();
  state.currentPage=defaultPage(state.currentRole);saveState();render()
}

/* ---------------- EXECUTIVE / PRESENTATION PAGES ---------------- */
function renderExecutiveOverview(){
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

function renderGuidedDemo(){
  var cards=[
    {n:"01",title:"Signal Sources",text:"Farklı kaynaklardan Learning Signal geldiğini ve ortak veri omurgasında tutulduğunu gösterin.",target:"signals",label:"Learning Signals"},
    {n:"02",title:"Survey Coverage",text:"Yıllık ankette her birimin aynı katılım düzeyine sahip olmadığını gösterin.",target:"survey",label:"Survey Coverage"},
    {n:"03",title:"Smart Grouping",text:"Pivot, Excel, Power Query ve Power BI yanıtlarının aynı cluster altında önerildiğini çalıştırın.",target:"open-analysis",label:"Açık Uçlu Analiz"},
    {n:"04",title:"Need Evidence",text:"Dört farklı kaynaktaki sinyallerin NEED-0028 altında birleştiğini gösterin.",target:"need:NEED-0028",label:"NEED-0028"},
    {n:"05",title:"Course Match",text:"Power BI Temelleri’nin bulunduğunu, fakat ileri dashboard ihtiyacını kısmen karşıladığını gösterin.",target:"need:NEED-0028",label:"Existing Solution Analysis"},
    {n:"06",title:"Design Handoff",text:"İnsan kararı sonrası kanıtı kaybolmayan yapılandırılmış tasarım brief’ini gösterin.",target:"handoff:HND-2026-0008",label:"Training Design Handoff"}
  ];
  $("#appView").innerHTML=pageHead("Guided Demo","5–10 dakikalık yönetici anlatımında ürünün çalışan dikey kesitini adım adım izleyin.",'<button class="btn" data-page="executive-overview">← Overview</button>')+
    '<div class="notice"><strong>Sunum anlatısı:</strong> Bu akış bir slide gösterisi değil; uygulamanın gerçek ekranlarını izleyen kısa bir rehberdir.</div>'+
    '<div class="grid guide-grid" style="margin-top:14px">'+cards.map(function(card){
      return '<article class="card guide-card"><div class="guide-num">'+card.n+'</div><h2>'+esc(card.title)+'</h2><p>'+esc(card.text)+'</p><button class="btn '+(card.n==="01"?"primary":"")+'" data-demo-target="'+esc(card.target)+'">'+esc(card.label)+' →</button></article>'
    }).join("")+'</div>'+
    '<section class="card" style="margin-top:14px"><h2>Final message</h2><p>Bu MVP eğitim tasarımını otomatikleştirmiyor. Farklı öğrenme sinyallerinin ortak ihtiyaca ve izlenebilir eğitim kararına dönüşebildiğini kanıtlıyor.</p></section>'
}

/* ---------------- ANALYST PAGES ---------------- */
function renderAnalystDashboard(){
  var signals=state.learningSignals;
  var unclassified=signals.filter(function(s){return s.openText&&s.humanStatus!=="ACCEPTED"}).length;
  var campaign=state.surveyCampaigns[0];
  var low=campaign.units.filter(function(u){return coverageStatus(u)==="Low Coverage"}).length;
  var critical=signals.filter(function(s){return s.riskLevel==="Critical"&&s.status!=="RESOLVED"}).length;
  var ready=state.needs.filter(function(n){return n.status==="READY_FOR_DECISION"}).length;
  var sourceCounts=DemoDB.aggregate("learningSignals","sourceType");
  var top=state.needs.slice().sort(function(a,b){return b.signalIds.length-a.signalIds.length}).slice(0,5);
  $("#appView").innerHTML=pageHead("İhtiyaç Analizi Dashboard","Nerede öğrenme ihtiyacı oluştuğunu; kaynak, coverage, Need ve karar bağlamıyla izleyin.",'<button class="btn primary" data-page="open-analysis">Akıllı analizi aç</button>')+
    '<div class="grid kpis">'+kpi("Captured Signals",signals.length,"ortak veri modeli")+kpi("Unclassified Open Text",unclassified,"human review")+kpi("Low Coverage Units",low,"coverage context")+kpi("Active Needs",state.needs.filter(function(n){return n.status!=="CLOSED"}).length,"toplulaştırılmış")+kpi("Critical Review",critical,"fast lane")+kpi("Ready for Decision",ready,"human decision")+'</div>'+
    '<div class="grid chart-grid">'+
      '<section class="card"><h2>Signals by Source</h2>'+barList(Object.keys(sourceCounts).map(function(key){return {label:(SOURCE_META[key]||SOURCE_META.Other).short,value:sourceCounts[key]}}),120)+'</section>'+
      '<section class="card"><h2>Top Needs</h2>'+barList(top.map(function(n){return {label:n.title,value:n.signalIds.length}}),top[0].signalIds.length)+'</section>'+
      '<section class="card"><h2>Coverage by Unit</h2>'+barList(campaign.units.map(function(u){return {label:orgName(u.organizationId),value:pct(u.responses,u.target),display:pct(u.responses,u.target)+"%",color:coverageStatus(u)==="Low Coverage"?"red":coverageStatus(u)==="Watch"?"amber":"teal"}}),100)+'<p class="caption">Coverage oranı ihtiyaç doğruluğu değildir.</p></section>'+
      '<section class="card"><h2>Decision Outcomes</h2>'+barList(["USE_EXISTING","REVISE_EXISTING","CREATE_NEW","DEFER","REJECT"].map(function(type){return {label:type.replaceAll("_"," "),value:state.decisions.filter(function(d){return d.type===type}).length}}),3)+'</section>'+
      '<section class="card critical-panel"><div class="tags">'+badge("Popularity ≠ Priority")+badge(critical+" Critical")+'</div><h2 style="margin-top:12px">Critical Content Fast Lane</h2><p>Tek bir güvenlik bildirimi bile normal talep hacminden bağımsız olarak Immediate Review hattına alınır.</p><button class="btn sm danger" data-page="critical">Critical Review aç</button></section>'+
      '<section class="card"><h2>Son Traceability Olayları</h2>'+state.audit.slice(0,6).map(function(a){return '<div class="time-item"><div class="time-line"><div class="dot"></div><div class="vline"></div></div><div><div class="time-title">'+esc(a.action)+'</div><div class="time-meta">'+esc(a.entity)+' · '+esc(a.actor)+' · '+esc(a.timestamp)+'</div></div></div>'}).join("")+'</section>'+
    '</div>'
}

function renderLearningSignals(){
  var rows=state.learningSignals.slice().reverse();
  $("#appView").innerHTML=pageHead("Learning Signals","Request, survey, feedback, dış platform ve kritik içerik sinyallerini kişisel performans değerlendirmesi üretmeden ortak modelde izleyin.",'<button class="btn" data-page="open-analysis">Açık uçlu analize git</button>')+
    '<div class="notice"><strong>Privacy by design:</strong> Survey sinyalleri anonimdir. Analist görünümü kişi adı yerine rol ve organizasyon bağlamı gösterir; bireysel performans puanı üretmez.</div>'+
    '<div class="filters" style="margin-top:12px"><input id="signalSearch" type="search" placeholder="Signal ID, özet veya konu ara…" aria-label="Learning Signal ara"><select id="signalSourceFilter" aria-label="Kaynak filtresi"><option value="">Tüm kaynaklar</option>'+Object.keys(SOURCE_META).map(function(source){return '<option value="'+esc(source)+'">'+esc(SOURCE_META[source].short)+'</option>'}).join("")+'</select><select id="signalStatusFilter" aria-label="Durum filtresi"><option value="">Tüm durumlar</option><option>CAPTURED</option><option>LINKED</option><option>CLASSIFIED</option><option>HUMAN_REVIEW</option><option>UNCLASSIFIED</option><option>IMMEDIATE_REVIEW</option></select></div>'+
    '<div class="table-wrap"><table><thead><tr><th>Signal ID</th><th>Summary</th><th>Source</th><th>Role</th><th>Organization</th><th>Suggested Topic</th><th>Need</th><th>Status</th><th>Date</th></tr></thead><tbody id="signalRows">'+
    rows.map(function(signal){
      var needLabel=signal.linkedNeedIds.length?signal.linkedNeedIds.join(", "):"—";
      var search=(signal.id+" "+signal.summary+" "+(signal.topicHint||signal.suggestedCluster||"")+" "+orgName(signal.organizationId)).toLocaleLowerCase("tr-TR");
      return '<tr class="clickable signal-row" data-signal-id="'+signal.id+'" data-source="'+esc(signal.sourceType)+'" data-status="'+esc(signal.status)+'" data-search="'+esc(search)+'"><td><strong>'+esc(signal.id)+'</strong></td><td class="table-title">'+originalText(signal.summary)+'</td><td>'+sourceBadge(signal.sourceType)+'</td><td>'+esc(signal.anonymous?"Anonim":signal.personRole)+'</td><td>'+esc(orgName(signal.organizationId))+'</td><td>'+(signal.topicHint||signal.suggestedCluster?esc(signal.topicHint||signal.suggestedCluster):'<span class="subtle">Unclassified</span>')+'</td><td>'+esc(needLabel)+'</td><td>'+badge(signal.status)+'</td><td>'+fmtDate(signal.createdAt)+'</td></tr>'
    }).join("")+'</tbody></table></div><p class="caption" id="signalResultCount" style="margin-top:8px">'+rows.length+' kayıt gösteriliyor.</p>';
  bindSignalFilters()
}
function bindSignalFilters(){
  var search=$("#signalSearch"),source=$("#signalSourceFilter"),status=$("#signalStatusFilter");
  function apply(){
    var text=search.value.toLocaleLowerCase("tr-TR"),count=0;
    document.querySelectorAll(".signal-row").forEach(function(row){
      var visible=(!text||row.dataset.search.indexOf(text)>-1)&&(!source.value||row.dataset.source===source.value)&&(!status.value||row.dataset.status===status.value);
      row.style.display=visible?"":"none";if(visible)count++
    });
    $("#signalResultCount").textContent=count+" kayıt gösteriliyor."
  }
  [search,source,status].forEach(function(node){node.addEventListener(node===search?"input":"change",apply)})
}

function renderOpenAnalysis(){
  var all=state.learningSignals.filter(function(s){return s.openText});
  var accepted=all.filter(function(s){return s.humanStatus==="ACCEPTED"}).length;
  var review=all.filter(function(s){return s.humanStatus==="REVIEW_REQUIRED"}).length;
  var unclassified=all.filter(function(s){return s.humanStatus==="UNCLASSIFIED"}).length;
  var filter=state.analysisFilter||"ALL";
  var rows=all.filter(function(s){return filter==="ALL"||s.humanStatus===filter});
  $("#appView").innerHTML=pageHead("Açık Uçlu Cevap Analizi","Deterministic, açıklanabilir kurallar benzer konu önerileri üretir; her öneri insan incelemesi gerektirir.",'<button class="btn blue" data-action="run-analysis">Run Smart Analysis</button>')+
    '<div class="grid kpis kpis-four">'+kpi("Açık uçlu yanıt",all.length,"analiz kapsamı")+kpi("Kabul edilen",accepted,"insan tarafından onaylandı")+kpi("İnsan incelemesi",review,"onay bekleyen öneri")+kpi("Sınıflandırılmamış",unclassified,"yeni bağlam gerekli")+'</div>'+
    '<div class="notice"><strong>Demo Smart Analysis:</strong> Bu ekranda dış AI servisi veya uydurma model adı kullanılmaz. Keyword/similarity kuralları öneri üretir; nihai sınıflandırma analiste aittir.'+(state.analysisRunAt?'<br><span class="caption">Son çalışma: '+esc(state.analysisRunAt)+'</span>':"")+'</div>'+
    '<div class="pill-tabs">'+[
      ["ALL","Tümü ("+all.length+")"],["REVIEW_REQUIRED","Human Review ("+review+")"],["ACCEPTED","Accepted ("+accepted+")"],["UNCLASSIFIED","Unclassified ("+unclassified+")"]
    ].map(function(tab){return '<button class="'+(filter===tab[0]?"active":"")+'" data-analysis-filter="'+tab[0]+'">'+tab[1]+'</button>'}).join("")+'</div>'+
    '<div class="table-wrap"><table><thead><tr><th>Raw response</th><th>Suggested Cluster</th><th>Confidence</th><th>Source</th><th>Organization</th><th>Human Status</th><th>Human Action</th></tr></thead><tbody>'+
    rows.map(function(signal){
      var actions=signal.humanStatus==="REVIEW_REQUIRED"?
        '<div class="inline-actions"><button class="btn sm primary" data-action="accept-cluster" data-signal="'+signal.id+'">Accept</button><button class="btn sm" data-action="change-cluster" data-signal="'+signal.id+'">Change Cluster</button><button class="btn sm" data-action="leave-unclassified" data-signal="'+signal.id+'">Leave Unclassified</button></div>':
        signal.humanStatus==="UNCLASSIFIED"?'<div class="inline-actions"><button class="btn sm" data-action="change-cluster" data-signal="'+signal.id+'">Assign Cluster</button></div>':'<span class="subtle">Human confirmed</span>';
      return '<tr><td class="table-title">“'+originalText(signal.rawText)+'”</td><td>'+(signal.suggestedCluster?badge(signal.suggestedCluster):'<span class="subtle">No suggestion</span>')+'</td><td>'+(signal.suggestionConfidence?signal.suggestionConfidence+"%":"—")+'</td><td>'+sourceBadge(signal.sourceType)+'</td><td>'+esc(orgName(signal.organizationId))+'</td><td>'+badge(signal.humanStatus)+'</td><td>'+actions+'</td></tr>'
    }).join("")+'</tbody></table></div>'
}

function renderSurveyCoverage(){
  var campaign=state.surveyCampaigns[0],target=campaign.units.reduce(function(s,u){return s+u.target},0),responses=campaign.units.reduce(function(s,u){return s+u.responses},0),open=campaign.units.reduce(function(s,u){return s+u.openResponses},0);
  $("#appView").innerHTML=pageHead("Yıllık İhtiyaç Analizi","Survey builder değil; katılım kapsamını ve açık uçlu analiz yükünü görünür kılan sentetik coverage ekranıdır.")+
    '<section class="card"><div class="tags">'+badge(campaign.id)+badge(campaign.status)+'<span class="badge b-gray">Demo thresholds: ≥'+CONFIG.coverage.healthy+' Healthy · '+CONFIG.coverage.watch+'–'+(CONFIG.coverage.healthy-1)+' Watch · &lt;'+CONFIG.coverage.watch+' Low</span></div><h2 style="margin-top:12px">'+esc(campaign.title)+'</h2>'+
    '<div class="metric-row"><div class="mini-metric"><div class="n">'+target+'</div><div class="t">Target population</div></div><div class="mini-metric"><div class="n">'+responses+'</div><div class="t">Responses</div></div><div class="mini-metric"><div class="n">'+pct(responses,target)+'%</div><div class="t">Response rate</div></div><div class="mini-metric"><div class="n">'+open+'</div><div class="t">Open text count</div></div></div>'+
    '<div class="notice warning"><strong>Düşük yanıt sayısı, ihtiyacın bulunmadığını göstermez.</strong> Sonuçlar katılım kapsamıyla birlikte yorumlanmalıdır. Eşikler kurum politikası değil, ayarlanabilir demo config değerleridir.</div></section>'+
    '<div class="table-wrap" style="margin-top:14px"><table><thead><tr><th>Organization</th><th>Target</th><th>Responses</th><th>Coverage</th><th>Open Responses</th><th>Status</th><th>Reminder Status</th><th>Demo Action</th></tr></thead><tbody>'+
    campaign.units.map(function(unit){
      var rate=pct(unit.responses,unit.target),status=coverageStatus(unit);
      return '<tr><td class="table-title">'+esc(orgName(unit.organizationId))+'</td><td>'+unit.target+'</td><td>'+unit.responses+'</td><td><div class="coverage-row"><div class="progress"><span style="width:'+rate+'%;background:'+(status==="Low Coverage"?"#DD140E":status==="Watch"?"#D29F13":"#263685")+'"></span></div><strong>'+rate+'%</strong></div><div class="caption">'+unit.responses+' / '+unit.target+' target</div></td><td>'+unit.openResponses+'</td><td>'+badge(status)+'</td><td>'+badge(unit.reminderStatus)+'</td><td>'+(unit.reminderStatus==="Planned"?'<span class="subtle">Action recorded</span>':unit.reminderStatus==="Not Required"?'<span class="subtle">Aksiyon gerekmiyor</span>':'<button class="btn sm" data-action="plan-reminder" data-org="'+unit.organizationId+'">Hatırlatma Planla</button>')+'</td></tr>'
    }).join("")+'</tbody></table></div>'+
    '<div class="grid chart-grid" style="margin-top:14px"><section class="card"><h2>Coverage Context</h2>'+barList(campaign.units.map(function(u){return {label:orgName(u.organizationId),value:pct(u.responses,u.target),display:pct(u.responses,u.target)+"%",color:coverageStatus(u)==="Low Coverage"?"red":coverageStatus(u)==="Watch"?"amber":"teal"}}),100)+'</section><section class="card"><h2>Interpretation Guardrail</h2><div class="insight-list"><div class="insight"><strong>Coverage ≠ Need accuracy</strong><span>Yanıt kapsamı analizin güven bağlamıdır.</span></div><div class="insight"><strong>Reminder is a demo action</strong><span>Gerçek e-posta gönderilmez; aksiyon ve audit kaydı oluşturulur.</span></div></div></section></div>'
}

function renderNeeds(){
  var needs=state.needs.slice().sort(function(a,b){
    var rank={Critical:4,High:3,Medium:2,Low:1};return (rank[b.humanPriority]||0)-(rank[a.humanPriority]||0)||b.signalIds.length-a.signalIds.length
  });
  $("#appView").innerHTML=pageHead("Learning Needs","Farklı kaynaklardaki sinyalleri ortak ihtiyaç altında görün; evidence hacmini nihai öncelikle karıştırmayın.")+
    '<div class="notice"><strong>Farklı sinyaller, ortak bir ihtiyaç.</strong> Anket, talep ve geri bildirim kayıtları tekil çalışan sayısı olarak toplanmaz. Nihai öncelik insan değerlendirmesiyle belirlenir.</div>'+
    '<div class="grid need-grid" style="margin-top:14px">'+needs.map(function(need){
      var ev=needEvidence(need),mix=ev.mix;
      return '<article class="card need-card"><div class="tags">'+badge(need.id)+badge(need.humanPriority)+badge(need.status)+'</div><h2 style="margin-top:12px">'+esc(need.title)+'</h2><p>'+esc(need.summary)+'</p>'+sourceComposition(need)+
        '<div class="metric-row"><div class="mini-metric"><div class="n">'+need.signalIds.length+'</div><div class="t">Evidence records</div></div><div class="mini-metric"><div class="n">'+ev.sourceCount+'</div><div class="t">Source types</div></div><div class="mini-metric"><div class="n">'+ev.orgCount+'</div><div class="t">Organizations</div></div><div class="mini-metric"><div class="n">'+(mix["Course Feedback"]||0)+'</div><div class="t">Feedback</div></div></div>'+
        '<div class="push"><p class="caption">Suggested Priority: '+esc(need.suggestedPriority)+' · Human Priority: '+esc(need.humanPriority)+'</p><button class="btn sm primary" data-need-id="'+need.id+'">İhtiyacın kanıtlarını incele</button></div></article>'
    }).join("")+'</div>'
}

function sourceGroupForFilter(source){
  if(source==="Annual Survey")return "Survey";
  if(source==="Manual Request")return "Request";
  if(source==="Course Feedback"||source==="Instructor Feedback")return "Feedback";
  if(source==="External Learning Platform")return "External";
  if(source==="Content / Critical")return "Content";
  return "Other"
}
function renderNeedDetail(){
  var need=DemoDB.findById("needs",state.selectedNeedId)||DemoDB.findById("needs","NEED-0028");
  state.selectedNeedId=need.id;
  var ev=needEvidence(need),mix=ev.mix,filter=state.needSignalFilter||"All";
  var filtered=ev.signals.filter(function(signal){return filter==="All"||sourceGroupForFilter(signal.sourceType)===filter});
  var decision=need.decisionId?DemoDB.findById("decisions",need.decisionId):null;
  var handoff=need.handoffId?DemoDB.findById("handoffs",need.handoffId):null;
  var matches=matchExistingCourses(need);
  var representative=ev.signals.filter(function(s){return s.rawText}).slice(0,3);
  var sourceRows=Object.keys(mix).map(function(source){return {label:(SOURCE_META[source]||SOURCE_META.Other).short,value:mix[source]}});
  $("#appView").innerHTML=pageHead(need.id+" — "+need.title,"Farklı kaynaklardan gelen kanıtlar, mevcut eğitim kapsamı ve kararın tasarıma aktarım süreci.",'<button class="btn" data-action="print">Print Summary</button><button class="btn primary" data-action="open-decision" data-need="'+need.id+'">'+(decision?"Kararı güncelle":"Human Decision")+'</button>')+
    '<section class="card"><div class="tags">'+badge(need.status)+badge("Human Priority: "+need.humanPriority)+badge("Suggested: "+need.suggestedPriority)+'</div><h2 style="margin-top:12px">Executive Summary</h2><p style="font-size:14px;color:#4D4D4D">'+esc(need.summary)+'</p><div class="notice"><strong>Evidence Summary:</strong> '+esc(evidenceSummaryText(need))+'</div>'+
    '<div class="metric-row"><div class="mini-metric"><div class="n">'+need.signalIds.length+'</div><div class="t">Evidence records</div></div><div class="mini-metric"><div class="n">'+ev.sourceCount+'</div><div class="t">Source types</div></div><div class="mini-metric"><div class="n">'+ev.orgCount+'</div><div class="t">Organizations</div></div><div class="mini-metric"><div class="n">'+ev.roleCount+'</div><div class="t">Person roles</div></div></div></section>'+
    '<div class="grid chart-grid" style="margin-top:14px"><section class="card"><h2>Evidence by Source</h2>'+barList(sourceRows,Math.max.apply(null,sourceRows.map(function(r){return r.value})))+'<p class="caption">Farklı evidence türleri tek bir “kişi sayısı” olarak yorumlanmaz.</p></section>'+
    '<section class="card"><h2>Representative Signals</h2><div class="quote-list">'+representative.map(function(s){return '<div class="quote">“'+originalText(s.rawText)+'”<div class="caption">'+esc((SOURCE_META[s.sourceType]||SOURCE_META.Other).short)+' · '+esc(orgName(s.organizationId))+' · '+(s.anonymous?"Anonymous":"Role context")+'</div></div>'}).join("")+'</div></section></div>'+
    '<div class="detail-grid" style="margin-top:14px"><section class="card"><div class="tags">'+badge("Existing Solution Analysis")+badge("Human Review Required")+'</div><h2 style="margin-top:12px">Mevcut eğitim gerçekten ihtiyacı karşılıyor mu?</h2>'+
      matches.map(function(match){var course=DemoDB.findById("courses",match.courseId);return '<div class="meta" style="margin-bottom:9px"><div style="display:flex;justify-content:space-between;gap:12px"><div><strong>'+esc(course.title)+'</strong><div class="caption">'+esc(course.level)+' · '+esc(course.summary)+'</div></div><div class="tags">'+badge(match.match+"% Match")+badge(match.coverage+" Coverage")+'</div></div><div class="progress" style="margin:10px 0"><span style="width:'+match.match+'%"></span></div><div class="caption">'+esc(match.reason)+'</div></div>'}).join("")+
      '<div class="notice warning"><strong>Recommendation:</strong> '+(need.id==="NEED-0028"?"Mevcut katalog kısmi kapsam sağlıyor. İleri dashboard, DAX ve yönetim raporlaması için human review required.":"Eşleşme konu ve hedef kitle bağlamıyla insan tarafından doğrulanmalıdır.")+'</div></section>'+
    '<aside class="card"><h2>Priority Context</h2><div class="meta-grid"><div class="meta"><div class="k">Impact</div><div class="v">'+esc(need.impact)+'</div></div><div class="meta"><div class="k">Urgency</div><div class="v">'+esc(need.urgency)+'</div></div><div class="meta"><div class="k">Breadth</div><div class="v">'+ev.orgCount+' organizations</div></div><div class="meta"><div class="k">Feedback repetition</div><div class="v">'+(mix["Course Feedback"]||0)+' records</div></div></div>'+
      '<div class="notice warning" style="margin-top:10px"><strong>Demand count != Priority.</strong> Coverage, breadth, risk ve tekrar bağlamı görünür tutulur; tek gizemli skora eritilmez.</div>'+
      (state.currentRole==="analyst"?'<div class="field" style="margin-top:12px"><label for="humanPriority">Human Priority</label><select id="humanPriority" data-need-priority="'+need.id+'"><option '+(need.humanPriority==="Low"?"selected":"")+'>Low</option><option '+(need.humanPriority==="Medium"?"selected":"")+'>Medium</option><option '+(need.humanPriority==="High"?"selected":"")+'>High</option><option '+(need.humanPriority==="Critical"?"selected":"")+'>Critical</option></select></div>':"")+
    '</aside></div>'+
    '<section class="card" style="margin-top:14px"><h2>Evidence Records</h2><div class="pill-tabs">'+["All","Survey","Request","Feedback","External","Content"].map(function(tab){return '<button class="'+(filter===tab?"active":"")+'" data-need-filter="'+tab+'">'+tab+' ('+ev.signals.filter(function(s){return tab==="All"||sourceGroupForFilter(s.sourceType)===tab}).length+')</button>'}).join("")+'</div>'+
    '<div class="table-wrap"><table><thead><tr><th>Signal</th><th>Representative text</th><th>Source</th><th>Organization</th><th>Privacy</th><th>Status</th></tr></thead><tbody>'+filtered.slice(0,30).map(function(signal){return '<tr class="clickable" data-signal-id="'+signal.id+'"><td><strong>'+signal.id+'</strong></td><td class="table-title">'+originalText(signal.rawText)+'</td><td>'+sourceBadge(signal.sourceType)+'</td><td>'+esc(orgName(signal.organizationId))+'</td><td>'+badge(signal.anonymous?"Anonymous / Aggregate":"Role Context")+'</td><td>'+badge(signal.status)+'</td></tr>'}).join("")+'</tbody></table></div><p class="caption">İlk '+Math.min(30,filtered.length)+' / '+filtered.length+' kayıt gösteriliyor.</p></section>'+
    '<section class="card" style="margin-top:14px"><h2>Need → Decision → Training Design Handoff</h2><div class="lineage"><div class="lineage-box"><div class="kind">Source Need</div><div class="title">'+esc(need.id)+'</div><div class="caption">'+ev.sourceCount+' source types · '+need.signalIds.length+' records</div></div><div class="lineage-arrow">→</div>'+
    '<div class="lineage-box"><div class="kind">Human Decision</div><div class="title">'+(decision?esc(decision.type):"Decision required")+'</div><div class="caption">'+(decision?esc(decision.rationale):"Rationale ile kaydedilmelidir.")+'</div></div><div class="lineage-arrow">→</div>'+
    '<div class="lineage-box"><div class="kind">Training Design Handoff</div><div class="title">'+(handoff?'<button class="link-btn" data-handoff-id="'+handoff.id+'">'+esc(handoff.id)+'</button>':"Not created")+'</div><div class="caption">'+(handoff?esc(handoff.status):"REVISE / CREATE kararı handoff oluşturur.")+'</div></div></div></section>'
}

function renderCritical(){
  var critical=state.learningSignals.filter(function(s){return s.sourceType==="Content / Critical"||s.riskLevel==="Critical"});
  $("#appView").innerHTML=pageHead("Critical Content / Immediate Review","Tek bir kritik içerik sinyali bile normal talep yoğunluğundan bağımsız olarak fast lane’e alınır.")+
    '<div class="notice critical"><strong>Popularity ≠ Priority.</strong> Risk taşıyan içerik sinyalleri survey clustering veya talep hacmini beklemez; human review ile ele alınır.</div>'+
    '<div class="grid three-grid" style="margin-top:14px">'+critical.map(function(signal){
      var request=signal.requestId?DemoDB.findById("requests",signal.requestId):null;
      return '<article class="card critical-panel"><div class="tags">'+badge(signal.riskLevel)+badge(signal.status)+sourceBadge(signal.sourceType)+'</div><h2 style="margin-top:12px">'+originalText(signal.summary)+'</h2><p>'+originalText(signal.rawText)+'</p>'+
        '<div class="meta-grid"><div class="meta"><div class="k">Signal ID</div><div class="v">'+signal.id+'</div></div><div class="meta"><div class="k">Related course</div><div class="v">'+esc(courseName(signal.relatedCourseId))+'</div></div><div class="meta"><div class="k">Organization</div><div class="v">'+esc(orgName(signal.organizationId))+'</div></div><div class="meta"><div class="k">Request</div><div class="v">'+esc(request?request.id:"—")+'</div></div></div>'+
        '<div class="inline-actions" style="margin-top:12px">'+(signal.status!=="IMMEDIATE_REVIEW"&&signal.status!=="RESOLVED"?'<button class="btn sm danger" data-action="open-critical" data-signal="'+signal.id+'">Immediate Review aç</button>':"")+(signal.status!=="RESOLVED"?'<button class="btn sm" data-action="resolve-critical" data-signal="'+signal.id+'">İncelemeyi kapat</button>':'<span class="badge b-green">Resolved</span>')+'</div></article>'
    }).join("")+'</div>'
}

function renderDecisions(){
  var rows=state.decisions.slice().reverse();
  $("#appView").innerHTML=pageHead("Human Decisions","Akıllı önerilerden ayrı tutulan, karar türü ve zorunlu rationale ile kaydedilmiş insan kararları.")+
    '<div class="table-wrap"><table><thead><tr><th>Decision</th><th>Need</th><th>Type</th><th>Related Course</th><th>Rationale</th><th>Decision Maker</th><th>Date</th><th>Handoff</th></tr></thead><tbody>'+
    rows.map(function(d){var need=DemoDB.findById("needs",d.needId);return '<tr><td><strong>'+d.id+'</strong></td><td><button class="link-btn" data-need-id="'+d.needId+'">'+d.needId+' · '+esc(need?need.title:"")+'</button></td><td>'+badge(d.type)+'</td><td>'+esc(courseName(d.relatedCourseId))+'</td><td class="table-title">'+esc(d.rationale)+'</td><td>'+esc(d.decisionMaker)+'</td><td>'+fmtDate(d.decisionDate)+'</td><td>'+(need&&need.handoffId?'<button class="link-btn" data-handoff-id="'+need.handoffId+'">'+need.handoffId+'</button>':"—")+'</td></tr>'}).join("")+
    '</tbody></table></div>'
}

function renderAudit(){
  $("#appView").innerHTML=pageHead("Audit & Traceability","State-changing aksiyonların actor, timestamp, entity ve before/after bağlamıyla kaydedildiği yerel demo izi.")+
    '<div class="table-wrap"><table><thead><tr><th>Timestamp</th><th>Actor</th><th>Entity</th><th>Action</th><th>Before</th><th>After</th></tr></thead><tbody>'+
    state.audit.map(function(a){return '<tr><td>'+esc(a.timestamp)+'</td><td>'+esc(a.actor)+'</td><td><span class="codeish">'+esc(a.entity)+'</span></td><td class="table-title">'+esc(a.action)+'</td><td>'+esc(a.before)+'</td><td>'+esc(a.after)+'</td></tr>'}).join("")+
    '</tbody></table></div><p class="caption">Bu iz gerçek bir backend audit servisi değil; MVP davranışını göstermek için localStorage’da saklanan sentetik demo kaydıdır.</p>'
}

/* ---------------- REQUESTER PAGES ---------------- */
function renderRequesterHome(){
  var mine=state.requests.filter(function(r){return r.submittedBy==="Demo Kullanıcı"}).slice().reverse();
  $("#appView").innerHTML=
    '<section class="hero"><div><div class="eyebrow">Çalışan · Gelişim Sinyali</div><h1>Ne öğrenmek veya geliştirmek istiyorsunuz?</h1><p>Önce mevcut eğitimleri keşfedin; ihtiyacınızı karşılamıyorsa içerik/seviye açığını veya yeni gelişim ihtiyacını paylaşın.</p><div class="inline-actions" style="margin-top:15px"><button class="btn primary" data-page="find-training">Akıllı Eğitim Bul</button><button class="btn" data-page="new-request">Yeni gelişim sinyali</button></div></div><div class="north-star"><strong>Demo tasarım prensibi</strong><span>Analiz görünümü bireysel performans puanı üretmez; gelişim sinyallerini toplulaştırılmış ihtiyaç analizi için kullanır. Uygulama kurum politikasının yerini almaz.</span></div></section>'+
    '<div class="grid three-grid"><article class="card"><div class="tags">'+badge("DISCOVERY_PROBLEM")+'</div><h2 style="margin-top:11px">Eğitim var, bulunamıyor</h2><p>Uygun katalog kaydı bulunursa formal request açmadan yönlendirme kaydedilebilir.</p><button class="btn sm" data-page="find-training">Eğitim ara</button></article>'+
    '<article class="card"><div class="tags">'+badge("COVERAGE_PROBLEM")+'</div><h2 style="margin-top:11px">Eğitim var, kapsam yetersiz</h2><p>İçerik veya seviye ihtiyacı karşılamıyorsa yeni Learning Signal oluşur.</p><button class="btn sm" data-page="catalog">Kataloğu incele</button></article>'+
    '<article class="card"><div class="tags">'+badge("SOLUTION_GAP")+'</div><h2 style="margin-top:11px">Uygun çözüm bulunmuyor</h2><p>Formal gelişim talebi bir Request ve bağlı Learning Signal olarak kaydedilir.</p><button class="btn sm" data-page="new-request">Talep oluştur</button></article></div>'+
    '<div class="grid section-grid" style="margin-top:14px"><section class="card"><h2>Son Taleplerim</h2>'+(mine.length?mine.slice(0,5).map(function(r){return '<div class="time-item"><div class="time-line"><div class="dot"></div><div class="vline"></div></div><div><div class="time-title"><button class="link-btn" data-request-id="'+r.id+'">'+r.id+' · '+esc(r.title)+'</button></div><div class="time-meta">'+badge(r.status)+' · '+fmtDate(r.updatedAt)+'</div></div></div>'}).join(""):'<div class="empty">Henüz talep yok.</div>')+'</section>'+
    '<section class="card"><h2>Bir sinyal gönderince ne olur?</h2><div class="timeline">'+["Learning Signal kaydı oluşur","Benzer sinyaller için akıllı öneri üretilir","İnsan analist Need ve existing coverage bağlamını değerlendirir","Gerekçeli karar ve gerekiyorsa tasarım handoff’u kaydedilir"].map(function(text){return '<div class="time-item"><div class="time-line"><div class="dot"></div><div class="vline"></div></div><div><div class="time-title">'+text+'</div><div class="time-meta">Kişisel performans değerlendirmesi üretilmez.</div></div></div>'}).join("")+'</div></section></div>'
}

function matchCoursesForText(text){
  var value=String(text||"").toLocaleLowerCase("tr-TR");
  var scores=state.courses.map(function(course){
    var terms=course.tags.concat(course.skills).concat([course.title,course.topic]);
    var hits=terms.reduce(function(sum,term){var words=String(term).toLocaleLowerCase("tr-TR").split(/\s+/);return sum+words.reduce(function(s,w){return s+(w.length>2&&value.indexOf(w)>-1?1:0)},0)},0);
    return {course:course,score:Math.min(94,30+hits*13)}
  }).filter(function(row){return row.score>30}).sort(function(a,b){return b.score-a.score});
  return scores.length?scores.slice(0,3):state.courses.slice(0,3).map(function(course,i){return {course:course,score:42-i*5}})
}
function renderFindTraining(){
  $("#appView").innerHTML=pageHead("Akıllı Eğitim Bul","Tam chatbot değil; mevcut eğitim keşfi ile coverage gap’i ayıran ince, kural tabanlı bir arama deneyimi.",'<button class="btn" data-page="new-request">Doğrudan talep oluştur</button>')+
    '<section class="card"><div class="field"><label for="courseDiscoveryText">Ne öğrenmek veya geliştirmek istiyorsunuz?</label><textarea id="courseDiscoveryText" placeholder="Örn. Power BI ile yönetim dashboard’u hazırlamak istiyorum.">Power BI ile yönetim dashboard’u hazırlamak istiyorum.</textarea><div class="hint">Arama demo kurallarıyla sentetik katalog üzerinde çalışır; dış servis veya gerçek AI çağrısı yoktur.</div></div><button class="btn primary" data-action="search-courses">Benzer eğitimleri bul</button></section>'+
    '<div id="courseDiscoveryResults" style="margin-top:14px"></div>'
}
function renderCourseDiscoveryResults(text){
  var results=matchCoursesForText(text),container=$("#courseDiscoveryResults");
  container.innerHTML='<div class="grid three-grid">'+results.map(function(row){
    var levelNote=row.course.id==="CRS-003"?"Bu eğitim temel seviyededir; ileri dashboard ve DAX kapsamı sınırlıdır.":row.course.summary;
    return '<article class="card"><div class="tags">'+badge(row.score+"% Match")+badge(row.course.level)+'</div><h2 style="margin-top:12px">'+esc(row.course.title)+'</h2><p>'+esc(levelNote)+'</p><div class="inline-actions"><button class="btn sm primary" data-action="course-meets" data-course="'+row.course.id+'" data-query="'+esc(text)+'">İhtiyacımı karşılıyor</button><button class="btn sm" data-action="course-insufficient" data-course="'+row.course.id+'" data-query="'+esc(text)+'">İçerik/seviye yetersiz</button></div></article>'
  }).join("")+'</div><div class="notice" style="margin-top:12px"><strong>Outcome ayrımı:</strong> Karşılıyorsa formal request oluşmaz; bir discovery signal çözüm bilgisiyle kaydedilir. Yetersizse coverage problem signal’ı analiz backlog’una gider.</div>'
}

function renderNewRequest(){
  var draft=state.requestDraft||"";
  $("#appView").innerHTML=pageHead("Yeni Gelişim Sinyali","Formal talep bir Request kaydı ve ona bağlı ayrı Learning Signal kaydı oluşturur.",'<button class="btn" data-page="requester-home">Vazgeç</button>')+
    '<div class="notice"><strong>Güven veren tasarım prensibi:</strong> Eğitim/gelişim sinyali performans değerlendirmesi değildir. Analiz görünümü bireysel performans puanı üretmez ve sinyalleri mümkün olduğunda toplulaştırılmış değerlendirir.</div>'+
    '<section class="card" style="margin-top:14px;max-width:900px"><form id="requestForm"><div class="field"><label for="requestText">İhtiyacınızı veya bildiriminizi anlatın *</label><textarea id="requestText" name="description" required>'+esc(draft)+'</textarea><div class="hint">Örn. Power BI ile ileri dashboard hazırlamak istiyorum; mevcut başlangıç eğitimi ihtiyacımı karşılamıyor.</div></div>'+
    '<div class="form-grid"><div class="field"><label for="requestCourse">İlgili mevcut eğitim</label><select id="requestCourse" name="course"><option value="">İlgili eğitim yok / emin değilim</option>'+state.courses.map(function(c){return '<option value="'+c.id+'">'+esc(c.title)+'</option>'}).join("")+'</select></div><div class="field"><label for="desiredPeriod">Ne zaman ihtiyaç duyuluyor?</label><select id="desiredPeriod" name="period"><option>Bu dönem</option><option>Gelecek dönem</option><option>Mümkün olan en kısa zamanda</option><option>Acil değil / öneri</option></select></div></div>'+
    '<div class="form-grid"><div class="field"><label for="affected">Kimleri etkiliyor?</label><select id="affected" name="affected"><option>Sadece beni</option><option>Ekibimi</option><option>Bölümümü</option><option>Birden fazla birimi</option></select></div><div class="field"><label>Kritik içerik şüphesi var mı?</label><div class="radio-row"><div class="radio-pill"><input id="criticalNo" type="radio" name="critical" value="no" checked><label for="criticalNo">Hayır</label></div><div class="radio-pill"><input id="criticalYes" type="radio" name="critical" value="yes"><label for="criticalYes">Evet, prosedür yanlış/riskli olabilir</label></div></div></div></div>'+
    '<div id="criticalFormNotice" class="notice critical" style="display:none;margin-bottom:13px"><strong>Immediate Review:</strong> Bu kayıt normal talep hacmini beklemeden kritik inceleme kuyruğuna alınır.</div>'+
    '<div class="form-actions"><button class="btn primary" type="submit">Request + Learning Signal oluştur</button></div></form></section>';
  bindRequestForm()
}
function bindRequestForm(){
  document.querySelectorAll('input[name="critical"]').forEach(function(input){input.addEventListener("change",function(e){$("#criticalFormNotice").style.display=e.target.value==="yes"?"block":"none"})});
  $("#requestForm").addEventListener("submit",function(e){
    e.preventDefault();var data=new FormData(e.target),description=String(data.get("description")||"").trim();
    if(!description)return;
    var title=description.split(/[.!?]/)[0].slice(0,75)||"Yeni gelişim ihtiyacı";
    var request=createRequestRecord({title:title,description:description,relatedCourseId:data.get("course")||null,desiredPeriod:data.get("period"),affected:data.get("affected"),critical:data.get("critical")==="yes"});
    state.requestDraft="";state.selectedRequestId=request.id;saveState();
    $("#appView").innerHTML='<section class="card success-screen"><div class="success-icon">✓</div><h1>Bildirim alındı</h1><p>'+(request.issueFlag?"Kritik içerik şüphesi nedeniyle kayıt Immediate Review kuyruğuna yönlendirildi.":"Request ve ona bağlı Learning Signal aynı veri omurgasında oluşturuldu.")+'</p><div style="font-size:22px;font-weight:850;margin:15px">'+request.id+' → '+request.signalId+'</div><div class="inline-actions" style="justify-content:center"><button class="btn primary" data-page="my-requests">Taleplerime git</button><button class="btn" data-page="requester-home">Ana sayfa</button></div></section>';
    toast("İlişkili Request ve Learning Signal kaydedildi.")
  })
}
function renderMyRequests(){
  var rows=state.requests.filter(function(r){return r.submittedBy==="Demo Kullanıcı"}).slice().reverse();
  $("#appView").innerHTML=pageHead("Taleplerim","Kendi formal taleplerinizi ve bağlı Learning Signal kaydını izleyin.",'<button class="btn primary" data-page="new-request">Yeni gelişim sinyali</button>')+
    '<div class="table-wrap"><table><thead><tr><th>Request</th><th>Başlık</th><th>Signal</th><th>İlgili eğitim</th><th>Need</th><th>Durum</th><th>Tarih</th></tr></thead><tbody>'+
    rows.map(function(r){return '<tr class="clickable" data-request-id="'+r.id+'"><td><strong>'+r.id+'</strong></td><td class="table-title">'+esc(r.title)+'</td><td><span class="codeish">'+r.signalId+'</span></td><td>'+esc(courseName(r.relatedCourseId))+'</td><td>'+esc(r.needId||"—")+'</td><td>'+badge(r.status)+'</td><td>'+fmtDate(r.updatedAt)+'</td></tr>'}).join("")+
    '</tbody></table></div>'
}
function renderCatalog(){
  $("#appView").innerHTML=pageHead("Sentetik Eğitim Kataloğu","Existing solution discovery ve coverage problem ayrımını göstermek için kullanılan küçük demo kataloğu. Bu MVP bir LMS değildir.",'<button class="btn" data-page="find-training">Akıllı Eğitim Bul</button>')+
    '<div class="grid need-grid">'+state.courses.map(function(c){return '<article class="card need-card"><div class="tags">'+badge(c.status)+badge(c.level)+'</div><h2 style="margin-top:12px">'+esc(c.title)+'</h2><p>'+esc(c.summary)+'</p><div class="tags">'+c.skills.map(function(skill){return '<span class="badge b-gray">'+esc(skill)+'</span>'}).join("")+'</div><div class="push"><p class="caption">Audience: '+esc(c.audience.join(", "))+'</p><button class="btn sm" data-action="course-feedback" data-course="'+c.id+'">Bu eğitim hakkında feedback</button></div></article>'}).join("")+'</div>'
}

/* ---------------- TRAINING DESIGN PAGES ---------------- */
function renderHandoffs(){
  var rows=state.handoffs.slice().reverse();
  $("#appView").innerHTML=pageHead("Training Design Handoff","Need analizinden eğitim tasarım birimine aktarılan, iki durumlu yapılandırılmış brief kuyruğu. Sistem eğitimi kendisi tasarlamaz.")+
    '<div class="notice"><strong>Aktarım kapsamı:</strong> Tasarıma hazır ve teslim alındı durumları, ihtiyaç analizinin tasarım birimine aktarımını izler. Eğitim programının tasarlanması bu prototipin kapsamı dışındadır.</div>'+
    '<div class="table-wrap" style="margin-top:14px"><table><thead><tr><th>Handoff</th><th>Proposed Title</th><th>Source Need</th><th>Solution Type</th><th>Related Course</th><th>Evidence</th><th>Status</th><th>Date</th></tr></thead><tbody>'+
    rows.map(function(h){return '<tr class="clickable" data-handoff-id="'+h.id+'"><td><strong>'+h.id+'</strong></td><td class="table-title">'+esc(h.proposedTitle)+'</td><td>'+h.sourceNeedId+'</td><td>'+badge(h.solutionType)+'</td><td>'+esc(courseName(h.relatedCourseId))+'</td><td>'+esc(h.evidenceSummary)+'</td><td>'+badge(h.status)+'</td><td>'+fmtDate(h.createdAt)+'</td></tr>'}).join("")+
    '</tbody></table></div>'
}
function renderHandoffDetail(){
  var handoff=DemoDB.findById("handoffs",state.selectedHandoffId)||state.handoffs[0];
  if(!handoff){state.currentPage="handoffs";return render()}
  var need=DemoDB.findById("needs",handoff.sourceNeedId),decision=DemoDB.findById("decisions",handoff.decisionId),ev=needEvidence(need),mix=signalSourceMix(need);
  var reps=ev.signals.filter(function(s){return s.rawText}).slice(0,3);
  $("#appView").innerHTML=pageHead(handoff.id+" — "+handoff.proposedTitle,"Kaynak ihtiyaç, insan kararı ve kanıt zinciri korunarak eğitim tasarım birimine aktarılan analiz özeti.",'<button class="btn" data-action="print">Print Summary</button>'+(state.currentRole==="designer"&&handoff.status==="READY_FOR_DESIGN"?'<button class="btn primary" data-action="receive-handoff" data-handoff="'+handoff.id+'">Teslim al</button>':""))+
    '<section class="card"><div class="tags">'+badge(handoff.status)+badge(handoff.solutionType)+badge("Structured Brief")+'</div><h2 style="margin-top:12px">Analysis Brief</h2><p style="font-size:14px;color:#4D4D4D">'+esc(handoff.needSummary)+'</p><div class="notice"><strong>Why this course / revision exists:</strong> '+esc(decision?decision.rationale:"İnsan kararı bulunamadı.")+'</div>'+
    '<div class="metric-row"><div class="mini-metric"><div class="n">'+need.id+'</div><div class="t">Source Need</div></div><div class="mini-metric"><div class="n">'+ev.sourceCount+'</div><div class="t">Source types</div></div><div class="mini-metric"><div class="n">'+ev.orgCount+'</div><div class="t">Organizations</div></div><div class="mini-metric"><div class="n">'+ev.signals.length+'</div><div class="t">Evidence records</div></div></div></section>'+
    '<div class="detail-grid" style="margin-top:14px"><section class="card"><h2>Structured Handoff</h2><div class="meta-grid"><div class="meta"><div class="k">Decision</div><div class="v">'+esc(decision?decision.type:"—")+'</div></div><div class="meta"><div class="k">Related existing course</div><div class="v">'+esc(courseName(handoff.relatedCourseId))+'</div></div><div class="meta"><div class="k">Target audience</div><div class="v">'+esc(handoff.targetAudience.join(", "))+'</div></div><div class="meta"><div class="k">Handoff date</div><div class="v">'+fmtDate(handoff.createdAt)+'</div></div><div class="meta"><div class="k">Design unit status</div><div class="v">'+esc(handoff.status)+'</div></div><div class="meta"><div class="k">Received at</div><div class="v">'+fmtDate(handoff.receivedAt)+'</div></div></div>'+
    '<h3 style="margin-top:14px">Expected learning / development area</h3><p>'+esc(handoff.expectedOutcome)+'</p><h3>Evidence Summary</h3><p>'+esc(handoff.evidenceSummary)+'</p></section>'+
    '<aside class="card"><h2>Source Mix</h2>'+barList(Object.keys(mix).map(function(source){return {label:(SOURCE_META[source]||SOURCE_META.Other).short,value:mix[source]}}),Math.max.apply(null,Object.values(mix)))+'<h3 style="margin-top:14px">Representative Signals</h3><div class="quote-list">'+reps.map(function(s){return '<div class="quote">“'+originalText(s.rawText)+'”<div class="caption">'+esc((SOURCE_META[s.sourceType]||SOURCE_META.Other).short)+' · '+(s.anonymous?"Anonymous":"Role context")+'</div></div>'}).join("")+'</div></aside></div>'+
    '<section class="card" style="margin-top:14px"><h2>Traceable Lineage</h2><div class="lineage"><div class="lineage-box"><div class="kind">Learning Signals</div><div class="title">'+ev.signals.length+' evidence records</div><div class="caption">'+ev.sourceCount+' source types</div></div><div class="lineage-arrow">→</div><div class="lineage-box"><div class="kind">Source Need</div><div class="title"><button class="link-btn" data-need-id="'+need.id+'">'+need.id+' · '+esc(need.title)+'</button></div><div class="caption">'+esc(need.summary)+'</div></div><div class="lineage-arrow">→</div><div class="lineage-box"><div class="kind">Human Decision</div><div class="title">'+esc(decision?decision.id:"—")+' · '+esc(decision?decision.type:"—")+'</div><div class="caption">'+esc(decision?decision.rationale:"—")+'</div></div><div class="lineage-arrow">→</div><div class="lineage-box"><div class="kind">Design Handoff</div><div class="title">'+handoff.id+'</div><div class="caption">'+esc(handoff.status)+'</div></div></div></section>'+
    '<div class="notice warning" style="margin-top:14px"><strong>Bu sistem eğitim tasarımını yapmaz.</strong> Öğrenme hedefi, modül yapısı, yöntem, değerlendirme veya onay zinciri üretmez; yalnızca doğrulanmış ihtiyaç kanıtını tasarım birimine taşır.</div>'
}

function renderRoadmap(){
  $("#appView").innerHTML=pageHead("MVP Scope & Roadmap","Çalışan dikey kesit ile future enhancement alanlarını birbirinden net biçimde ayırın.")+
    '<div class="roadmap"><article class="card now"><div class="eyebrow">Now · MVP Proof</div><h2>Signal → Need</h2><p>Ortak Learning Signal modeli, survey coverage, akıllı öneri ve mixed-source Need.</p></article><article class="card now"><div class="eyebrow">Now · MVP Proof</div><h2>Decision → Handoff</h2><p>Existing coverage analizi, rationale ile insan kararı ve yapılandırılmış tasarım brief’i.</p></article><article class="card"><div class="eyebrow">Future Enhancement</div><h2>Real Integrations</h2><p>Survey, HR, LMS ve dış öğrenme platformu bağlantıları; bu demoda aktif değildir.</p></article><article class="card"><div class="eyebrow">Future Enhancement</div><h2>Competency Context</h2><p>Doğrulanmış yetkinlik çerçevesi oluştuğunda yeni sinyal kaynağı; kişi verdict’i değildir.</p></article><article class="card"><div class="eyebrow">Future Enhancement</div><h2>Advanced AI</h2><p>Gelişmiş benzerlik, özetleme ve routing desteği; human decision yerine geçmez.</p></article><article class="card"><div class="eyebrow">Future Enhancement</div><h2>Industry Benchmark</h2><p>Benzer sektörlerdeki model araştırması; gerçek şirket verisi veya sahte benchmark score içermez.</p></article><article class="card"><div class="eyebrow">Future Enhancement</div><h2>Learning Assistant</h2><p>Keşif ve etkileşim sinyali; ana MVP değerini chatbot’a indirgemez.</p></article><article class="card"><div class="eyebrow">Future Enhancement</div><h2>Design Intelligence</h2><p>Tasarım birimiyle süreç doğrulandıktan sonra değerlendirilecek; bu MVP eğitim tasarlamaz.</p></article></div>'
}

/* ---------------- REAL AI REQUEST FLOW ---------------- */
function paintDocumentIndex(){
  var node=$("#documentIndexNotice");if(!node)return;
  var report=DOC_INDEX.report,progress=report&&report.progress||{};
  var labels={ready:"Aramada hazır",pending:"İşlenmeyi bekliyor",error:"İşlenemedi"};
  var busy=DOC_INDEX.syncing||progress.running;
  var wasOpen=!!node.querySelector('details[open]');
  var files=report?(report.documents||[]).filter(function(file){return file.status!=="missing"}):[];
  var total=report&&(report.documents_total??files.length)||0,offset=report&&report.offset||0,limit=report&&report.limit||20;
  node.className="notice "+(DOC_INDEX.error||report&&!report.complete&&!busy?"warning":"");
  node.innerHTML='<div class="inline-actions"><strong>PDF bilgi kaynağı · Test paneli</strong><button type="button" class="btn sm" data-action="sync-documents" '+(busy||LIVE_REQUEST.busy?'disabled':'')+'>'+(busy?'Klasör eşitleniyor…':'PDF klasörünü eşitle')+'</button></div>'+
    '<p class="caption">Bu dosya listesi geliştirme ve test içindir; son kullanıcı ekranının parçası olmayacaktır.</p>'+
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

/* ---------------- MODALS ---------------- */
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
function openSignalDetail(signalId){
  var signal=DemoDB.findById("learningSignals",signalId);if(!signal)return;
  state.selectedSignalId=signalId;saveState();
  var linked=signal.linkedNeedIds.map(function(id){var n=DemoDB.findById("needs",id);return n?id+" · "+n.title:id}).join(", ")||"Not linked";
  openModal('<div class="modal-head"><div><h2>'+signal.id+' — Learning Signal</h2><div class="subtle">Ortak sinyal modeli ve ilişki görünümü</div></div><button class="close" data-action="close-modal" aria-label="Pencereyi kapat">✕</button></div>'+
    '<div class="tags">'+sourceBadge(signal.sourceType)+badge(signal.status)+badge(signal.anonymous?"Anonymous / Aggregate":"Role Context")+'</div><h3 style="margin-top:14px">Original / Representative text</h3><p>'+originalText(signal.rawText)+'</p>'+
    '<div class="meta-grid"><div class="meta"><div class="k">Signal Type</div><div class="v">'+esc(signal.signalType)+'</div></div><div class="meta"><div class="k">Organization</div><div class="v">'+esc(orgName(signal.organizationId))+'</div></div><div class="meta"><div class="k">System Suggestion</div><div class="v">'+esc(signal.suggestedCluster||signal.topicHint||"—")+'</div></div><div class="meta"><div class="k">Confidence</div><div class="v">'+(signal.suggestionConfidence?signal.suggestionConfidence+"%":"—")+'</div></div><div class="meta"><div class="k">Linked Need</div><div class="v">'+esc(linked)+'</div></div><div class="meta"><div class="k">Request Link</div><div class="v">'+esc(signal.requestId||"—")+'</div></div></div>'+
    '<div class="notice" style="margin-top:12px"><strong>Privacy:</strong> Survey response’larda isim tutulmaz. Bu ekran performans değerlendirmesi üretmez.</div>'+
    '<div class="field" style="margin-top:13px"><label for="signalNeedSelect">Need’e bağla</label><select id="signalNeedSelect">'+state.needs.map(function(n){return '<option value="'+n.id+'" '+(signal.suggestedNeedId===n.id?"selected":"")+'>'+n.id+' · '+esc(n.title)+'</option>'}).join("")+'</select></div>'+
    '<div class="form-actions"><button class="btn" data-action="close-modal">Kapat</button><button class="btn primary" data-action="confirm-signal-link" data-signal="'+signal.id+'">Signal → Need bağla</button></div>')
}
function openDecisionModal(needId){
  var need=DemoDB.findById("needs",needId),decision=need&&need.decisionId?DemoDB.findById("decisions",need.decisionId):null;
  if(!need)return;
  openModal('<div class="modal-head"><div><h2>Human Decision</h2><div class="subtle">'+need.id+' · '+esc(need.title)+'</div></div><button class="close" data-action="close-modal" aria-label="Pencereyi kapat">✕</button></div>'+
    '<form id="decisionForm" data-need="'+need.id+'"><div class="field"><label for="decisionType">Decision *</label><select id="decisionType" name="type"><option value="USE_EXISTING" '+(decision&&decision.type==="USE_EXISTING"?"selected":"")+'>Use Existing</option><option value="REVISE_EXISTING" '+(!decision||decision.type==="REVISE_EXISTING"?"selected":"")+'>Revise Existing</option><option value="CREATE_NEW" '+(decision&&decision.type==="CREATE_NEW"?"selected":"")+'>Create New</option><option value="NON_TRAINING" '+(decision&&decision.type==="NON_TRAINING"?"selected":"")+'>Non-training</option><option value="DEFER">Defer</option><option value="REJECT">Reject</option></select></div>'+
    '<div class="field"><label for="decisionCourse">Related Course</label><select id="decisionCourse" name="course"><option value="">İlgili eğitim yok</option>'+state.courses.map(function(c){return '<option value="'+c.id+'" '+((decision&&decision.relatedCourseId===c.id)||(!decision&&c.id==="CRS-003")?"selected":"")+'>'+esc(c.title)+' · '+esc(c.level)+'</option>'}).join("")+'</select></div>'+
    '<div class="field"><label for="decisionRationale">Rationale *</label><textarea id="decisionRationale" name="rationale" required>'+esc(decision?decision.rationale:"Mevcut eğitim başlangıç seviyesinde kalıyor. Farklı kaynaklardan gelen sinyaller dashboard tasarımı ve ileri raporlama seviyesinde yoğunlaşıyor.")+'</textarea></div>'+
    '<div class="meta-grid"><div class="meta"><div class="k">Decision Date</div><div class="v">'+fmtDate(new Date().toISOString())+'</div></div><div class="meta"><div class="k">Decision Maker</div><div class="v">Demo Analist</div></div><div class="meta" style="grid-column:1/-1"><div class="k">Evidence Summary</div><div class="v">'+esc(evidenceSummaryText(need))+'</div></div></div>'+
    '<div class="notice warning" style="margin-top:12px">REVISE veya CREATE kararı, Eğitim Tasarım Birimi için yapılandırılmış handoff oluşturur/günceller. Sistem eğitimi tasarlamaz.</div>'+
    '<div class="form-actions" style="margin-top:14px"><button class="btn" type="button" data-action="close-modal">Vazgeç</button><button class="btn primary" type="submit">Gerekçeli kararı kaydet</button></div></form>');
  $("#decisionForm").addEventListener("submit",function(e){
    e.preventDefault();var form=new FormData(e.target),rationale=String(form.get("rationale")||"").trim();
    if(!rationale){toast("Rationale zorunludur.");return}
    var saved=recordHumanDecision({needId:need.id,type:form.get("type"),relatedCourseId:form.get("course")||null,rationale:rationale});
    if(saved){closeModal();toast("Human decision ve ilişkili lineage kaydedildi.");renderNeedDetail()}
  })
}
function openClusterModal(signalId){
  var signal=DemoDB.findById("learningSignals",signalId);if(!signal)return;
  openModal('<div class="modal-head"><div><h2>Cluster değiştir</h2><div class="subtle">'+signal.id+' · Human review</div></div><button class="close" data-action="close-modal">✕</button></div><p>“'+originalText(signal.rawText)+'”</p><div class="field"><label for="clusterSelect">Human-selected Cluster</label><select id="clusterSelect">'+CLUSTERS.map(function(cluster){return '<option '+(signal.suggestedCluster===cluster?"selected":"")+'>'+esc(cluster)+'</option>'}).join("")+'</select></div><div class="form-actions"><button class="btn" data-action="close-modal">Vazgeç</button><button class="btn primary" data-action="confirm-cluster" data-signal="'+signal.id+'">Değişikliği kaydet</button></div>')
}
function openRequestDetail(requestId){
  var request=DemoDB.findById("requests",requestId),signal=request?DemoDB.findById("learningSignals",request.signalId):null;if(!request)return;
  openModal('<div class="modal-head"><div><h2>'+request.id+' — Talebim</h2><div class="subtle">Kendi talep ve sinyal bağlantınız</div></div><button class="close" data-action="close-modal">✕</button></div><div class="tags">'+badge(request.status)+(request.issueFlag?badge("Critical Fast Lane"):"")+'</div><h3 style="margin-top:14px">'+esc(request.title)+'</h3><p>'+originalText(request.description)+'</p><div class="meta-grid"><div class="meta"><div class="k">Learning Signal</div><div class="v">'+esc(request.signalId)+'</div></div><div class="meta"><div class="k">Need</div><div class="v">'+esc(request.needId||"Henüz bağlanmadı")+'</div></div><div class="meta"><div class="k">Related Course</div><div class="v">'+esc(courseName(request.relatedCourseId))+'</div></div><div class="meta"><div class="k">Signal Status</div><div class="v">'+esc(signal?signal.status:"—")+'</div></div></div><div class="notice" style="margin-top:12px">Gizli analist notları ve başka kişilerin kayıtları bu görünümde gösterilmez.</div><div class="form-actions" style="margin-top:13px"><button class="btn" data-action="close-modal">Kapat</button></div>')
}
function openCourseFeedbackModal(courseId){
  var course=DemoDB.findById("courses",courseId);if(!course)return;
  openModal('<div class="modal-head"><div><h2>Eğitim Geri Bildirimi</h2><div class="subtle">'+esc(course.title)+'</div></div><button class="close" data-action="close-modal">✕</button></div><form id="feedbackForm" data-course="'+course.id+'"><div class="field"><label for="feedbackText">Geri bildiriminiz *</label><textarea id="feedbackText" required>Temel içerik faydalıydı ancak ileri dashboard ihtiyacını karşılamadı.</textarea></div><div class="form-actions"><button class="btn" type="button" data-action="close-modal">Vazgeç</button><button class="btn primary" type="submit">Learning Signal oluştur</button></div></form>');
  $("#feedbackForm").addEventListener("submit",function(e){e.preventDefault();var text=$("#feedbackText").value.trim();if(!text)return;var needId=course.topic==="Veri Analitiği ve Raporlama"?"NEED-0028":null;captureLearningSignal({signalType:"COURSE_FEEDBACK",sourceType:"Course Feedback",rawText:text,summary:text,organizationId:"ORG-01",personRole:"Çalışan",relatedCourseId:course.id,needId:needId,status:needId?"LINKED":"CAPTURED"});closeModal();toast("Course Feedback yeni Learning Signal olarak kaydedildi.");renderCatalog()})
}

/* ---------------- EVENT HANDLERS ---------------- */
function resetPresentationScenario(){
  var fresh=buildInitialState();
  fresh.learningSignals.filter(function(s){return s.openText}).forEach(function(seedSignal){
    var current=DemoDB.findById("learningSignals",seedSignal.id);
    if(current){
      current.topicHint=seedSignal.topicHint;current.suggestedCluster=seedSignal.suggestedCluster;
      current.suggestionConfidence=seedSignal.suggestionConfidence;current.humanStatus=seedSignal.humanStatus;
      current.status=seedSignal.status
    }
  });
  var freshNeed=fresh.needs.find(function(n){return n.id==="NEED-0028"}),currentNeed=DemoDB.findById("needs","NEED-0028");
  if(currentNeed&&freshNeed)Object.assign(currentNeed,clone(freshNeed));
  var freshDecision=fresh.decisions.find(function(d){return d.id==="DCS-2026-0008"}),decisionIndex=state.decisions.findIndex(function(d){return d.id==="DCS-2026-0008"});
  if(decisionIndex>-1)state.decisions[decisionIndex]=clone(freshDecision);else state.decisions.push(clone(freshDecision));
  var freshHandoff=fresh.handoffs.find(function(h){return h.id==="HND-2026-0008"}),handoffIndex=state.handoffs.findIndex(function(h){return h.id==="HND-2026-0008"});
  if(handoffIndex>-1)state.handoffs[handoffIndex]=clone(freshHandoff);else state.handoffs.push(clone(freshHandoff));
  state.surveyCampaigns[0]=clone(fresh.surveyCampaigns[0]);
  fresh.learningSignals.filter(function(s){return s.riskLevel==="Critical"}).forEach(function(seedSignal){
    var current=DemoDB.findById("learningSignals",seedSignal.id);if(current){current.status=seedSignal.status;current.riskLevel=seedSignal.riskLevel}
  });
  state.analysisRunAt=null;state.analysisRunCount=0;state.analysisFilter="ALL";state.needSignalFilter="All";
  DemoDB.audit("Presentation scenario reset","MVP-DEMO-STORY","Changed demo state","Seed scenario");
  saveState();toast("Ana sunum senaryosu başlangıç durumuna getirildi.");render()
}

document.addEventListener("click",function(event){
  var pageButton=event.target.closest("[data-page]");
  if(pageButton){
    if(pageButton.dataset.page==='admin-panel'&&typeof PORTAL!=='undefined'){PORTAL.adminTab='requests';PORTAL.filter='';PORTAL.search='';PORTAL.offset=0}
    state.currentPage=pageButton.dataset.page;saveState();render();setMobileMenu(false);$("#appView").focus({preventScroll:true});window.scrollTo({top:0,behavior:"auto"});return
  }
  var demoTarget=event.target.closest("[data-demo-target]");
  if(demoTarget){
    var target=demoTarget.dataset.demoTarget;
    if(target.indexOf("need:")===0){state.selectedNeedId=target.split(":")[1];state.currentPage="need-detail"}
    else if(target.indexOf("handoff:")===0){state.selectedHandoffId=target.split(":")[1];state.currentRole="designer";state.currentPage="handoff-detail"}
    else{state.currentPage=target;if(target==="signals"||target==="open-analysis")state.currentRole="analyst"}
    saveState();render();focusPageStart();return
  }
  var actionButton=event.target.closest("[data-action]");
  if(actionButton){
    var action=actionButton.dataset.action;
    if(action==="retry-ai"){checkAIHealth(true);return}
    if(action==="documents-prev"||action==="documents-next"){
      DOC_INDEX.offset=Math.max(0,DOC_INDEX.offset+(action==="documents-next"?20:-20));
      loadDocumentStatus().catch(function(error){DOC_INDEX.error=error.message;paintDocumentIndex()});return;
    }
    if(action==="sync-documents"){ensureDocumentIndex().then(function(){toast('PDF klasörü güncel. Yeni analizler yalnızca hazır dosyaları kullanacak.')}).catch(function(error){toast(error.message)});return}
    if(action==="close-modal"){closeModal();return}
    if(action==="presentation-mode"){state.currentRole="executive";state.currentPage="guided-demo";saveState();render();return}
    if(action==="reset-demo"){
      if(confirm("Yerel demo değişiklikleri silinsin ve sentetik başlangıç verisi geri yüklensin mi?")){
        localStorage.removeItem(CONFIG.storageKey);state=buildInitialState();saveState();toast("Tüm demo verisi sıfırlandı.");render()
      }
      return
    }
    if(action==="scenario-reset"){
      if(confirm("Ana sunum senaryosu başlangıç durumuna getirilsin mi?"))resetPresentationScenario();
      return
    }
    if(action==="run-analysis"){
      actionButton.disabled=true;actionButton.innerHTML='<span class="spinner"></span>Analysing…';
      setTimeout(function(){runOpenTextAnalysis();toast("Akıllı sınıflandırma önerileri yenilendi; human review bekleniyor.");renderOpenAnalysis()},CONFIG.simulatedDelay);
      return
    }
    if(action==="accept-cluster"){acceptClusterSuggestion(actionButton.dataset.signal);toast("Suggestion insan tarafından kabul edildi.");renderOpenAnalysis();return}
    if(action==="change-cluster"){openClusterModal(actionButton.dataset.signal);return}
    if(action==="leave-unclassified"){leaveUnclassified(actionButton.dataset.signal);toast("Signal unclassified bırakıldı.");renderOpenAnalysis();return}
    if(action==="confirm-cluster"){acceptClusterSuggestion(actionButton.dataset.signal,$("#clusterSelect").value);closeModal();toast("Human-selected cluster kaydedildi.");renderOpenAnalysis();return}
    if(action==="plan-reminder"){scheduleSurveyReminder(actionButton.dataset.org);toast("Demo hatırlatma aksiyonu kaydedildi; gerçek e-posta gönderilmedi.");renderSurveyCoverage();return}
    if(action==="confirm-signal-link"){
      var signalId=actionButton.dataset.signal,needId=$("#signalNeedSelect").value;
      DemoDB.link(signalId,needId);closeModal();toast(signalId+" → "+needId+" bağlandı.");render();return
    }
    if(action==="open-decision"){openDecisionModal(actionButton.dataset.need);return}
    if(action==="print"){window.print();return}
    if(action==="open-critical"){
      var criticalSignal=DemoDB.findById("learningSignals",actionButton.dataset.signal);
      if(criticalSignal){var before=criticalSignal.status;criticalSignal.status="IMMEDIATE_REVIEW";DemoDB.audit("Critical review opened",criticalSignal.id,before,criticalSignal.status);saveState();toast("Immediate Review fast lane açıldı.");renderCritical()}
      return
    }
    if(action==="resolve-critical"){
      var resolved=DemoDB.findById("learningSignals",actionButton.dataset.signal);
      if(resolved){var old=resolved.status;resolved.status="RESOLVED";DemoDB.audit("Critical review closed",resolved.id,old,"RESOLVED");saveState();toast("Kritik inceleme human review ile kapatıldı.");renderCritical()}
      return
    }
    if(action==="search-courses"){
      var query=$("#courseDiscoveryText").value.trim();if(!query){toast("Lütfen gelişim ihtiyacınızı yazın.");return}
      renderCourseDiscoveryResults(query);return
    }
    if(action==="course-meets"){
      resolveWithExistingCourse(actionButton.dataset.query,actionButton.dataset.course,"RESOLVED_EXISTING_SOLUTION");
      toast("Formal request açılmadı; discovery signal existing solution ile çözüldü.");
      $("#courseDiscoveryResults").innerHTML='<div class="notice success"><strong>Existing solution selected.</strong> Formal request oluşturulmadı. Learning Signal, RESOLVED_EXISTING_SOLUTION sonucu ve ilgili course ID ile kaydedildi.</div>';return
    }
    if(action==="course-insufficient"){
      resolveWithExistingCourse(actionButton.dataset.query,actionButton.dataset.course,"COVERAGE_PROBLEM");
      toast("Coverage problem Learning Signal olarak analiz backlog’una kaydedildi.");
      $("#courseDiscoveryResults").innerHTML='<div class="notice warning"><strong>Coverage problem captured.</strong> Existing course bulundu; ancak içerik/seviye yetersizliği yeni Learning Signal olarak NEED-0028 kanıtına bağlandı.</div>';return
    }
    if(action==="course-feedback"){openCourseFeedbackModal(actionButton.dataset.course);return}
    if(action==="receive-handoff"){receiveHandoff(actionButton.dataset.handoff);toast("Handoff Eğitim Tasarım Birimi tarafından teslim alındı.");renderHandoffDetail();return}
  }
  var filterButton=event.target.closest("[data-analysis-filter]");
  if(filterButton){state.analysisFilter=filterButton.dataset.analysisFilter;saveState();renderOpenAnalysis();return}
  var needFilter=event.target.closest("[data-need-filter]");
  if(needFilter){state.needSignalFilter=needFilter.dataset.needFilter;saveState();renderNeedDetail();return}
  var needButton=event.target.closest("[data-need-id]");
  if(needButton){state.selectedNeedId=needButton.dataset.needId;state.currentPage="need-detail";saveState();render();focusPageStart();return}
  var handoffButton=event.target.closest("[data-handoff-id]");
  if(handoffButton){state.selectedHandoffId=handoffButton.dataset.handoffId;state.currentPage="handoff-detail";saveState();render();focusPageStart();return}
  var signalButton=event.target.closest("[data-signal-id]");
  if(signalButton){openSignalDetail(signalButton.dataset.signalId);return}
  var requestButton=event.target.closest("[data-request-id]");
  if(requestButton){openRequestDetail(requestButton.dataset.requestId);return}
});

document.addEventListener("change",function(event){
  var priority=event.target.closest("[data-need-priority]");
  if(priority){
    var need=DemoDB.findById("needs",priority.dataset.needPriority);
    if(need){var before=need.humanPriority;need.humanPriority=priority.value;DemoDB.audit("Human priority updated",need.id,before,priority.value);saveState();toast("Human Priority güncellendi.");renderNeedDetail()}
  }
});
$("#roleSelect").addEventListener("change",function(event){
  state.currentRole=event.target.value;state.currentPage=defaultPage(state.currentRole);saveState();render();setMobileMenu(false);window.scrollTo({top:0,behavior:"auto"})
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

/* ---------------- INIT ---------------- */
document.addEventListener('DOMContentLoaded',function(){
  state=loadState();state.currentRole='submitter';state.currentPage='submitter-home';
  initPortal();
});

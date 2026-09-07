const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.join(__dirname,'..');
const app=fs.readFileSync(path.join(root,'app/static/js/app.js'),'utf8');
const portal=fs.readFileSync(path.join(root,'app/static/js/portal.js'),'utf8');
const tr=fs.readFileSync(path.join(root,'app/static/js/i18n-tr.js'),'utf8');
const context=vm.createContext({
  document:{readyState:'loading',addEventListener(){}},
  MutationObserver:class{observe(){} disconnect(){}},
  Node:{TEXT_NODE:3,ELEMENT_NODE:1},HTMLInputElement:class{},
});
vm.runInContext(tr.replace(/\}\)\(\);\s*$/, 'globalThis.translateString=translateString;globalThis.translateNode=translateNode;})();'),context);
vm.runInContext(app.slice(app.indexOf('/* ---------------- SELECTORS / FORMATTERS'),app.indexOf('/* ---------------- ROUTING')),context);
vm.runInContext(portal.slice(portal.indexOf('var WORKFLOW_LABELS='),portal.indexOf('function portalMode(')),context);
vm.runInContext(portal.slice(portal.indexOf('function fitNumber('),portal.indexOf('function portalEmpty(')),context);
vm.runInContext(portal.slice(portal.indexOf('function renderFitDetails('),portal.indexOf('async function ensurePortalIndex(')),context);

test('record identifiers remain unchanged while interface text is translated',()=>{
  const result=context.translateString('Linked Need: NEED-0028 · SIG-2026-0012 · REQ-2026-0001');
  for(const id of ['NEED-0028','SIG-2026-0012','REQ-2026-0001'])assert.ok(result.includes(id));
});
test('long phrases are translated before their shorter fragments',()=>{
  assert.equal(context.translateString('Human decision remains final'),'Nihai karar insana aittir');
});
test('complete status tokens reach the localization layer',()=>{
  assert.ok(context.badge('IMMEDIATE_REVIEW').includes('IMMEDIATE_REVIEW'));
  assert.equal(context.translateString('IMMEDIATE_REVIEW'),'ACİL İNCELEME');
  assert.equal(context.translateString('RECEIVED_BY_DESIGN'),'TASARIM BİRİMİ TESLİM ALDI');
});
test('raw content is escaped and excluded from interface translation',()=>{
  assert.equal(context.originalText('<script>Need</script>'),'<span data-no-translate>&lt;script&gt;Need&lt;/script&gt;</span>');
  const node={nodeType:3,nodeValue:'Need',parentElement:{closest:()=>true}};
  context.translateNode(node);assert.equal(node.nodeValue,'Need');
});
test('translated option label does not change its implicit submitted value',()=>{
  const attributes={};
  const option={nodeType:1,tagName:'OPTION',textContent:'High',closest:()=>null,hasAttribute:k=>k in attributes,setAttribute:(k,v)=>attributes[k]=v,childNodes:[]};
  const child={nodeType:3,nodeValue:'High',parentElement:option};option.childNodes.push(child);
  context.translateNode(option);
  assert.equal(attributes.value,'High');assert.equal(child.nodeValue,'Yüksek');
});
test('zero-length chart values do not create a misleading visible bar',()=>{
  assert.ok(context.barList([{label:'Zero',value:0}],100).includes('width:0%'));
  assert.ok(context.barList([{label:'Limit',value:200}],100).includes('width:100%'));
});
test('employee result shows explained fit percentages and summaries, never page excerpts or raw scores',()=>{
  const html=context.renderEmployeeResult({request_id:7,classification:{category:'Data',subcategory:'Excel'},coverage:{fit_percent:91,reason:'<b>test</b>'},courses:[{course_code:'PRIVATE_CODE',course_name:'Test',score:0.1113,fit:{percent:91,summary:'<script>alert(1)</script>',topics:['Power Query'],components:{need_coverage:70,content_relevance:15,semantic_similarity:6}},evidence:[{page_number:2,content:'PRIVATE EXCERPT'}]}]});
  assert.ok(html.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));
  assert.ok(html.includes('%91'));
  assert.ok(html.includes('Power Query'));
  assert.ok(html.includes('Uyum oranı nasıl hesaplandı?'));
  for(const value of ['Sayfa 2','PRIVATE_CODE','PRIVATE EXCERPT','0.1113','<script>'])assert.ok(!html.includes(value));
  assert.ok(html.includes('doğruluk veya başarı garantisi değildir'));
});

test('employee request uses the full form width and has no developer or guidance sidebar',()=>{
  const code=portal.slice(portal.indexOf('function renderPortalRequest('),portal.indexOf('function renderFitDetails('));
  assert.ok(code.includes('portal-request-form'));
  assert.ok(!code.includes('request-help'));
  assert.ok(!code.includes('documentIndexNotice'));
  assert.ok(!code.includes('İyi bir analiz için'));
  assert.ok(code.includes('portal-requests'));
});

test('fit display clamps nonfinite or out-of-range values',()=>{
  assert.equal(context.fitNumber(NaN),0);
  assert.equal(context.fitNumber(120),100);
  assert.equal(context.fitNumber(-1),0);
  assert.equal(context.fitNumber(83.5),84);
});

test('fit breakdown preserves decimal points and explains final rounding',()=>{
  const html=context.renderFitDetails({components:{need_coverage:46.7,content_relevance:5.9,semantic_similarity:5.4}});
  assert.ok(html.includes('46,7 / 70 puan'));
  assert.ok(html.includes('5,9 / 20 puan'));
  assert.ok(html.includes('Toplam, tam yüzdeye yuvarlanır'));
});

test('an unsupported request explicitly shows zero catalog fit without inventing a course',()=>{
  const html=context.renderEmployeeResult({request_id:8,coverage:{fit_percent:0},courses:[]});
  assert.ok(html.includes('Katalog uyumu <strong>%0</strong>'));
  assert.ok(!html.includes('course-fit-card'));
});

test('navigation separates authenticated employee and manager workspaces',()=>{
  const shell=portal.slice(portal.indexOf('function renderPortalShell('),portal.indexOf('function renderPortalRoute('));
  assert.ok(shell.includes("var nav=admin?"));
  assert.ok(shell.includes('account-logout'));
  assert.ok(shell.includes('Çözüme Ulaşanlar'));
});

test('login uses username and password and never asks users to choose their own role',()=>{
  const wiring=portal.slice(portal.indexOf('function renderPortalLogin('),portal.indexOf('function renderPortalShell('));
  const experience=fs.readFileSync(path.join(root,'app/static/js/experience.js'),'utf8');
  const login=experience.slice(experience.indexOf('function renderExperienceLogin('),experience.indexOf('function setSoundButton('));
  assert.ok(wiring.includes('renderExperienceLogin'));
  assert.ok(login.includes('accountUsername'));
  assert.ok(login.includes('accountPassword'));
  assert.ok(wiring.includes('/api/auth/login'));
  assert.ok(!login.includes('<select'));
  assert.ok(!login.includes('1234'));
});

test('changing status immediately applies the current filter and resets pagination',()=>{
  const listeners={},calls=[];
  const nodes={
    '#portalListFilters':{addEventListener:(name,fn)=>listeners['form:'+name]=fn},
    '#portalStatus':{value:'REFERRED',addEventListener:(name,fn)=>listeners['status:'+name]=fn},
    '#portalSearch':{value:'C++',addEventListener:(name,fn)=>listeners['search:'+name]=fn},
  };
  const c=vm.createContext({PORTAL:{epoch:2,offset:40},$:(key)=>nodes[key],clearTimeout,setTimeout,portalSaveFilters(){},loadPortalList:(admin)=>calls.push(admin)});
  vm.runInContext(portal.slice(portal.indexOf('function bindListFilters('),portal.indexOf('async function loadPortalList(')),c);
  c.bindListFilters(true);listeners['status:change']();
  assert.equal(c.PORTAL.filter,'REFERRED');assert.equal(c.PORTAL.search,'C++');assert.equal(c.PORTAL.offset,0);assert.deepEqual(calls,[true]);
  nodes['#portalStatus'].value='RESOLVED';listeners['form:submit']({preventDefault(){}});
  assert.equal(c.PORTAL.filter,'RESOLVED');
});

test('out-of-order filter responses cannot replace the newest visible results',async()=>{
  const pending=[],nodes={'#portalListContent':{innerHTML:'',setAttribute(){}},'#portalListStats':{innerHTML:''}};
  const c=vm.createContext({PORTAL:{epoch:1,listRevision:0,offset:0,filter:'',search:''},$:(key)=>nodes[key],
    apiRequest:()=>new Promise(resolve=>pending.push(resolve)),portalRequestRows:(items)=>items[0].name,portalStats:()=>'',portalQueueControls:()=>{},encodeURIComponent,document:{querySelectorAll:()=>[]}});
  vm.runInContext(portal.slice(portal.indexOf('async function loadPortalList('),portal.indexOf('function renderPortalList(')),c);
  const first=c.loadPortalList(true);c.PORTAL.filter='RESOLVED';const second=c.loadPortalList(true);
  const data=(name)=>({items:[{name}],total:1,offset:0,limit:20,summary:{}});
  pending[1](data('NEW'));await second;pending[0](data('OLD'));await first;
  assert.ok(nodes['#portalListContent'].innerHTML.includes('NEW'));assert.ok(!nodes['#portalListContent'].innerHTML.includes('OLD'));
});

test('account changes invalidate pending request results and erase private UI state',()=>{
  const clear=portal.slice(portal.indexOf('function clearPortalAccount('),portal.indexOf('function portalSessionExpired('));
  assert.ok(clear.includes('PORTAL.accountGeneration++'));
  assert.ok(clear.includes("LIVE_REQUEST.text=''"));
  const submit=portal.slice(portal.indexOf('function bindPortalRequest('),portal.indexOf('function renderListControls('));
  assert.ok(submit.includes('generation!==PORTAL.accountGeneration'));
});

test('unknown route has one inline target choice while a resolved route hides that choice',()=>{
  const c=livePortalContext();
  const request={request_id:3,status:'IN_REVIEW',permissions:{can_refer:true},classification:{},decision_support:{action:'NEW_COURSE'}};
  const unknown=c.portalReviewEditor(request);
  assert.ok(unknown.includes('id="decisionRoutingChoice" >'));
  assert.ok(unknown.includes('<option value="TECHNICAL_DESIGN"'));
  assert.ok(unknown.includes('<option value="ENGINEERING_DESIGN"'));
  const known=c.portalReviewEditor({...request,routing:{resolved:true,requires_selection:false,department:'TECHNICAL_DESIGN',department_label:'Teknik Eğitim Tasarım Şefliği',options:[]}});
  assert.ok(known.includes('id="decisionRoutingChoice" hidden'));
  assert.ok(known.includes('Talebi onayla ve ilerlet'));
  assert.ok(!known.includes('portalReferralForm'));
});
test('canonical brand colors and locally served assets are configured',()=>{
  const css=fs.readFileSync(path.join(root,'app/static/css/platform.css'),'utf8').toLowerCase();
  for(const color of ['#263685','#dd140e','#4d4d4d','#f8f7f7','#d29f13','#1e1a34','#222223'])assert.ok(css.includes(color));
  const shell=fs.readFileSync(path.join(root,'app/static/index_tusas_faz31.html'),'utf8');
  assert.ok(!shell.includes('base64,'));assert.ok(!shell.includes('TUSAS_PHASE31'));
  assert.ok(!css.includes('https://'));assert.ok(shell.includes('aria-controls="sidebar"'));
});

function networkContext(fetch){
  const nodes={
    '#aiConnectionBadge':{},'#aiAvailabilityNotice':{},'#submitterAnalyzeButton':{},
    '#documentIndexNotice':{querySelector(){return null}},
  };
  const c=vm.createContext({fetch,AbortController,setTimeout,clearTimeout,Date,
    LIVE_AI:{status:'connected',message:'Ready'},LIVE_REQUEST:{busy:false},
    DOC_INDEX:{error:'',syncing:false},$:(selector)=>nodes[selector],
    esc:(value)=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'),
  });
  vm.runInContext(app.slice(app.indexOf('async function apiRequest('),app.indexOf('function pageHead(')),c);
  vm.runInContext(app.slice(app.indexOf('function paintDocumentIndex('),app.indexOf('async function loadDocumentStatus(')),c);
  return {c,nodes};
}

test('quota response replaces the green badge and preserves an actionable error',async()=>{
  const {c,nodes}=networkContext(async()=>({ok:false,status:429,json:async()=>({
    detail:'Günlük kota doldu.',ai_status:'quota',error_code:'AI_DAILY_QUOTA_EXCEEDED',
    quota_limit:50,quota_remaining:0,retry_at:'2026-09-05T00:00:00+00:00',
  })}));
  await assert.rejects(c.apiRequest('/api/requests/analyze'),error=>{
    assert.equal(error.code,'AI_DAILY_QUOTA_EXCEEDED');
    assert.ok(error.message.includes('03:00:00'));return true;
  });
  assert.equal(c.LIVE_AI.status,'quota');
  assert.equal(nodes['#aiConnectionBadge'].textContent,'YZ kullanım sınırı');
  assert.equal(nodes['#submitterAnalyzeButton'].disabled,false);
  assert.ok(nodes['#aiAvailabilityNotice'].innerHTML.includes('kalan: 0'));
});

test('service error appears once and form-only errors remain visible without losing draft',()=>{
  const {c,nodes}=networkContext();
  nodes['#submitterFormError']={innerHTML:''};
  c.LIVE_REQUEST={busy:false,text:'Preserved draft',error:'Service failure'};
  c.LIVE_AI={status:'error',message:'Service failure'};
  c.applyAIStatusToCurrentPage();
  assert.equal(nodes['#submitterFormError'].innerHTML,'');
  assert.ok(nodes['#aiAvailabilityNotice'].innerHTML.includes('Service failure'));
  assert.equal(c.LIVE_REQUEST.text,'Preserved draft');
  c.LIVE_AI={status:'connected',message:'Ready'};
  c.applyAIStatusToCurrentPage();
  assert.ok(nodes['#submitterFormError'].innerHTML.includes('Service failure'));
  c.LIVE_AI={status:'error',message:'Different failure'};
  c.applyAIStatusToCurrentPage();
  assert.ok(nodes['#submitterFormError'].innerHTML.includes('Service failure'));
});

test('actual fetch failure shows an application-server error instead of green AI',async()=>{
  const {c,nodes}=networkContext(async()=>{throw new TypeError('Failed to fetch')});
  await assert.rejects(c.apiRequest('/api/requests/analyze'),/Uygulama sunucusuna ulaşılamadı/);
  assert.equal(c.LIVE_AI.status,'server_error');
  assert.equal(nodes['#aiConnectionBadge'].textContent,'Sunucuya erişilemiyor');
});

test('provider timeout remains distinct from a browser connection failure',async()=>{
  const {c}=networkContext(async()=>({ok:false,status:504,json:async()=>({detail:'Sağlayıcı zamanında yanıt vermedi.',ai_status:'error',error_code:'AI_TIMEOUT'})}));
  await assert.rejects(c.apiRequest('/api/requests/analyze'),/Sağlayıcı zamanında/);
  assert.equal(c.LIVE_AI.status,'error');
});

test('unreadable response is not falsely labelled a network failure',async()=>{
  const {c}=networkContext(async()=>({ok:true,status:200,json:async()=>{throw new SyntaxError('Bad JSON')}}));
  await assert.rejects(c.apiRequest('/api/requests/analyze'),/Sunucu yanıtı okunamadı/);
  assert.notEqual(c.LIVE_AI.status,'server_error');
});

test('a timed-out request does not become a generic server-down message',async()=>{
  const {c}=networkContext(async()=>{const error=new Error('Aborted');error.name='AbortError';throw error});
  await assert.rejects(c.apiRequest('/api/requests/analyze'),/zaman aşımına/);
  assert.notEqual(c.LIVE_AI.status,'server_error');
});

test('knowledge sources omit deleted filenames and show pagination for a large corpus',()=>{
  const {c,nodes}=networkContext();
  c.DOC_INDEX.report={complete:true,files_on_disk:1000,ready_count:1000,pending_count:0,error_count:0,
    documents_total:1000,offset:20,limit:20,progress:{running:false},
    documents:[{file:'live.pdf',status:'ready'},{file:'deleted.pdf',status:'missing'}],
  };
  c.paintDocumentIndex();
  const html=nodes['#documentIndexNotice'].innerHTML;
  assert.ok(html.includes('Eğitim bilgi kaynakları'));
  assert.ok(html.includes('live.pdf'));
  assert.ok(!html.includes('deleted.pdf'));
  assert.ok(!html.includes('Silinmiş'));
  assert.ok(html.includes('documents-next'));
});

function livePortalContext(extra={}){
  const c=vm.createContext({document:{addEventListener(){}},esc:context.esc,navIcon:context.navIcon,kpi:context.kpi,
    LIVE_REQUEST:{text:'',busy:false,result:null,error:''},state:{currentPage:'submitter-request'},toast(){},
    ...extra});
  vm.runInContext(portal,c);return c;
}

test('40 percent catalog match becomes a new course need without a course recommendation',()=>{
  const html=context.renderEmployeeResult({request_id:21,coverage:{fit_percent:40},decision_support:{action:'NEW_COURSE'},
    courses:[{course_name:'Weak match',fit:{percent:40}}]});
  assert.ok(html.includes('Yeni eğitim ihtiyacı kaydedildi'));
  assert.ok(html.includes('%40'));
  assert.ok(!html.includes('course-fit-card'));
  assert.ok(!html.includes('Weak match'));
});

test('partial matches explain enrichment while resolved requests show their current outcome',()=>{
  const c=livePortalContext();
  assert.ok(c.portalNextStep({decision_support:{action:'ENRICH_COURSE'}}).includes('tamamlama önerisi'));
  const html=c.portalNextStep({status:'RESOLVED',decision_support:{action:'NEW_COURSE'}});
  assert.ok(html.includes('Talebiniz çözüme ulaştı'));
  assert.ok(!html.includes('Yeni eğitim ihtiyacı kaydedildi'));
});

test('human review accepts approval without a duplicate checkbox and keeps corrections separate from AI',()=>{
  const c=livePortalContext();
  const html=c.portalReviewEditor({classification:{subcategory_id:'DATA.EXCEL',subcategory:'Excel'},
    decision_support:{suggested_department:{id:'TECHNICAL_DESIGN'},missing_topics:['<script>unsafe</script>'],brief:{existing_course:{course_id:1}}},
    review_options:{courses:[{id:1,name:'<img onerror=x>'}]}});
  assert.ok(html.includes('value="APPROVED"'));assert.ok(html.includes('value="MODIFIED"'));assert.ok(html.includes('value="REJECTED"'));
  assert.ok(!html.includes('decisionTrainingConfirmed'));
  assert.ok(!html.includes('type="checkbox"'));
  assert.ok(html.includes('id="decisionCorrections" class="review-fields review-corrections" hidden'));
  assert.ok(html.includes('required minlength="10"'));
  assert.ok(html.includes('&lt;script&gt;unsafe&lt;/script&gt;'));
  assert.ok(html.includes('&lt;img onerror=x&gt;'));
  assert.ok(!html.includes('<script>'));
});

test('decision history compares original AI and human judgment without exposing audit excerpts',()=>{
  const c=livePortalContext();
  const html=c.portalDecisionHistory({review_options:{courses:[]},decisions:[{outcome:'REJECTED',reason:'<b>Yanlış kapsam</b>',
    reviewer:{display_name:'Analist'},actual_category:'Veri',changed_fields:['subcategory'],original_ai:{classification:{subcategory:'Excel'},
      coverage:{fit_percent:97},courses:[],audit:{private:'RAW PDF SECRET'}}}]});
  assert.ok(html.includes('KARARA ESAS AI DEĞERLENDİRMESİ'));assert.ok(html.includes('İNSAN DEĞERLENDİRMESİ'));
  assert.ok(html.includes('&lt;b&gt;Yanlış kapsam&lt;/b&gt;'));assert.ok(html.includes('Kategori'));
  assert.ok(!html.includes('RAW PDF SECRET'));
});

test('human decision history separates operational assignment from the original AI department verdict',()=>{
  const c=livePortalContext();const html=c.portalDecisionHistory({decisions:[{outcome:'APPROVED',reason:'Kapsam doğrulandı.',actual_department:'TECHNICAL_DESIGN',training_need_confirmed:true,
    routing:{department:'ENGINEERING_DESIGN',department_label:'Mühendislik Eğitim Tasarım Şefliği'},next_status:'REFERRED'}]});
  assert.ok(html.includes('Teknik Eğitim Tasarım Şefliği'));
  assert.ok(html.includes('<strong>İşlem hedefi:</strong> Mühendislik Eğitim Tasarım Şefliği'));
});

test('learning report distinguishes an unmeasured agreement rate from zero and links source requests',()=>{
  const c=livePortalContext();
  const html=c.portalReviewReport({summary:{total_requests:3,reviewed_requests:0,pending_review:3,agreement_percent:null},
    repeated_needs:[{topic:'<b>Excel</b>',request_count:2,confirmed_count:0,request_ids:[4,5],missing_topics:['Pivot']}],learning:{}});
  assert.ok(html.includes('—'));assert.ok(html.includes('data-id="4"'));assert.ok(html.includes('&lt;b&gt;Excel&lt;/b&gt;'));
  assert.ok(html.includes('Katılım oranı, yapay zekânın doğruluk oranı değildir'));
});

test('PDF extraction preserves typed request and never submits an analysis',async()=>{
  const handlers={},calls=[];
  const nodes={
    '#requestPDFRead':{addEventListener:(_,fn)=>handlers.read=fn},
    '#requestPDFFile':{files:[{name:'need.pdf',size:50}]},
    '#requestPDFError':{innerHTML:''},
  };
  const c=livePortalContext({$:(key)=>nodes[key],FormData:class{append(){}},
    apiRequest:async(path)=>{calls.push(path);return {filename:'need.pdf',text:'PDF ihtiyacı',page_count:1}}});
  c.LIVE_REQUEST.text='Kendi açıklamam';c.renderPortalRequest=()=>{};
  c.bindPortalPDF();await handlers.read();
  assert.deepEqual(calls,['/api/requests/extract-pdf']);
  assert.equal(c.LIVE_REQUEST.text,'Kendi açıklamam');assert.equal(c.PORTAL_PDF.document.text,'PDF ihtiyacı');
  assert.equal(c.LIVE_REQUEST.result,null);
});

test('PDF append rejects combined overflow and requires an explicit append action',()=>{
  const handlers={},errors=[];
  const nodes={
    '#requestPDFRead':{addEventListener(){}},
    '#requestPDFText':{value:'PDF metni',addEventListener(){}},
    '#requestPDFInsert':{addEventListener:(_,fn)=>handlers.insert=fn},
    '#requestPDFError':{innerHTML:''},
    '#submitterRequestText':{value:'A'.repeat(4999),focus(){}},
  };
  const c=livePortalContext({$:(key)=>nodes[key]});c.renderPortalRequest=()=>{};
  c.PORTAL_PDF.document={text:'PDF metni'};c.LIVE_REQUEST.text=nodes['#submitterRequestText'].value;
  c.bindPortalPDF();handlers.insert();
  assert.equal(c.LIVE_REQUEST.text.length,4999);assert.ok(nodes['#requestPDFError'].innerHTML.includes('korundu'));
  nodes['#submitterRequestText'].value='İhtiyacım';handlers.insert();
  assert.equal(c.LIVE_REQUEST.text,'İhtiyacım\n\nPDF metni');assert.equal(c.PORTAL_PDF.document,null);
  assert.equal(c.LIVE_REQUEST.result,null);
});

test('a delayed PDF response is discarded after an account switch',async()=>{
  const handlers={};let resolve;
  const nodes={'#requestPDFRead':{addEventListener:(_,fn)=>handlers.read=fn},'#requestPDFFile':{files:[{name:'need.pdf',size:20}]}};
  const c=livePortalContext({$:(key)=>nodes[key],FormData:class{append(){}},apiRequest:()=>new Promise(r=>resolve=r)});
  c.renderPortalRequest=()=>{};c.bindPortalPDF();const pending=handlers.read();
  c.PORTAL.accountGeneration++;c.PORTAL_PDF={busy:false,error:'',document:null};
  resolve({filename:'need.pdf',text:'Other account private data',page_count:1});await pending;
  assert.equal(c.PORTAL_PDF.document,null);
});

test('prior-case disagreements remain visible instead of presenting a false consensus',()=>{
  const c=livePortalContext();
  const html=c.portalPriorCases({sample_count:4,has_conflict:true,category_votes:[{label:'Excel',count:2},{label:'Python',count:1}],department_votes:[]});
  assert.ok(html.includes('farklılaşıyor'));assert.ok(html.includes('4 önceki talep'));assert.ok(html.includes('Python'));
});

function reviewHarness(overrides={},transport){
  const handlers={},sent=[];let outcome='APPROVED';
  const ids=['decisionCategory','decisionDepartment','decisionCourse','decisionMissing','decisionExcess','decisionNeedType','decisionReason','decisionRoutingDepartment','decisionCorrections','decisionApprovedSummary','decisionOutcomeNote','decisionRouting','decisionRoutingChoice','decisionSubmit','decisionRouteLabel','decisionActionHint','decisionTaxonomyNote','portalDecisionError'];
  const nodes=Object.fromEntries(ids.map(id=>['#'+id,{value:'',dataset:{},innerHTML:'',textContent:'',disabled:false,hidden:false,classList:{toggle(){}},addEventListener:(name,fn)=>handlers[id+':'+name]=fn}]));
  Object.assign(nodes['#decisionCategory'],{value:'DATA.EXCEL'});nodes['#decisionDepartment'].value='TECHNICAL_DESIGN';nodes['#decisionNeedType'].value='training';nodes['#decisionCourse'].value='3';nodes['#decisionReason'].value='İhtiyaç ve kaynak doğrulandı.';
  const fields=['decisionCategory','decisionDepartment','decisionCourse','decisionMissing','decisionExcess','decisionNeedType'];
  nodes['#portalDecisionForm']={
    addEventListener:(name,fn)=>handlers['form:'+name]=fn,
    querySelector:selector=>selector.includes('decisionOutcome')?{value:outcome}:nodes['#decisionSubmit'],
    querySelectorAll:selector=>selector==='[data-correction]'?fields.map(id=>nodes['#'+id]):[{addEventListener:(_,fn)=>handlers.change=fn}],
  };
  const c=livePortalContext({$:(key)=>nodes[key],render(){},apiRequest:async(path,options)=>{sent.push({path,payload:JSON.parse(options.body)});return transport?transport(path,options):{status:'ACTION_PLANNED'}}});
  c.PORTAL.epoch=2;c.PORTAL.taxonomy={groups:[{name:'Veri',children:[{id:'DATA.EXCEL',name:'Excel'}]}]};
  const request={request_id:4,version:7,permissions:{can_refer:true},classification:{subcategory_id:'DATA.EXCEL'},
    routing:{resolved:true,requires_selection:false,department:'TECHNICAL_DESIGN'},
    decision_support:{action:'USE_COURSE',suggested_department:{id:'TECHNICAL_DESIGN'},brief:{existing_course:{course_id:3}},missing_topics:[]},...overrides};
  return {c,nodes,handlers,sent,request,setOutcome(value){outcome=value;handlers.change()}};
}

test('returning from correction to approval submits the AI verdict without stale corrections or duplicate confirmation',async()=>{
  const h=reviewHarness();await h.c.bindPortalDecision(h.request,2);
  h.setOutcome('MODIFIED');h.nodes['#decisionDepartment'].value='ENGINEERING_DESIGN';h.nodes['#decisionMissing'].value='Ek konu';h.setOutcome('APPROVED');
  assert.equal(h.nodes['#decisionCorrections'].hidden,true);
  await h.handlers['form:submit']({preventDefault(){}});
  assert.equal(h.sent[0].path,'/api/admin/requests/4/review-and-advance');
  assert.deepEqual(h.sent[0].payload,{outcome:'APPROVED',expected_version:7,reason:'İhtiyaç ve kaynak doğrulandı.'});
});

test('single unresolved target is sent as routing metadata without falsely modifying AI approval',async()=>{
  const h=reviewHarness({routing:{resolved:false,requires_selection:true,department:null},decision_support:{action:'NEW_COURSE'}});
  h.nodes['#decisionCourse'].value='';await h.c.bindPortalDecision(h.request,2);
  assert.equal(h.nodes['#decisionRoutingDepartment'].required,true);
  assert.equal(h.nodes['#decisionRoutingChoice'].hidden,false);
  h.nodes['#decisionRoutingDepartment'].value='ENGINEERING_DESIGN';
  await h.handlers['form:submit']({preventDefault(){}});
  assert.equal(h.sent[0].payload.routing_department,'ENGINEERING_DESIGN');
  assert.equal(h.sent[0].payload.outcome,'APPROVED');
  assert.ok(!('actual_department' in h.sent[0].payload));
});

test('full course match bypasses target choice while a human-added gap needs a real target',async()=>{
  const h=reviewHarness({routing:{resolved:false,requires_selection:true,department:null}});
  await h.c.bindPortalDecision(h.request,2);
  assert.equal(h.nodes['#decisionRoutingDepartment'].required,false);
  h.setOutcome('MODIFIED');h.nodes['#decisionDepartment'].value='';h.nodes['#decisionMissing'].value='Ek kazanım';h.handlers['decisionMissing:change']();
  assert.equal(h.nodes['#decisionRoutingDepartment'].required,true);
});

test('corrected category uses the server routing rule and clears a stale suggested department',async()=>{
  const h=reviewHarness({review_options:{routing_by_category:{'OPERATIONS.MANUFACTURING':{id:'TECHNICAL_DESIGN'},'ENGINEERING.SYSTEMS':{id:'ENGINEERING_DESIGN'},'OTHER.REVIEW':{id:null}}},decision_support:{action:'NEW_COURSE'}});
  h.nodes['#decisionCourse'].value='';await h.c.bindPortalDecision(h.request,2);h.setOutcome('MODIFIED');
  h.nodes['#decisionCategory'].value='ENGINEERING.SYSTEMS';h.handlers['decisionCategory:change']();
  assert.equal(h.nodes['#decisionDepartment'].value,'ENGINEERING_DESIGN');
  assert.equal(h.nodes['#decisionRoutingDepartment'].required,false);
  h.nodes['#decisionCategory'].value='OTHER.REVIEW';h.handlers['decisionCategory:change']();
  assert.equal(h.nodes['#decisionDepartment'].value,'');
  assert.equal(h.nodes['#decisionRoutingDepartment'].required,true);
  h.nodes['#decisionDepartment'].value='TECHNICAL_DESIGN';h.handlers['decisionDepartment:change']();
  h.nodes['#decisionCategory'].value='ENGINEERING.SYSTEMS';h.handlers['decisionCategory:change']();
  assert.equal(h.nodes['#decisionDepartment'].value,'TECHNICAL_DESIGN','explicit human reassignment remains intentional');
});

test('non-training and rejection keep their meaning and department feedback cannot advance an analyst workflow',async()=>{
  const nonTraining=reviewHarness({decision_support:{action:'NON_TRAINING'}});await nonTraining.c.bindPortalDecision(nonTraining.request,2);
  assert.equal(nonTraining.nodes['#decisionRouting'].hidden,true);
  assert.ok(nonTraining.nodes['#decisionSubmit'].innerHTML.includes('YZ değerlendirmesini onayla'));
  const department=reviewHarness({permissions:{can_refer:false}});await department.c.bindPortalDecision(department.request,2);
  department.setOutcome('REJECTED');await department.handlers['form:submit']({preventDefault(){}});
  assert.equal(department.sent[0].path,'/api/admin/requests/4/decisions');
  assert.equal(department.sent[0].payload.training_need_confirmed,false);
  assert.equal(department.sent[0].payload.outcome,'REJECTED');
});

test('duplicate decision submissions are ignored and a conflict preserves the typed draft',async()=>{
  let reject;const h=reviewHarness({},()=>new Promise((resolve,fail)=>{reject=fail}));await h.c.bindPortalDecision(h.request,2);
  h.nodes['#decisionReason'].value='İnceleme notum korunmalı.';
  const first=h.handlers['form:submit']({preventDefault(){}});await h.handlers['form:submit']({preventDefault(){}});
  assert.equal(h.sent.length,1);assert.equal(h.nodes['#decisionSubmit'].disabled,true);
  reject(Object.assign(new Error('Talep değişti.'),{status:409}));await first;
  assert.equal(h.c.PORTAL.drafts['4:decision'].reason,'İnceleme notum korunmalı.');
  assert.equal(h.nodes['#decisionSubmit'].disabled,false);
  assert.ok(h.nodes['#portalDecisionError'].innerHTML.includes('Taslağım korunsun'));
});

test('filters persist only status and sorting per authenticated account, never the request search',()=>{
  const saved=new Map();const c=livePortalContext({localStorage:{getItem:key=>saved.get(key),setItem:(key,value)=>saved.set(key,value)}});
  c.PORTAL.user={username:'analyst-one'};c.PORTAL.filter='REFERRED';c.PORTAL.sort='oldest';c.PORTAL.search='PRIVATE PROJECT PHRASE';c.portalSaveFilters(true);
  assert.equal(saved.size,1);assert.deepEqual(JSON.parse([...saved.values()][0]),{status:'REFERRED',sort:'oldest',view:''});
  c.PORTAL.user={username:'analyst-two'};c.portalRestoreFilters(true);assert.equal(c.PORTAL.filter,'');
  c.PORTAL.user={username:'analyst-one'};c.portalRestoreFilters(true);assert.equal(c.PORTAL.filter,'REFERRED');assert.equal(c.PORTAL.sort,'oldest');
});

test('activity history shows only recorded events, named actors and rejection reasons',()=>{
  const c=livePortalContext();const html=c.portalTimeline({status:'IN_REVIEW',process:{current_owner:{label:'İhtiyaç analizi'},next_action:{label:'Kapsamı değerlendir'},timeline:[
    {label:'YZ önerisi yanlış',outcome:'REJECTED',note:'<b>Kapsam yanlış</b>',actor:{display_name:'Analist A',role:'NEEDS_ANALYST'},at:'2026-09-07T10:35:00Z'},
    {label:'Talep oluşturuldu',actor:{display_name:'Çalışan B',role:'EMPLOYEE'},at:'2026-09-06T10:00:00Z'},
  ]}});
  assert.ok(html.indexOf('Talep oluşturuldu')<html.indexOf('YZ önerisi yanlış'));assert.ok(html.includes('Analist A'));assert.ok(html.includes('Çalışan B'));
  assert.ok(html.includes('&lt;b&gt;Kapsam yanlış&lt;/b&gt;'));assert.ok(html.includes('activity-rejected'));assert.ok(!html.includes('Kapsamı değerlendir'));
  assert.equal((html.match(/<li /g)||[]).length,2);
});

test('single valid target is selected automatically and submitted without a second confirmation',async()=>{
  const h=reviewHarness({routing:{resolved:false,requires_selection:true,department:null,options:[{id:'ENGINEERING_DESIGN',label:'Mühendislik'}]},decision_support:{action:'NEW_COURSE'}});
  await h.c.bindPortalDecision(h.request,2);
  assert.equal(h.nodes['#decisionRoutingChoice'].hidden,true);
  await h.handlers['form:submit']({preventDefault(){}});
  assert.equal(h.sent.length,1);assert.equal(h.sent[0].payload.routing_department,'ENGINEERING_DESIGN');
  assert.equal(h.sent[0].payload.outcome,'APPROVED');assert.equal(h.sent[0].payload.actual_department,undefined);
});

test('case layout separates recorded history from current action and preserves status transitions',()=>{
  const c=livePortalContext();
  const result={request_id:4,status:'REFERRED',topic:'Sentetik ihtiyaç',process:{creator:{display_name:'Çalışan A'},current_owner:{label:'Mühendislik'},next_action:{label:'İçeriği incele'},timeline:[
    {status:'IN_REVIEW',at:'2026-09-01T10:00:00Z',label:'Analize alındı'},
    {outcome:'MODIFIED',at:'2026-09-01T11:00:00Z',label:'Düzeltildi'},
    {status:'REFERRED',at:'2026-09-01T12:00:00Z',label:'Yönlendirildi'}]}};
  const history=c.portalTimeline(result);assert.ok(history.includes('İhtiyaç analizinde <span aria-label="yeni durum">→</span> Eğitim tasarımında'));
  const action=c.portalCurrentAction(result,'portalStatusForm');assert.ok(action.includes('İçeriği incele'));assert.ok(action.includes('Yönlendirildi'));assert.ok(action.includes('Mühendislik'));
  assert.ok(!history.includes('İçeriği incele'));
  const empty=c.portalProcessSteps({status:'IN_REVIEW'});assert.ok(!empty.includes('class="complete"'));assert.ok(empty.includes('süreç adımları mevcut değil'));
});

test('missing identity and dates are honest, raw technical status does not leak into the UI',()=>{
  const c=livePortalContext();assert.equal(c.portalDate(null),'Tarih kaydı yok');assert.equal(c.portalDate('bad date'),'Tarih kaydı yok');
  const facts=c.portalRequestFacts({});assert.ok(facts.includes('Kullanıcı bilgisi kaydedilmemiş'));assert.ok(facts.includes('Organizasyon bilgisi tanımlanmamış'));
  assert.ok(!c.workflowBadge('PENDING_SECRET_ENUM').includes('PENDING_SECRET_ENUM'));
  const steps=c.portalProcessSteps({status:'ACTION_PLANNED',process:{steps:[{label:'Eğitim tasarımı',state:'skipped'}]}});
  assert.ok(steps.includes('Gerekmedi'));assert.ok(!steps.includes('aria-current="step"'));
});

test('full-course analysis brief uses actual next action and labels generic planning information optional',()=>{
  const c=livePortalContext();const html=c.portalAnalysisBrief({status:'IN_REVIEW',routing:{requires_selection:true,reason:'Sorumlu birimi seçmelidir.'},decision_support:{action:'USE_COURSE',action_label:'Mevcut dersin uygunluğunu onayla',suggested_department:{reason:'Sorumlu birimi seçmelidir.'},brief:{existing_course:{course_name:'Excel'},information_needed:['Katılımcı sayısı']}}});
  assert.ok(html.includes('Mevcut ders çözüm planına alınır'));
  assert.ok(!html.includes('Sorumlu birimi seçmelidir'));
  assert.ok(html.includes('İsteğe bağlı'));assert.ok(html.includes('tespit edilmiş eksiklik veya onay koşulu değildir'));
});

test('first review appears before optional AI detail, then a recorded review collapses behind the next action',()=>{
  const c=livePortalContext();c.PORTAL.user={role:'NEEDS_ANALYST'};
  const result={request_id:5,version:1,status:'IN_REVIEW',text:'Raporlama yetkinliği ihtiyacı.',permissions:{can_review:true,can_refer:true},decision_support:{action:'USE_COURSE',fit_percent:97,brief:{existing_course:{course_name:'Excel'}}}};
  const first=c.portalDetailBody(result,true);
  assert.ok(first.indexOf('id="portalDecisionForm"')<first.indexOf('id="portalAnalysisDetails"'));
  assert.ok(first.includes('%97'));assert.ok(first.includes('Raporlama yetkinliği ihtiyacı.'));
  const next=c.portalDetailBody({...result,status:'ACTION_PLANNED',version:2,decisions:[{request_version:2,reviewer:{role:'NEEDS_ANALYST'}}]},true);
  assert.ok(next.includes('<details class="card review-repeat" >'));
  assert.ok(next.indexOf('id="portalStatusForm"')<next.indexOf('class="card review-repeat"'));
  assert.equal(c.portalReviewAlreadyRecorded({...result,version:3,decisions:[{request_version:2,reviewer:{role:'NEEDS_ANALYST'}}]}),false,'reopened review must not be hidden');
});

test('empty generated drafts never show update warnings while a changed note remains visible',()=>{
  const c=livePortalContext();c.portalDraft({request_id:4,version:1},'status');
  const process={available_actions:[{code:'RESOLVE',channel:'action',label:'Çözümün gerçekleştiğini bildir',target:'RESOLVED'}]};
  const empty=c.portalStatusEditor({request_id:4,version:2,status:'ACTION_PLANNED',process},true);
  assert.ok(!empty.includes('Talep güncellendi.'));
  c.PORTAL.drafts['4:status'].note='Kaybolmaması gereken açıklama';
  const dirty=c.portalStatusEditor({request_id:4,version:3,status:'ACTION_PLANNED',process},true);
  assert.ok(dirty.includes('Talep güncellendi.'));assert.ok(dirty.includes('Kaybolmaması gereken açıklama'));
});

test('logout removes prior live-region feedback and cancels only the local document polling timer',()=>{
  const canceled=[],removed=[];const node={textContent:'Önceki hesabın işlem sonucu',classList:{remove:value=>removed.push(value)}};
  const c=livePortalContext({$:(key)=>key==='#toast'?node:null,DOC_INDEX:{timer:42,report:{private:'document'}},clearTimeout:id=>canceled.push(id)});
  c.clearPortalAccount();assert.equal(node.textContent,'');assert.deepEqual(removed,['show']);assert.deepEqual(canceled,[42]);assert.equal(c.DOC_INDEX.timer,null);assert.equal(c.DOC_INDEX.report,null);
});

test('role report uses each units reviewed requests as denominator and keeps missing roles unmeasured',()=>{
  const c=livePortalContext();
  const html=c.portalRoleReport([{role:'NEEDS_ANALYST',reviewed_requests:4,approved:3,modified:1,rejected:0},
    {role:'TECHNICAL_DESIGN',reviewed_requests:2,approved:1,modified:0,rejected:1}]);
  assert.ok(html.includes('%75'));assert.ok(html.includes('%50'));assert.ok(html.includes('öneriye katılım · 4 talep'));
  assert.ok(html.includes('Mühendislik Eğitim Tasarım'));assert.ok(html.includes('Henüz değerlendirme yok'));
  assert.ok(html.includes('birim toplamları genel talep sayısına eşit olmayabilir'));
  assert.ok(!html.includes('%0'));
});

test('scope signals distinguish confirmed training needs from unconfirmed and unavailable counts',()=>{
  const c=livePortalContext();
  const html=c.portalScopeReport([{topic:'Pivot',count:5,confirmed_count:2,request_ids:[1,2,3,4,5]},
    {topic:'Python',count:1,confirmed_count:0,request_ids:[6]},
    {topic:'Older signal',count:1,request_ids:[7]}],'Eksik içerik','İçerik boşlukları');
  assert.ok(html.includes('2 doğrulandı</strong> · 3 doğrulanmadı'));
  assert.ok(html.includes('0 doğrulandı</strong> · 1 doğrulanmadı'));
  assert.ok(html.includes('Eğitim ihtiyacı doğrulama bilgisi yok'));
  assert.ok(html.includes('talepte eğitim ihtiyacının insan tarafından onaylandığını'));
});

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

test('analysis failure retains the last successful version and uses backend retry permission',()=>{
  const c=livePortalContext();
  const state={latest_run:{id:2,sequence:2,status:'FAILED',status_label:'Analiz tamamlanamadı',error_message:'Servis kapalı.'},latest_completed:{id:1,sequence:1,completed_at:'2026-09-07T10:00:00Z'},available_actions:[{code:'RETRY',label:'Analizi yeniden dene'}]};
  const html=c.portalAnalysisState({analysis_state:state});
  assert.ok(html.includes('Talebiniz kaydedildi ancak analiz şu anda tamamlanamadı.'));
  assert.ok(html.includes('Önceki başarılı sonuç korunuyor.'));assert.ok(html.includes('v1'));
  assert.ok(html.includes('Analizi yeniden dene'));assert.ok(!html.includes('FAILED'));
  assert.ok(!c.portalAnalysisState({analysis_state:{...state,available_actions:[]}}).includes('data-analysis-action'));
});
test('a fresh analysis version never inherits a historical human decision',()=>{
  const c=livePortalContext();c.PORTAL.user={role:'NEEDS_ANALYST'};
  const request={status:'ACTION_PLANNED',version:8,analysis_state:{latest_completed:{id:2}},decisions:[{request_version:8,reviewer:{role:'NEEDS_ANALYST'},analysis_version:{id:1}}]};
  assert.equal(c.portalReviewAlreadyRecorded(request),false);
  request.decisions[0].analysis_version.id=2;assert.equal(c.portalReviewAlreadyRecorded(request),true);
});
test('pending request shows no invented course analysis or progress success',()=>{
  const c=livePortalContext();
  const html=c.portalDetailBody({request_id:12,version:1,status:'IN_REVIEW',text:'Kaydedilen özgün metin',analysis_state:{latest_run:{id:1,sequence:1,status:'PENDING',status_label:'Analiz bekliyor'},latest_completed:null,available_actions:[]}},true);
  assert.ok(html.includes('Analiz bekliyor'));assert.ok(html.includes('Kaydedilen özgün metin'));
  assert.ok(!html.includes('Katalog uyumu'));assert.ok(!html.includes('Eksik kazanım'));assert.ok(!html.includes('data-analysis-action'));
});

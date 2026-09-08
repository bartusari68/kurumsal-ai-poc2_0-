const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100},reducedMotion:'reduce'}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8015/');await page.locator('#accountUsername').fill('teknik_admin');await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(()=>PORTAL.user&&PORTAL.ready);
 
 async function switchUser(user){await page.getByRole('button',{name:'Çıkış yap',exact:true}).click();await page.locator('#accountUsername').fill(user);await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(u=>PORTAL.user&&PORTAL.user.username===u&&PORTAL.ready,user)}
 await switchUser('ihtiyac_admin');
 await page.getByRole('button',{name:'Yetkinlik Kataloğu',exact:true}).click();await page.locator('#skillCreate summary').click();
 await page.locator('#skillForm [name="canonical_name"]').fill('REST API geliştirme');await page.locator('#skillForm [name="aliases"]').fill('RESTful API');await page.locator('#skillForm button').click();await page.getByRole('heading',{name:'REST API geliştirme',exact:true}).waitFor();
 await page.evaluate(()=>openPortalRequest(2,true));await page.locator('[data-skill-dismiss-candidate="1"]').click();await page.waitForFunction(()=>!SKILLS.busy&&document.querySelector('.skill-need-history'));
 await page.evaluate(()=>openPortalRequest(2,true));await page.locator('#requestSkills').waitFor();assert.equal(await page.locator('[data-skill-confirm-candidate="1"]').count(),0);
 await page.evaluate(()=>openPortalRequest(1,true));await page.locator('#requestSkills').waitFor();
 await page.locator('#decisionReason').fill('Kaydedilmemiş sentetik karar gerekçesi');
 await page.locator('[data-skill-confirm-candidate="1"]').click();await page.waitForFunction(()=>document.querySelector('#requestSkills').textContent.includes('İnsan tarafından doğrulandı'));
 assert.equal(await page.locator('#decisionReason').inputValue(),'Kaydedilmemiş sentetik karar gerekçesi');
 await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'tmp/faz11-request-skills.png',fullPage:true});
 await switchUser('teknik_admin');await page.evaluate(()=>openPublication(2));await page.locator('[data-skill-map-editor]').click();await page.locator('[data-skill-map-add]').click();
 await page.locator('#skillMapRows [data-skill-select] option[value="2"]').waitFor({state:'attached'});await page.locator('#skillMapRows [data-skill-select]').selectOption('2');await page.locator('[data-map-outcome]').selectOption('0');
 await page.locator('#publication-description').fill('Kaydedilmemiş katalog açıklaması');await page.locator('#skillMapForm button[type="submit"]').click();await page.waitForFunction(()=>PUB.detail.skills.length===1&&!SKILLS.busy);
 assert.equal(await page.locator('#publication-description').inputValue(),'Kaydedilmemiş katalog açıklaması');assert.equal(await page.evaluate(()=>PUB.drafts[2].expected_version),await page.evaluate(()=>PUB.detail.revision));
 await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'tmp/faz11-course-map.png',fullPage:true});
 await page.getByRole('button',{name:'Ders Kataloğu',exact:true}).click();await page.locator('#catalogContent [data-pub-course]').first().click();await page.locator('[data-training-create]').click();await page.locator('#trainingForm').waitFor();
 await page.locator('[name="external_trainer"]').fill('Sentetik eğitmen');await page.locator('[name="start_at"]').fill('2026-10-01T09:00');await page.locator('[name="end_at"]').fill('2026-10-01T11:00');await page.locator('[name="location"]').fill('Sentetik eğitim salonu');await page.locator('[name="capacity"]').fill('2');await page.getByRole('button',{name:'Oturum taslağı oluştur',exact:true}).click();
 await page.waitForFunction(()=>TRAIN.detail&&TRAIN.detail.status==='DRAFT'&&!TRAIN.busy);
 const id=await page.evaluate(()=>TRAIN.id),user=await page.evaluate(()=>TRAIN.options.source_requests[0].user_id);
 await page.locator('#trainingUser').selectOption(String(user));await page.locator('#trainingRequest').selectOption('1');await page.getByRole('button',{name:'Katılımcıyı kaydet',exact:true}).click();await page.waitForFunction(()=>TRAIN.detail.participant_count===1&&!TRAIN.busy);
 await page.locator('[data-training-action="SCHEDULE"]').click();await page.waitForFunction(()=>TRAIN.detail.status==='SCHEDULED'&&!TRAIN.busy);
 await page.getByRole('button',{name:'Eğitim Operasyonları',exact:true}).click();await page.locator('#trainingStatus').selectOption('SCHEDULED');await page.waitForFunction(()=>document.querySelectorAll('#trainingQueue tbody tr').length===1);await page.screenshot({path:'tmp/faz11-queue.png',fullPage:true});await page.locator('[data-training-open="'+id+'"]').click();
 await page.locator('[data-training-action="START"]').click();await page.waitForFunction(()=>TRAIN.detail.status==='IN_PROGRESS'&&!TRAIN.busy);
 await page.locator('[data-training-result="attendance"]').selectOption('ATTENDED');await page.locator('[data-training-result="completion"]').selectOption('COMPLETED');
 await page.locator('[data-training-save-results="attendance"]').click();await page.waitForFunction(()=>TRAIN.detail.enrollments[0].attendance==='ATTENDED'&&!TRAIN.busy);
 assert.equal(await page.locator('[data-training-result="completion"]').inputValue(),'COMPLETED');
 await page.locator('[data-training-save-results="completion"]').click();await page.waitForFunction(()=>TRAIN.detail.enrollments[0].completion==='COMPLETED'&&!TRAIN.busy);
 await page.locator('[data-training-action="FINALIZE_ATTENDANCE"]').click();await page.waitForFunction(()=>TRAIN.detail.attendance_finalized_at&&!TRAIN.busy);
 await page.locator('[data-training-action="COMPLETE"]').click();await page.waitForFunction(()=>TRAIN.detail.status==='COMPLETED'&&!TRAIN.busy);

 await page.locator('summary').filter({hasText:'Eğitim sonrası sonuç takibi planla'}).click();
 await page.locator('#evaluationPlanForm button').click();await page.locator('#evaluationPlanResult').filter({hasText:'planlandı'}).waitFor();
 await page.screenshot({path:'tmp/faz11-session.png',fullPage:true});
 async function login(user){await page.getByRole('button',{name:'Çıkış yap',exact:true}).click();await page.locator('#accountUsername').fill(user);await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(u=>PORTAL.user&&PORTAL.user.username===u&&PORTAL.ready,user)}
 await login('calisan');
 await page.getByRole('button',{name:'Değerlendirmelerim',exact:true}).click();await page.locator('#evaluationList tbody tr').first().waitFor();
 assert.equal(await page.locator('#evaluationList tbody tr').count(),3);
 await page.screenshot({path:'tmp/faz11-evaluations.png',fullPage:true});
 const evaluations=await (await page.request.get('http://127.0.0.1:8015/api/evaluations')).json();
 for(const item of evaluations.items){
   await page.evaluate(id=>openEvaluation(id),item.id);await page.locator('#evaluationForm').waitFor();
   const data=await (await page.request.get('http://127.0.0.1:8015/api/evaluations/'+item.id)).json();
   for(const q of data.template.questions){const input=page.locator('#evaluationForm [name="'+q.id+'"]');if(q.type==='free_text')await input.fill('Sentetik gözlem: uygulama örneklerini artırabiliriz.');else await input.selectOption(q.type==='rating'?'4':q.id==='outcome'?'PARTIALLY_RESOLVED':q.id==='problem_persists'?'PARTLY':q.id==='application'?'PARTLY':Object.keys(q.options)[0])}
   await page.screenshot({path:'tmp/faz11-evaluation-'+item.evaluation_type+'.png',fullPage:true});
   await page.locator('#evaluationSubmit').click();await page.waitForFunction(()=>!document.querySelector('#evaluationSubmit'));
   assert.equal(await page.locator('#evaluationForm select:not([disabled])').count(),0);
 }
 await page.getByRole('button',{name:'İşlerim',exact:true}).click();await page.locator('#operationsContent').waitFor();
 const inbox=await (await page.request.get('http://127.0.0.1:8015/api/operations/inbox')).json();assert.equal(inbox.items.filter(x=>x.kind==='evaluation').length,0);
 await login('teknik_admin');await page.evaluate(()=>openPortalRequest(1,true));await page.getByRole('heading',{name:'Sonuç / Etki',exact:true}).waitFor();
 await page.screenshot({path:'tmp/faz11-outcome-trace.png',fullPage:true});
 const detail=await (await page.request.get('http://127.0.0.1:8015/api/admin/requests/1')).json();assert.equal(detail.status,'REFERRED');assert.equal(detail.effectiveness.find(x=>x.evaluation_type==='APPLICATION').outcome,'PARTIALLY_RESOLVED');
 await page.evaluate(()=>openTraining(1));await page.getByRole('heading',{name:'Eğitim sonucu / etki',exact:true}).waitFor();await page.screenshot({path:'tmp/faz11-session-results.png',fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 
 await page.getByRole('button',{name:'Yetkinlik Kataloğu',exact:true}).click();await page.locator('#skillSearch').fill('Python');await page.locator('[data-skill-open="1"]').click();await page.getByRole('heading',{name:'Python',exact:true}).waitFor();await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'tmp/faz11-skill-detail.png',fullPage:true});
 await switchUser('calisan');await page.getByRole('button',{name:'Yetkinliklerim',exact:true}).click();await page.locator('[data-skill-mine="1"]').click();await page.locator('.skill-evidence').first().waitFor();assert.equal(await page.locator('.skill-evidence').count(),4);
 const evidence=await (await page.request.get('http://127.0.0.1:8015/api/skills/mine/1')).json();assert.deepEqual(evidence.evidence.items.map(x=>x.type).sort(),['REQUEST_NEED','TRAINING_COMPLETION','SELF_EVALUATION','OUTCOME_EVALUATION'].sort());
 await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'tmp/faz11-my-skill-evidence.png',fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.deepEqual(errors,[]);fs.writeFileSync('tmp/faz11-browser-report.json',JSON.stringify({passed:true,skillEvidence:4,requestDraftPreserved:true,publicationDraftPreserved:true,candidateDismissalPersists:true,evaluations:3,status:detail.status,outcome:'PARTIALLY_RESOLVED',javascriptErrors:errors},null,2));
 }finally{await browser.close()}})().catch(error=>{console.error(error);process.exitCode=1});

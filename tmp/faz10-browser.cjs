const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1100},reducedMotion:'reduce'}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8014/');await page.locator('#accountUsername').fill('teknik_admin');await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(()=>PORTAL.user&&PORTAL.ready);
 await page.getByRole('button',{name:'Ders Kataloğu',exact:true}).click();await page.locator('#catalogContent [data-pub-course]').first().click();await page.locator('[data-training-create]').click();await page.locator('#trainingForm').waitFor();
 await page.locator('[name="external_trainer"]').fill('Sentetik eğitmen');await page.locator('[name="start_at"]').fill('2026-10-01T09:00');await page.locator('[name="end_at"]').fill('2026-10-01T11:00');await page.locator('[name="location"]').fill('Sentetik eğitim salonu');await page.locator('[name="capacity"]').fill('2');await page.getByRole('button',{name:'Oturum taslağı oluştur',exact:true}).click();
 await page.waitForFunction(()=>TRAIN.detail&&TRAIN.detail.status==='DRAFT'&&!TRAIN.busy);
 const id=await page.evaluate(()=>TRAIN.id),user=await page.evaluate(()=>TRAIN.options.source_requests[0].user_id);
 await page.locator('#trainingUser').selectOption(String(user));await page.locator('#trainingRequest').selectOption('1');await page.getByRole('button',{name:'Katılımcıyı kaydet',exact:true}).click();await page.waitForFunction(()=>TRAIN.detail.participant_count===1&&!TRAIN.busy);
 await page.locator('[data-training-action="SCHEDULE"]').click();await page.waitForFunction(()=>TRAIN.detail.status==='SCHEDULED'&&!TRAIN.busy);
 await page.getByRole('button',{name:'Eğitim Operasyonları',exact:true}).click();await page.locator('#trainingStatus').selectOption('SCHEDULED');await page.waitForFunction(()=>document.querySelectorAll('#trainingQueue tbody tr').length===1);await page.screenshot({path:'tmp/faz10-queue.png',fullPage:true});await page.locator('[data-training-open="'+id+'"]').click();
 await page.locator('[data-training-action="START"]').click();await page.waitForFunction(()=>TRAIN.detail.status==='IN_PROGRESS'&&!TRAIN.busy);
 await page.locator('[data-training-result="attendance"]').selectOption('ATTENDED');await page.locator('[data-training-result="completion"]').selectOption('COMPLETED');
 await page.locator('[data-training-save-results="attendance"]').click();await page.waitForFunction(()=>TRAIN.detail.enrollments[0].attendance==='ATTENDED'&&!TRAIN.busy);
 assert.equal(await page.locator('[data-training-result="completion"]').inputValue(),'COMPLETED');
 await page.locator('[data-training-save-results="completion"]').click();await page.waitForFunction(()=>TRAIN.detail.enrollments[0].completion==='COMPLETED'&&!TRAIN.busy);
 await page.locator('[data-training-action="FINALIZE_ATTENDANCE"]').click();await page.waitForFunction(()=>TRAIN.detail.attendance_finalized_at&&!TRAIN.busy);
 await page.locator('[data-training-action="COMPLETE"]').click();await page.waitForFunction(()=>TRAIN.detail.status==='COMPLETED'&&!TRAIN.busy);

 await page.locator('summary').filter({hasText:'Eğitim sonrası sonuç takibi planla'}).click();
 await page.locator('#evaluationPlanForm button').click();await page.locator('#evaluationPlanResult').filter({hasText:'planlandı'}).waitFor();
 await page.screenshot({path:'tmp/faz10-session.png',fullPage:true});
 async function login(user){await page.getByRole('button',{name:'Çıkış yap',exact:true}).click();await page.locator('#accountUsername').fill(user);await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(u=>PORTAL.user&&PORTAL.user.username===u&&PORTAL.ready,user)}
 await login('calisan');
 await page.getByRole('button',{name:'Değerlendirmelerim',exact:true}).click();await page.locator('#evaluationList tbody tr').first().waitFor();
 assert.equal(await page.locator('#evaluationList tbody tr').count(),3);
 await page.screenshot({path:'tmp/faz10-evaluations.png',fullPage:true});
 const evaluations=await (await page.request.get('http://127.0.0.1:8014/api/evaluations')).json();
 for(const item of evaluations.items){
   await page.evaluate(id=>openEvaluation(id),item.id);await page.locator('#evaluationForm').waitFor();
   const data=await (await page.request.get('http://127.0.0.1:8014/api/evaluations/'+item.id)).json();
   for(const q of data.template.questions){const input=page.locator('#evaluationForm [name="'+q.id+'"]');if(q.type==='free_text')await input.fill('Sentetik gözlem: uygulama örneklerini artırabiliriz.');else await input.selectOption(q.type==='rating'?'4':q.id==='outcome'?'PARTIALLY_RESOLVED':q.id==='problem_persists'?'PARTLY':q.id==='application'?'PARTLY':Object.keys(q.options)[0])}
   await page.screenshot({path:'tmp/faz10-evaluation-'+item.evaluation_type+'.png',fullPage:true});
   await page.locator('#evaluationSubmit').click();await page.waitForFunction(()=>!document.querySelector('#evaluationSubmit'));
   assert.equal(await page.locator('#evaluationForm select:not([disabled])').count(),0);
 }
 await page.getByRole('button',{name:'İşlerim',exact:true}).click();await page.locator('#operationsContent').waitFor();
 const inbox=await (await page.request.get('http://127.0.0.1:8014/api/operations/inbox')).json();assert.equal(inbox.items.filter(x=>x.kind==='evaluation').length,0);
 await login('teknik_admin');await page.evaluate(()=>openPortalRequest(1,true));await page.getByRole('heading',{name:'Sonuç / Etki',exact:true}).waitFor();
 await page.screenshot({path:'tmp/faz10-outcome-trace.png',fullPage:true});
 const detail=await (await page.request.get('http://127.0.0.1:8014/api/admin/requests/1')).json();assert.equal(detail.status,'REFERRED');assert.equal(detail.effectiveness.find(x=>x.evaluation_type==='APPLICATION').outcome,'PARTIALLY_RESOLVED');
 await page.evaluate(()=>openTraining(1));await page.getByRole('heading',{name:'Eğitim sonucu / etki',exact:true}).waitFor();await page.screenshot({path:'tmp/faz10-session-results.png',fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.deepEqual(errors,[]);fs.writeFileSync('tmp/faz10-browser-report.json',JSON.stringify({passed:true,evaluations:3,status:detail.status,outcome:'PARTIALLY_RESOLVED',javascriptErrors:errors},null,2));
 }finally{await browser.close()}})().catch(error=>{console.error(error);process.exitCode=1});

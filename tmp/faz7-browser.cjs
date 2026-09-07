const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1000},reducedMotion:'reduce'}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8011/');await page.locator('#accountUsername').fill('teknik_admin');await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(()=>PORTAL.ready&&PORTAL.user);
 const report=[];
 for(const requestId of [1,2]){
  await page.getByRole('button',{name:'İşlerim',exact:true}).click();await page.locator('[data-dev-request="'+requestId+'"]').click();await page.locator('[data-dev-create]').click();await page.locator('#developmentForm').waitFor();
  assert.equal(await page.locator('[data-page="portal-delegations"]').count(),0);
  await page.locator('[data-dev-field="target_output"]').fill('Üretim adımlarını uygular ve sonucu doğrular.');
  if(requestId===2)await page.locator('[data-dev-field="change_notes"]').fill('Uygulama ve doğrulama örnekleri eklenecek.');
  await page.getByRole('button',{name:'Analiz önerilerini taslağa ekle',exact:true}).click();
  await page.getByRole('button',{name:'Kazanım ekle',exact:true}).click();await page.locator('[data-outcome="1"]').fill('Üretim sonuçlarını doğrulayabilir');
  await page.getByRole('button',{name:'Modül ekle',exact:true}).click();await page.locator('[data-module-title="0"]').fill('Üretim uygulaması');await page.locator('[data-module-description="0"]').fill('İş üzerinde örnek çalışma');
  await page.getByRole('button',{name:'Konu ekle',exact:true}).click();await page.locator('[data-topic-title="0:0"]').fill('Adımların uygulanması');await page.locator('[data-topic-description="0:0"]').fill('Üretim adımlarının sıralı uygulanması');
  await page.getByRole('button',{name:'Tasarım içeriğini kaydet',exact:true}).click();await page.waitForFunction(()=>DEV.detail.content_revision===1&&!DEV.busy);
  if(requestId===1){
   const remote=await page.evaluate(()=>developmentPayload(developmentDraft(DEV.detail)));remote.title='Diğer kullanıcı tasarımı';const identifier=await page.evaluate(()=>DEV.id);
   const response=await page.request.patch('http://127.0.0.1:8011/api/development/'+identifier,{data:remote});assert.equal(response.status(),200);
   await page.locator('[data-dev-field="summary"]').fill('Korunan insan taslağı ve uygulama hedefleri.');await page.getByRole('button',{name:'Tasarım içeriğini kaydet',exact:true}).click();await page.locator('[data-dev-rebase]').waitFor();
   assert.equal(await page.locator('[data-dev-field="summary"]').inputValue(),'Korunan insan taslağı ve uygulama hedefleri.');
   await page.locator('[data-dev-rebase]').click();await page.getByRole('button',{name:'Tasarım içeriğini kaydet',exact:true}).click();await page.waitForFunction(()=>!DEV.busy&&DEV.detail.content_revision===3);
  }
  for(const code of ['START_ANALYSIS','START_DESIGN']){await page.locator('[data-dev-action="'+code+'"]').click();await page.waitForFunction(code=>!DEV.busy&&DEV.detail.state===(code==='START_ANALYSIS'?'ANALYSIS':'DESIGN'),code)}
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.screenshot({path:'tmp/faz7-design-'+requestId+'.png',fullPage:true});
  await page.locator('[data-dev-action="SUBMIT_REVIEW"]').click();await page.waitForFunction(()=>!DEV.busy&&DEV.detail.state==='REVIEW');
  await page.locator('[data-dev-snapshot]').last().locator('summary').click();await page.locator('[data-dev-snapshot]').last().locator('h3').first().waitFor();
  await page.locator('#developmentNote').fill('Örnekleri yeniden kontrol edin');await page.locator('[data-dev-action="REQUEST_REVISION"]').click();await page.waitForFunction(()=>!DEV.busy&&DEV.detail.state==='DESIGN');
  await page.locator('[data-dev-action="SUBMIT_REVIEW"]').click();await page.waitForFunction(()=>!DEV.busy&&DEV.detail.state==='REVIEW');
  await page.locator('[data-dev-action="APPROVE"]').click();await page.waitForFunction(()=>!DEV.busy&&DEV.detail.state==='READY');
  const data=await page.evaluate(()=>DEV.detail);assert.equal(data.outcomes.length,2);assert.equal(data.modules[0].topics.length,1);
  await page.screenshot({path:'tmp/faz7-ready-'+requestId+'.png',fullPage:true});
  await page.getByRole('button',{name:'Kaynak Talep #'+requestId,exact:true}).click();await page.locator('.case-header').waitFor();assert.equal(await page.evaluate(()=>PORTAL.detail.status),'REFERRED');
  await page.locator('[data-dev-open="'+data.id+'"]').click();await page.locator('#developmentForm').waitFor();
  report.push({requestId,developmentId:data.id,state:data.state,requestUnchanged:true,outcomes:2,modules:1});
 }
 await page.getByRole('button',{name:'Eğitim Geliştirme',exact:true}).click();await page.locator('.development-table tbody tr').first().waitFor();assert.equal(await page.locator('.development-table tbody tr').count(),2);await page.screenshot({path:'tmp/faz7-queue.png',fullPage:true});
 await page.getByRole('button',{name:/Bildirimler,/}).click();await page.locator('[data-notification-open]').first().waitFor();await page.locator('[data-notification-open]').first().click();await page.locator('#developmentForm').waitFor();
 assert.deepEqual(errors,[]);fs.writeFileSync('tmp/faz7-browser-report.json',JSON.stringify({report,notificationOpensDevelopment:true,errors},null,2));console.log(JSON.stringify({report,errors}));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});

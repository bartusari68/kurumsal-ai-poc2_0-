const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 const base='http://127.0.0.1:8001';
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1000},reducedMotion:'reduce'}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/?v=faz4-browser');
  await page.locator('#accountUsername').fill('calisan');await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();
  await page.getByRole('button',{name:/Yeni talep ilet/}).first().click();
  await page.locator('#submitterRequestText').fill('Sentetik API testi eğitimi ihtiyacım var.');
  await page.waitForFunction(()=>LIVE_AI.status==='error');
  assert.equal(await page.locator('#submitterAnalyzeButton').isEnabled(),true);
  await page.locator('#submitterAnalyzeButton').click();
  await page.waitForFunction(()=>PORTAL.detail?.analysis_state?.latest_run?.status==='FAILED',{},{timeout:15000});
  const identifier=await page.evaluate(()=>PORTAL.detail.request_id);
  assert.ok(await page.locator('.case-file').innerText().then(t=>t.includes('Talebiniz kaydedildi ancak analiz şu anda tamamlanamadı.')));
  await page.screenshot({path:'tmp/faz4-analysis-failed-desktop.png',fullPage:true});
  await page.getByRole('button',{name:'Analizi yeniden dene',exact:true}).click();
  await page.waitForFunction(()=>PORTAL.detail?.analysis_state?.latest_run?.status==='COMPLETED',{},{timeout:15000});
  const initial=await page.evaluate(()=>({id:PORTAL.detail.request_id,version:PORTAL.detail.version,run:PORTAL.detail.analysis_state.latest_completed.id,sequence:PORTAL.detail.analysis_state.latest_completed.sequence,text:PORTAL.detail.text}));
  assert.equal(initial.id,identifier);assert.equal(initial.sequence,2);
  const manager=await browser.newContext();await manager.request.post(base+'/api/auth/login',{data:{username:'ihtiyac_admin',password:'1234'}});
  const info=await manager.request.post(base+'/api/admin/requests/'+identifier+'/actions',{data:{action:'REQUEST_INFO',expected_version:initial.version,note:'Sentetik ek kapsam bilgisini belirtin.'}});assert.equal(info.status(),200);
  await page.evaluate(id=>openPortalRequest(id,false),identifier);
  await page.locator('#requestStatusNote').fill('Ek sentetik bilgi: otomatik regresyon testleri de gerekiyor.');
  await page.locator('#portalStatusForm button[type=submit]').click();
  await page.waitForFunction(()=>PORTAL.detail?.analysis_state?.latest_run?.status==='COMPLETED'&&PORTAL.detail.analysis_state.latest_completed.sequence===3,{},{timeout:15000});
  const final=await page.evaluate(()=>({id:PORTAL.detail.request_id,text:PORTAL.detail.text,sequence:PORTAL.detail.analysis_state.latest_completed.sequence,runs:PORTAL.detail.analysis_state.history.map(x=>({sequence:x.sequence,status:x.status})),history:PORTAL.detail.process.timeline.map(x=>x.action).filter(Boolean),overflow:document.documentElement.scrollWidth>innerWidth}));
  assert.equal(final.id,identifier);assert.equal(final.text,initial.text);assert.equal(final.runs.length,3);assert.equal(final.overflow,false);assert.deepEqual(errors,[]);
  await page.screenshot({path:'tmp/faz4-analysis-updated-desktop.png',fullPage:true});
  const report={offlineSubmissionEnabled:true,persistedOnFailure:true,sameRequestAfterRetry:true,extraInfoCreatedVersion:true,originalTextPreserved:true,final,errors};
  fs.writeFileSync('tmp/faz4-browser-report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  await page.request.post(base+'/api/auth/logout');await manager.request.post(base+'/api/auth/logout');await manager.close();
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exit(1)});

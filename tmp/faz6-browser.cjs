const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const base='http://127.0.0.1:8001',errors=[],page=await browser.newPage({viewport:{width:1600,height:1000},reducedMotion:'reduce'});page.on('pageerror',e=>errors.push(e.message));
  async function login(username){await page.goto(base+'/?v=faz6');await page.locator('#accountUsername').fill(username);await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(()=>PORTAL.user&&PORTAL.ready)}
  await login('ihtiyac_admin');await page.getByRole('button',{name:'Vekâletlerim',exact:true}).first().click();await page.locator('#delegationUser').selectOption({label:'Sentetik Vekil'});
  function localDate(d){return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)}
  await page.locator('#delegationStart').fill(localDate(new Date(Date.now()-60000)));await page.locator('#delegationEnd').fill(localDate(new Date(Date.now()+3600000)));await page.locator('#delegationReason').fill('Sentetik izin dönemi');await page.getByRole('button',{name:'Vekâleti kaydet',exact:true}).click();
  await page.locator('[data-delegation-revoke]').waitFor();const delegation=await page.locator('[data-delegation-revoke]').getAttribute('data-delegation-revoke');await page.screenshot({path:'tmp/faz6-delegations-desktop.png',fullPage:true});
  await page.request.post(base+'/api/auth/logout');await login('vekil');await page.getByRole('button',{name:'İşlerim',exact:true}).click();await page.locator('#operationsContent tbody tr').first().waitFor();
  assert.ok((await page.locator('#operationsContent').innerText()).includes('adına vekâleten'));await page.screenshot({path:'tmp/faz6-inbox-desktop.png',fullPage:true});
  await page.locator('#operationsContent .table-request-title').first().click();await page.locator('.operations-delegation-banner').waitFor();
  const detail=await page.evaluate(()=>({id:PORTAL.detail.request_id,version:PORTAL.detail.version,assignee:PORTAL.detail.process.assignee.id}));
  const decision=await page.request.post(base+'/api/admin/requests/'+detail.id+'/decisions',{headers:{'X-Delegation-ID':delegation},data:{outcome:'REJECTED',expected_version:detail.version,reason:'Sentetik vekâlet değerlendirmesi kaydedildi.'}});assert.equal(decision.status(),200);const reviewed=await decision.json();assert.equal(reviewed.process.assignee.id,detail.assignee);
  const info=await page.request.post(base+'/api/admin/requests/'+detail.id+'/actions',{headers:{'X-Delegation-ID':delegation},data:{action:'REQUEST_INFO',expected_version:reviewed.version,note:'Sentetik test için ek kapsam bilgisi gerekiyor.'}});assert.equal(info.status(),200);
  await page.request.post(base+'/api/auth/logout');await login('calisan');await page.waitForFunction(()=>Number(document.querySelector('#operationsCount')?.textContent)>0,{},{timeout:40000});await page.locator('#operationsBell').click();await page.locator('[data-notification-open]').first().waitFor();assert.ok((await page.locator('#operationsContent').innerText()).includes('Ek bilginiz bekleniyor'));await page.screenshot({path:'tmp/faz6-notifications-desktop.png',fullPage:true});
  await page.locator('[data-notification-open]').first().click();await page.locator('.case-history').waitFor();assert.ok((await page.locator('.case-history').innerText()).includes('adına vekâleten'));assert.equal(await page.evaluate(()=>PORTAL.detail.status),'NEEDS_INFO');
  await page.getByRole('button',{name:'İşlerim',exact:true}).click();await page.locator('#operationsContent tbody tr').first().waitFor();assert.ok((await page.locator('#operationsContent').innerText()).includes('Ek bilgiyi gönder'));
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);assert.equal(overflow,false);assert.deepEqual(errors,[]);
  const report={delegationCreated:true,delegatedInbox:true,originalAssignmentPreservedOnReview:true,delegatedAuditVisible:true,employeeNotification:true,readOnOpen:true,employeeActionInbox:true,overflow,errors};fs.writeFileSync('tmp/faz6-browser-report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));await page.request.post(base+'/api/auth/logout');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});

const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});const report=[];try{
 for(const username of ['calisan','ihtiyac_admin','teknik_admin','muhendislik_admin']){
  const page=await browser.newPage({viewport:{width:1600,height:1000},reducedMotion:'reduce'}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8000/?v=faz6-live');await page.locator('#accountUsername').fill(username);await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(()=>PORTAL.user&&PORTAL.ready);
  for(const route of ['portal-inbox','portal-notifications','portal-delegations']){
   await page.evaluate(route=>{state.currentPage=route;render()},route);await page.waitForFunction(()=>document.querySelector('#operationsContent')&&!document.querySelector('#operationsContent .portal-skeleton'));
   assert.equal(await page.locator('#operationsContent [role=alert]').count(),0);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  }
  assert.ok((await page.locator('#operationsContent').innerText()).includes('başka aktif kullanıcı bulunmuyor'));
  assert.deepEqual(errors,[]);report.push({username,operationsViews:3,errors});await page.request.post('http://127.0.0.1:8000/api/auth/logout');await page.close();
 }
 fs.writeFileSync('tmp/faz6-live-report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});

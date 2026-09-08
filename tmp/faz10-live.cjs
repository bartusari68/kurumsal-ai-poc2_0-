const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{
const page=await browser.newPage({viewport:{width:1600,height:1100},reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto('http://127.0.0.1:8000/?v=20260908-17');await page.locator('#accountUsername').fill('calisan');await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(()=>PORTAL.user&&PORTAL.ready);
await page.getByRole('button',{name:'Değerlendirmelerim',exact:true}).click();await page.getByText('Bu durumda değerlendirme yok',{exact:true}).waitFor();
const list=await page.request.get('http://127.0.0.1:8000/api/evaluations');assert.equal(list.status(),200);assert.equal((await list.json()).total,0);
const inbox=await page.request.get('http://127.0.0.1:8000/api/operations/inbox');assert.equal(inbox.status(),200);
await page.getByRole('button',{name:'Çıkış yap',exact:true}).click();await page.locator('#accountUsername').fill('teknik_admin');await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(()=>PORTAL.user&&PORTAL.user.username==='teknik_admin'&&PORTAL.ready);
for(const path of ['/api/operations/inbox','/api/evaluations/report','/api/training','/api/operations/notifications']){const r=await page.request.get('http://127.0.0.1:8000'+path);assert.equal(r.status(),200,path)}
assert.deepEqual(errors,[]);fs.writeFileSync('tmp/faz10-live-report.json',JSON.stringify({url:'http://127.0.0.1:8000/?v=20260908-17',employeeMenu:true,employeeInbox:true,managerEndpoints:true,realEvaluations:0,javascriptErrors:errors},null,2));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});

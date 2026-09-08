const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{
const page=await browser.newPage({viewport:{width:1600,height:1100},reducedMotion:'reduce'});const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto('http://127.0.0.1:8014/');await page.locator('#accountUsername').fill('calisan');await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(()=>PORTAL.user&&PORTAL.ready);
await page.getByRole('button',{name:/Bildirimler,/}).click();await page.locator('[data-notification-open^="evaluation:"]').first().click();await page.locator('#evaluationForm').waitFor();assert.equal(await page.locator('#evaluationSubmit').count(),0);
await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'tmp/faz10-final-evaluation.png',fullPage:false});
await page.getByRole('button',{name:'Çıkış yap',exact:true}).click();await page.locator('#accountUsername').fill('teknik_admin');await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(()=>PORTAL.user&&PORTAL.user.username==='teknik_admin'&&PORTAL.ready);
await page.evaluate(()=>openCatalogCourse(1));await page.getByRole('heading',{name:'Eğitim sonucu / etki',exact:true}).waitFor();await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:'tmp/faz10-course-effectiveness.png',fullPage:false});
assert.deepEqual(errors,[]);fs.writeFileSync('tmp/faz10-ui-extra.json',JSON.stringify({notificationDeepLink:true,courseAggregate:true,javascriptErrors:errors},null,2));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});

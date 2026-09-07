const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{
 const report=[];
 for(const username of ['calisan','ihtiyac_admin','teknik_admin','muhendislik_admin']){
  const page=await browser.newPage({viewport:{width:1600,height:1000},reducedMotion:'reduce'}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8000/?v=faz8-live');await page.locator('#accountUsername').fill(username);await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(()=>PORTAL.ready&&PORTAL.user);
  await page.getByRole('button',{name:'Ders Kataloğu',exact:true}).click();await page.locator('#catalogContent tbody tr').first().waitFor();assert.equal(await page.locator('#catalogContent tbody tr').count(),8);
  const catalog=await (await page.request.get('http://127.0.0.1:8000/api/catalog')).json();assert.ok(catalog.items.every(row=>row.legacy&&row.version_number===1&&row.state==='PUBLISHED'));assert.ok(catalog.items.every(row=>row.knowledge.status==='indexed'));
  if(username==='teknik_admin')await page.screenshot({path:'tmp/faz8-live-catalog.png',fullPage:true});
  for(const item of catalog.items){const response=await page.request.get('http://127.0.0.1:8000/api/catalog/courses/'+item.course_id);assert.equal(response.status(),200)}
  await page.locator('#catalogSearch').fill(catalog.items[0].code);await page.waitForFunction(()=>document.querySelectorAll('#catalogContent tbody tr').length===1);
  await page.locator('[data-pub-course]').click();await page.getByRole('heading',{name:'Sürüm geçmişi',exact:true}).waitFor();await page.locator('[data-pub-open]').click();await page.waitForFunction(()=>state.currentPage==='portal-publication'&&PUB.detail);assert.equal(await page.locator('[data-pub-action]').count(),0);assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.deepEqual(errors,[]);
  report.push({username,catalogCourses:8,allCourseDetailsOpened:true,legacyVersionReadonly:true,errors});await page.request.post('http://127.0.0.1:8000/api/auth/logout');await page.close();
 }
 fs.writeFileSync('tmp/faz8-live-report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});

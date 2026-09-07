const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1600,height:1000},reducedMotion:'reduce'}),errors=[],posts=[];
  page.on('pageerror',e=>errors.push(e.message));
  // Every mutation is intercepted: existing production records are never used as writable fixtures.
  await page.route('**/api/admin/requests/*/actions',async route=>{posts.push(route.request().postDataJSON());await route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'Sentetik sürüm çakışması'})})});
  await page.goto('http://127.0.0.1:8000/?v=faz3-form');await page.locator('#accountUsername').fill('teknik_admin');await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();
  await page.locator('.table-request-title').first().click();await page.locator('#portalPlanForm').waitFor();
  await page.locator('#planSummary').fill('Sentetik tarayıcı testi: uygulamalı eğitim ve sonuç kontrolü.');await page.locator('#planTarget').fill('2030-01-04');
  await page.locator('#portalPlanForm button[type=submit]').click();await page.locator('#portalPlanForm .action-error .notice').waitFor();
  assert.equal(posts[0].action,'SAVE_PLAN');assert.equal(posts[0].responsible_unit,'TECHNICAL_DESIGN');assert.equal(posts[0].target_date,'2030-01-04');assert.equal(typeof posts[0].expected_version,'number');
  await page.locator('#portalPlanForm [data-portal=reload-detail]').click();await page.locator('#portalPlanForm').waitFor();
  assert.equal(await page.locator('#planSummary').inputValue(),posts[0].summary);assert.equal(await page.locator('#planTarget').inputValue(),'2030-01-04');
  await page.getByText('Kişisel atama',{exact:true}).click();await page.locator('#assignmentNote').fill('Sentetik kişi atama testi.');
  const value=await page.locator('#caseAssignee option').nth(1).getAttribute('value');await page.locator('#caseAssignee').selectOption(value);
  await page.locator('#portalAssignmentForm button[type=submit]').click();await page.locator('#portalAssignmentForm .action-error .notice').waitFor();
  assert.equal(posts[1].action,'ASSIGN');assert.equal(posts[1].assignee_id,Number(value));assert.deepEqual(errors,[]);
  await page.screenshot({path:'tmp/faz3-plan-form-desktop.png',fullPage:true});
  const report={interceptedMutationCount:posts.length,planPayloadVerified:true,assignmentPayloadVerified:true,conflictDraftPreserved:true,errors};fs.writeFileSync('tmp/faz3-form-report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  await page.request.post('http://127.0.0.1:8000/api/auth/logout');
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exit(1)});

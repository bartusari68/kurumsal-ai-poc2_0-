const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
 try{
  const base='http://127.0.0.1:8001',page=await browser.newPage({viewport:{width:1600,height:1000},reducedMotion:'reduce'}),errors=[],posts=[];
  page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/api/requests/analyze'))posts.push(r.postDataJSON())});
  await page.goto(base+'/?v=faz5');await page.locator('#accountUsername').fill('calisan');await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();
  await page.getByRole('button',{name:/Yeni talep ilet/}).first().click();
  assert.equal(await page.locator('#submitterRequestText').isVisible(),true);
  await page.getByRole('button',{name:'AI ile Netleştir',exact:true}).click();
  assert.equal(await page.locator('#submitterRequestText').isVisible(),false);
  await page.locator('#intakeAnswer').fill('Sentetik Excel eğitimi ihtiyacım var.');await page.locator('#intakeForm button[type=submit]').click();
  await page.waitForFunction(()=>INTAKE.response?.status==='needs_more_info'&&!INTAKE.busy);
  await page.locator('#intakeAnswer').fill('Haftalık dosyaları elle birleştiriyorum; otomatik rapor istiyorum.');
  await page.evaluate(()=>{state.currentPage='portal-home';render()});
  await page.evaluate(()=>{state.currentPage='submitter-request';render()});
  assert.equal(await page.locator('#intakeAnswer').inputValue(),'Haftalık dosyaları elle birleştiriyorum; otomatik rapor istiyorum.');
  await page.locator('#intakeForm button[type=submit]').click();await page.getByRole('heading',{name:'Talebiniz hazır',exact:true}).waitFor();
  assert.equal(posts.length,0);assert.equal((await (await page.request.get(base+'/api/requests/mine')).json()).total,0);
  await page.locator('#intakeEdit').click();await page.locator('#submitterRequestText').fill('Onayladığım son metin: ekip raporlarını Power Query ile birleştirme ihtiyacı.');
  await page.screenshot({path:'tmp/faz5-draft-desktop.png',fullPage:true});
  await page.locator('#submitterAnalyzeButton').click();await page.waitForFunction(()=>PORTAL.detail?.analysis_state?.latest_run?.status==='FAILED',{},{timeout:15000});
  assert.equal(posts.length,1);assert.equal(posts[0].text,'Onayladığım son metin: ekip raporlarını Power Query ile birleştirme ihtiyacı.');assert.ok(posts[0].intake_token);
  const id=await page.evaluate(()=>PORTAL.detail.request_id);
  const duplicate=await page.request.post(base+'/api/requests/analyze',{data:posts[0]});assert.equal((await duplicate.json()).request_id,id);
  await page.evaluate(()=>{resetIntake();LIVE_REQUEST.text='';state.currentPage='submitter-request';render()});
  await page.getByRole('button',{name:'AI ile Netleştir',exact:true}).click();await page.locator('#intakeAnswer').fill('OFFLINE sentetik erişim sorunum var.');await page.locator('#intakeForm button[type=submit]').click();
  await page.waitForFunction(()=>INTAKE.error&&!INTAKE.busy);await page.getByRole('button',{name:'Doğrudan talebe geç',exact:true}).click();
  assert.equal(await page.locator('#submitterRequestText').inputValue(),'OFFLINE sentetik erişim sorunum var.');assert.equal(await page.locator('#submitterAnalyzeButton').isEnabled(),true);
  await page.locator('#submitterAnalyzeButton').click();await page.waitForFunction(()=>PORTAL.detail?.request_id===2);
  const total=(await (await page.request.get(base+'/api/requests/mine')).json()).total;assert.equal(total,2);assert.deepEqual(errors,[]);
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);assert.equal(overflow,false);
  const report={followup:true,navigationPreservesAnswer:true,noRequestBeforeApproval:true,editedTextSubmitted:true,duplicateProtected:true,offlineFallbackSubmitted:true,requests:total,errors,overflow};
  fs.writeFileSync('tmp/faz5-browser-report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));await page.request.post(base+'/api/auth/logout');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});

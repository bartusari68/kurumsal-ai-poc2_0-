const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs');
(async()=>{
  const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--enable-unsafe-swiftshader']});
  const context=await browser.newContext({viewport:{width:1440,height:900},deviceScaleFactor:1});
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
    window.__gainPeaks=[];
    const A=window.AudioContext;
    if(A){const create=A.prototype.createGain;A.prototype.createGain=function(){const gain=create.call(this),ramp=gain.gain.exponentialRampToValueAtTime.bind(gain.gain);gain.gain.exponentialRampToValueAtTime=function(value,time){window.__gainPeaks.push(value);return ramp(value,time)};return gain;};}
  });
  await page.goto('http://127.0.0.1:8000/?v=20260907-6');
  await page.locator('#accountUsername').waitFor();
  await page.locator('.earth-ready').waitFor({timeout:20000});
  await page.waitForFunction(()=>getComputedStyle(document.querySelector('.experience-earth-canvas')).opacity==='1');
  await page.screenshot({path:'tmp/case-login-desktop.png'});
  const report={login:await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,canvas:document.querySelector('canvas').width,assets:performance.getEntriesByType('resource').filter(x=>/4k|stars-/.test(x.name)).map(x=>x.name.split('/').pop())}))};
  await page.locator('#accountUsername').fill('ihtiyac_admin');await page.locator('#accountPassword').fill('1234');
  await page.locator('#experienceLoginSubmit').click();
  await page.locator('.experience-entry').waitFor({state:'attached'});
  report.transition=await page.locator('.experience-entry').evaluate(el=>({hasLogin:!!el.querySelector('.experience-login'),inert:el.inert,credentialValue:el.querySelector('input[type=password]').value,animation:getComputedStyle(el).animationName}));
  await page.screenshot({path:'tmp/case-login-transition.png'});
  await page.locator('.experience-entry').waitFor({state:'detached'});
  report.audio=await page.evaluate(()=>window.__gainPeaks);
  await page.locator('.table-request-title').first().waitFor();await page.locator('.table-request-title').first().click();
  await page.locator('.case-file').waitFor();
  await page.screenshot({path:'tmp/case-detail-desktop.png',fullPage:true});
  report.detail=await page.evaluate(()=>({titleCount:document.querySelectorAll('#appView h1').length,process:!!document.querySelector('.case-process'),history:!!document.querySelector('.case-history'),currentAction:!!document.querySelector('.case-context'),overflow:document.documentElement.scrollWidth>innerWidth,activeSteps:document.querySelectorAll('.workflow-steps [aria-current=step]').length,historyFakeActions:document.querySelectorAll('.case-history .activity-current').length}));
  if(process.argv.includes('--desktop-only')){report.errors=errors;fs.writeFileSync('tmp/case-desktop-report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));await page.request.post('http://127.0.0.1:8000/api/auth/logout');await browser.close();return;}
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:'tmp/case-detail-mobile.png',fullPage:true});
  report.mobileDetail=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,stepColumns:getComputedStyle(document.querySelector('.workflow-steps')).gridTemplateColumns}));
  await page.request.post('http://127.0.0.1:8000/api/auth/logout');
  const mobile=await browser.newContext({viewport:{width:390,height:844},deviceScaleFactor:3,reducedMotion:'reduce'}),mp=await mobile.newPage();
  await mp.goto('http://127.0.0.1:8000/?v=20260907-6');await mp.locator('#accountUsername').waitFor();await mp.locator('.earth-ready').waitFor();
  await mp.screenshot({path:'tmp/case-login-mobile.png',fullPage:true});
  report.mobileLogin=await mp.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth,canvas:document.querySelector('canvas').width,starSource:document.querySelector('.experience-starfield img').currentSrc,highTextures:performance.getEntriesByType('resource').some(x=>/earth-.*-4k/.test(x.name))}));
  report.errors=errors;fs.writeFileSync('tmp/case-ui-report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  await browser.close();
})().catch(error=>{console.error(error);process.exit(1)});

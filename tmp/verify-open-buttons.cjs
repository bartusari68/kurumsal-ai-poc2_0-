const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{
for(const username of ['calisan','ihtiyac_admin','teknik_admin','muhendislik_admin']){
 const page=await browser.newPage({viewport:{width:1600,height:1000},reducedMotion:'reduce'}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8000/');await page.locator('#accountUsername').fill(username);await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(()=>PORTAL.ready&&PORTAL.user);
 await page.getByRole('button',{name:username==='calisan'?'Gönderdiğim Talepler':'İşlerim',exact:true}).click();
 const button=page.locator('#appView tbody tr button').first();await button.waitFor();await button.click();
 await page.locator('.case-header').waitFor({timeout:15000});console.log(JSON.stringify({username,opened:true,title:await page.locator('.case-header h1').innerText(),errors}));
 await page.request.post('http://127.0.0.1:8000/api/auth/logout');await page.close();
}
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});

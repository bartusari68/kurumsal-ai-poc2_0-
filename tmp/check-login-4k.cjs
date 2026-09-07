const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const sharp=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
const fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--enable-unsafe-swiftshader']});
 const ctx=await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:2,reducedMotion:'reduce'}),page=await ctx.newPage();
 await page.goto('http://127.0.0.1:8000/?v=20260907-6');await page.locator('.earth-ready').waitFor();
 await page.waitForFunction(()=>performance.getEntriesByType('resource').some(x=>x.name.includes('earth-clouds.webp')));
 const report=await page.evaluate(()=>({canvas:document.querySelector('canvas').width,star:document.querySelector('.experience-starfield img').currentSrc,overflow:document.documentElement.scrollWidth>innerWidth}));
 await page.screenshot({path:'tmp/case-login-4k.png'});
 const sphere=await page.evaluate(()=>{const c=document.querySelector('canvas'),gl=c.getContext('webgl');c.width=c.height=4096;gl.viewport(0,0,4096,4096);gl.drawArrays(gl.TRIANGLE_STRIP,0,4);return c.toDataURL('image/png').split(',')[1]});
 const data=Buffer.from(sphere,'base64');
 for(const [width,name] of [[1024,'earth-day-night.webp'],[2048,'earth-still-2k.webp'],[4096,'earth-still-4k.webp']])await sharp(data).resize(width,width).webp({quality:88}).toFile('app/static/assets/experience/'+name);
 fs.writeFileSync('tmp/login-4k-report.json',JSON.stringify(report));console.log(JSON.stringify(report));await browser.close();
})().catch(error=>{console.error(error);process.exit(1)});

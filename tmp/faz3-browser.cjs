const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
  const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--enable-unsafe-swiftshader']});
  const report={accounts:[],errors:[]};
  try{
    for(const username of ['ihtiyac_admin','calisan','teknik_admin','muhendislik_admin']){
      const context=await browser.newContext({viewport:{width:1600,height:1000},reducedMotion:'reduce'});
      const page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
      await page.goto('http://127.0.0.1:8000/?v=faz3-7');
      await page.locator('#accountUsername').fill(username);await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();
      await page.waitForFunction(()=>PORTAL.user&&PORTAL.ready);
      const admin=username!=='calisan';
      const response=await page.request.get('http://127.0.0.1:8000'+(admin?'/api/admin/requests':'/api/requests/mine'));
      assert.equal(response.status(),200);const list=await response.json();
      report.accounts.push({username,total:list.total,queueViews:list.queue_views.map(v=>v.id)});
      if(username==='ihtiyac_admin'){
        await page.locator('#portalQueueViews button').first().waitFor();
        await page.screenshot({path:'tmp/faz3-queue-desktop.png',fullPage:true});
        await page.getByRole('button',{name:'Birimimin işleri',exact:true}).click();
        await page.waitForFunction(()=>PORTAL.view==='unit'&&document.querySelector('#portalListContent').getAttribute('aria-busy')==='false');
        const unit=await page.evaluate(()=>({rows:PORTAL.list.items.map(x=>x.responsible_scope),total:PORTAL.list.total}));
        assert.ok(unit.rows.every(role=>role==='NEEDS_ANALYST'));report.unitFilter=unit;
      }
      if(list.items.length){
        await page.evaluate(id=>openPortalRequest(id,PORTAL.isAdmin),list.items[0].request_id);
        await page.locator('.case-file').waitFor();
        const detail=await page.evaluate(()=>({state:PORTAL.detail.status,actions:PORTAL.detail.process.available_actions.map(x=>x.code),owner:PORTAL.detail.process.responsible_scope,overflow:document.documentElement.scrollWidth>innerWidth,history:!!document.querySelector('.case-history')}));
        assert.equal(detail.overflow,false);assert.equal(detail.history,true);report.accounts.at(-1).detail=detail;
        if(username==='ihtiyac_admin')await page.screenshot({path:'tmp/faz3-detail-desktop.png',fullPage:true});
      }
      await page.request.post('http://127.0.0.1:8000/api/auth/logout');await context.close();
    }
    assert.deepEqual(report.errors,[]);fs.writeFileSync('tmp/faz3-browser-report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exit(1)});

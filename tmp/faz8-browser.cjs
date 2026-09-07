const {chromium}=require('C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});try{
 const page=await browser.newPage({viewport:{width:1600,height:1000},reducedMotion:'reduce'}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8012/');await page.locator('#accountUsername').fill('teknik_admin');await page.locator('#accountPassword').fill('1234');await page.locator('#experienceLoginSubmit').click();await page.waitForFunction(()=>PORTAL.user&&PORTAL.ready);
 async function call(path,method='get',data){const result=await page.request[method]('http://127.0.0.1:8012'+path,data?{data}:{});assert.ok(result.ok(),await result.text());return result.json()}
 const report=[];
 for(const requestId of [1,2]){
  const request=await call('/api/admin/requests/'+requestId);let dev=await call('/api/development','post',{source_request_id:requestId,expected_request_version:request.version,...{work_type:request.development.create.work_type,source_course_id:request.development.create.source_course_id}});
  dev=await call('/api/development/'+dev.id,'patch',{expected_version:dev.version,title:'Üretim uygulamaları '+requestId,summary:'Üretim işlemlerini uygulama ve sonuç doğrulama eğitimi.',brief:{target_output:'Üretim sonuçlarını doğrular',missing_topics:['Uygulama'],change_notes:'Uygulama modülü eklendi',excess_notes:''},outcomes:[{text:'İşlem adımlarını uygulayabilir'},{text:'Sonuçları doğrulayabilir'}],modules:[{title:'Uygulama',description:'İş üzerinde öğrenme',topics:[{title:'Sonuç doğrulama',description:'Senaryo üzerinde doğrulama'}]}]});
  for(const action of ['START_ANALYSIS','START_DESIGN','SUBMIT_REVIEW','APPROVE'])dev=await call('/api/development/'+dev.id+'/actions','post',{expected_version:dev.version,action});
  await page.getByRole('button',{name:'Eğitim Geliştirme',exact:true}).click();await page.locator('[data-dev-open="'+dev.id+'"]').click();await page.locator('[data-pub-create]').click();await page.locator('#publicationForm').waitFor();
  if(requestId===1)await page.locator('#publication-code').fill('SENTETIK-KOD');
  await page.locator('#publication-title').fill('Yayımlanan üretim eğitimi '+requestId);await page.getByRole('button',{name:'Katalog bilgilerini kaydet',exact:true}).click();await page.waitForFunction(()=>!PUB.busy&&PUB.detail.revision===2);
  if(requestId===1){const remote=await page.evaluate(()=>publicationPayload(publicationDraft(PUB.detail)));remote.title='Diğer katalog düzenlemesi';await call('/api/catalog/versions/'+(await page.evaluate(()=>PUB.id)),'patch',remote);await page.locator('#publication-title').fill('Korunan katalog taslağı');await page.getByRole('button',{name:'Katalog bilgilerini kaydet',exact:true}).click();await page.locator('[data-pub-rebase]').waitFor();assert.equal(await page.locator('#publication-title').inputValue(),'Korunan katalog taslağı');await page.locator('[data-pub-rebase]').click();await page.getByRole('button',{name:'Katalog bilgilerini kaydet',exact:true}).click();await page.waitForFunction(()=>!PUB.busy&&PUB.detail.revision===4)}
  const before=(await call('/api/catalog')).total;
  await page.locator('[data-pub-action="PREPARE"]').click();await page.waitForFunction(()=>!PUB.busy&&PUB.detail.state==='READY_FOR_PUBLISH');assert.equal((await call('/api/catalog')).total,before);
  await page.screenshot({path:'tmp/faz8-ready-'+requestId+'.png',fullPage:true});
  await page.locator('[data-pub-action="PUBLISH"]').click();await page.waitForFunction(()=>!PUB.busy&&PUB.detail.state==='PUBLISHED');
  const published=await page.evaluate(()=>PUB.detail);assert.equal(await page.locator('#publicationForm').count(),0);assert.equal(published.knowledge.status,'no_document');
  if(requestId===2){await page.locator('[data-pub-compare]').click();await page.locator('#publicationComparison h4').first().waitFor();assert.ok((await page.locator('#publicationComparison').innerText()).includes('Eklenen'))}
  await page.locator('[data-pub-review]').click();await page.locator('#publicationReview h3').first().waitFor();
  assert.equal((await call('/api/development/'+dev.id)).state,'READY');assert.equal((await call('/api/admin/requests/'+requestId)).status,'REFERRED');
  await page.getByRole('button',{name:'Katalog dersine git',exact:true}).click();await page.getByRole('heading',{name:'Sürüm geçmişi',exact:true}).waitFor();
  await page.screenshot({path:'tmp/faz8-course-'+requestId+'.png',fullPage:true});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  report.push({requestId,version:published.version_number,state:published.state,courseId:published.course_id,requestAndDevelopmentUnchanged:true});
 }
 await page.getByRole('button',{name:'Ders Kataloğu',exact:true}).click();await page.locator('#catalogSearch').fill('SENTETIK-KOD');await page.waitForFunction(()=>document.querySelectorAll('#catalogContent tbody tr').length===1&&document.querySelector('#catalogContent tbody').textContent.includes('SENTETIK-KOD'));await page.screenshot({path:'tmp/faz8-catalog.png',fullPage:true});
 await page.getByRole('button',{name:/Bildirimler,/}).click();await page.locator('[data-notification-open]').first().waitFor();await page.locator('[data-notification-open]').first().click();await page.waitForFunction(()=>state.currentPage==='portal-publication'&&PUB.detail);assert.deepEqual(errors,[]);
 fs.writeFileSync('tmp/faz8-browser-report.json',JSON.stringify({report,conflictDraftPreserved:true,catalogSearch:true,notificationOpensPublication:true,errors},null,2));console.log(JSON.stringify({report,errors}));
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});

const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app/static/js/intake.js'),'utf8');
function setup(){
 const ctx=vm.createContext({esc:s=>String(s).replaceAll('<','&lt;').replaceAll('>','&gt;'),PORTAL:{accountGeneration:1},LIVE_REQUEST:{text:'',busy:false},state:{currentPage:'submitter-request'},renderPortalRequest(){}});
 vm.runInContext(source,ctx);return ctx;
}
test('direct submission is available without assistant approval',()=>{
 const c=setup();assert.equal(c.intakeCanSubmit(),true);assert.equal(c.intakeSubmissionToken(),null);
 c.INTAKE.mode='ai';assert.equal(c.intakeCanSubmit(),false);
 c.INTAKE.response={status:'ready'};c.INTAKE.token='signed';assert.equal(c.intakeCanSubmit(),true);
 c.INTAKE.refining=true;assert.equal(c.intakeCanSubmit(),false);
});
test('intake only calls preparation endpoint and never creates a request automatically',async()=>{
 const c=setup(),calls=[];c.INTAKE.mode='ai';c.INTAKE.answer='Sentetik ihtiyaç';
 c.apiRequest=async(path)=>{calls.push(path);return {status:'ready',draft:'Düzenlenebilir taslak',token:'signed',question:null}};
 await c.runIntake(false);assert.deepEqual(calls,['/api/intake']);assert.equal(c.LIVE_REQUEST.text,'Düzenlenebilir taslak');
 c.LIVE_REQUEST.text='Kullanıcının son metni';assert.equal(c.intakeSubmissionToken(),'signed');
});
test('failed interview preserves answer, previous draft and direct option',async()=>{
 const c=setup();c.INTAKE.mode='ai';c.INTAKE.answer='Gönderilmemiş yanıt';c.LIVE_REQUEST.text='Taslak';
 c.apiRequest=async()=>{throw Error('secret provider response')};await c.runIntake(false);
 assert.equal(c.INTAKE.answer,'Gönderilmemiş yanıt');assert.equal(c.LIVE_REQUEST.text,'Taslak');
 assert.ok(c.INTAKE.error.includes('doğrudan'));assert.ok(!c.INTAKE.error.includes('secret'));
 c.INTAKE.mode='direct';assert.equal(c.intakeCanSubmit(),true);
});
test('late response cannot replace another accounts draft',async()=>{
 const c=setup();let resolve;c.INTAKE.mode='ai';c.INTAKE.answer='Eski hesap';
 c.apiRequest=()=>new Promise(r=>{resolve=r});const task=c.runIntake(false);
 c.PORTAL.accountGeneration++;c.resetIntake();c.LIVE_REQUEST.text='Yeni hesap';
 resolve({status:'ready',draft:'Eski hesap taslağı',token:'old'});await task;
 assert.equal(c.LIVE_REQUEST.text,'Yeni hesap');assert.equal(c.INTAKE.token,null);
});
test('in-flight intake does not replace a directly edited request',async()=>{
 const c=setup();let resolve;c.INTAKE.mode='ai';c.INTAKE.answer='İlk metin';
 c.apiRequest=()=>new Promise(r=>{resolve=r});const task=c.runIntake(false);
 c.INTAKE.mode='direct';c.LIVE_REQUEST.text='Doğrudan yazdığım son metin';
 resolve({status:'ready',draft:'AI taslağı',token:'new'});await task;
 assert.equal(c.LIVE_REQUEST.text,'Doğrudan yazdığım son metin');assert.equal(c.INTAKE.draft,'AI taslağı');
});
test('conversation renders escaped user/model text and an editable approval flow',()=>{
 const c=setup();c.INTAKE.mode='ai';c.INTAKE.messages=[{role:'user',text:'<script>bad</script>'}];
 c.INTAKE.response={status:'ready',question_count:4};const html=c.intakeMarkup();
 assert.ok(!html.includes('<script>'));assert.ok(html.includes('&lt;script&gt;'));assert.ok(html.includes('Talebiniz hazır'));
 assert.ok(html.includes('Düzenle'));assert.ok(html.includes('intakeRefine" disabled'));assert.ok(html.includes('yalnızca'));
});
test('duplicate clicks while intake is pending issue one model request',async()=>{
 const c=setup();let resolve,calls=0;c.INTAKE.answer='İhtiyaç';
 c.apiRequest=()=>{calls++;return new Promise(r=>resolve=r)};
 const first=c.runIntake(false);await c.runIntake(false);
 resolve({status:'ready',draft:'Taslak',token:'new'});await first;assert.equal(calls,1);
});

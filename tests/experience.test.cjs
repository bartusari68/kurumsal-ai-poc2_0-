const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../app/static/js/experience.js'),'utf8');

function node(value=''){
  return {value,type:'password',dataset:{},isConnected:true,disabled:false,hidden:false,events:{},attributes:{},
    innerHTML:'',textContent:'',focus(){this.focused=true},
    addEventListener(name,fn){this.events[name]=fn},setAttribute(k,v){this.attributes[k]=v},
    removeAttribute(k){delete this.attributes[k]},remove(){this.removed=true},
    getContext(){return null}};
}
function setup(reduced){
  const elements=Object.fromEntries(['portalAccountLogin','accountUsername','accountPassword','experiencePasswordToggle','experienceCaps','experienceSound','experienceEarth','experienceLoginSubmit','portalLoginError'].map(k=>[k,node()]));
  const timers=[],appended=[];
  const context={document:{getElementById:id=>elements[id],querySelector:()=>null,createElement:()=>node(),body:{appendChild:el=>appended.push(el)}},
    localStorage:{getItem(){return null}},matchMedia:()=>({matches:reduced}),setTimeout:fn=>timers.push(fn)};
  context.window=context;vm.createContext(context);vm.runInContext(source,context);
  return {context,elements,timers,appended};
}
test('reduced motion enters immediately without overlay or delayed callback',async()=>{
  const {context,timers,appended}=setup(true);let entered=0;
  await context.playExperienceEntry(()=>entered++);
  assert.equal(entered,1);assert.equal(timers.length,0);assert.equal(appended.length,0);
});
test('entry animation renders authenticated content immediately and always removes overlay',async()=>{
  const {context,timers,appended}=setup(false);let entered=0;
  const result=context.playExperienceEntry(()=>entered++);
  assert.equal(entered,1);assert.equal(appended.length,1);assert.equal(appended[0].attributes['aria-hidden'],'true');
  timers[0]();await result;assert.equal(appended[0].removed,true);
});
test('failed login keeps inputs, blocks duplicate submissions and allows retry',async()=>{
  const {context,elements,appended}=setup(true);let reject,calls=0;
  elements.accountUsername.value=' test-user ';elements.accountPassword.value='test-password';
  context.bindExperienceLogin({authenticate:credentials=>{
    calls++;assert.equal(credentials.username,'test-user');assert.equal(credentials.password,'test-password');
    return new Promise((_,no)=>{reject=no});
  },onAuthenticated(){assert.fail('Invalid credentials must not enter the app')}});
  const event={preventDefault(){}};
  const submit=elements.portalAccountLogin.events.submit;
  const first=submit(event);await submit(event);assert.equal(calls,1);
  reject(new Error('Giriş bilgileri doğrulanamadı.'));await first;
  assert.equal(elements.accountUsername.value,' test-user ');assert.equal(elements.accountPassword.value,'test-password');
  assert.equal(elements.experienceLoginSubmit.disabled,false);assert.equal(elements.portalAccountLogin.dataset.busy,'false');
  assert.match(elements.portalLoginError.textContent,/doğrulanamadı/);assert.equal(appended.length,0);
});
test('a late login response cannot authenticate after its form has been replaced',async()=>{
  const {context,elements}=setup(true);let resolve,entered=0;
  elements.accountUsername.value='test-user';elements.accountPassword.value='test-password';
  context.bindExperienceLogin({authenticate:()=>new Promise(yes=>{resolve=yes}),onAuthenticated(){entered++}});
  const pending=elements.portalAccountLogin.events.submit({preventDefault(){}});
  elements.portalAccountLogin.isConnected=false;resolve({user:{username:'test-user'}});await pending;
  assert.equal(entered,0);
});

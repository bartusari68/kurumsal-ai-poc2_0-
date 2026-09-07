const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../app/static/js/development.js'),'utf8');
function setup(){const c=vm.createContext({});vm.runInContext(source,c);return c}
test('remote version cannot silently overwrite an unsaved design draft',()=>{
 const c=setup(),data={id:1,version:4,title:'İlk',summary:'Özet',brief:{},outcomes:[],modules:[]};
 const draft=c.developmentDraft(data);draft.title='İnsan taslağı';draft.dirty=true;
 const retained=c.developmentDraft({...data,version:5,title:'Diğer kullanıcı'});
 assert.equal(retained.title,'İnsan taslağı');assert.equal(retained.expected_version,4);
});
test('structured design payload preserves order and ids without leaking server metadata',()=>{
 const c=setup(),draft={expected_version:2,title:'Ders',summary:'Özet',brief:{},outcomes:[{id:2,text:'İkinci',position:9},{id:1,text:'İlk',created_at:'old'}],modules:[{id:4,title:'Modül',topics:[{id:8,title:'Konu',position:7}]}]};
 const result=c.developmentPayload(draft);assert.deepEqual(Array.from(result.outcomes,r=>r.id),[2,1]);assert.equal(result.modules[0].topics[0].id,8);assert.equal(result.outcomes[1].created_at,undefined);assert.equal(result.modules[0].topics[0].position,undefined);
});
test('account reset discards development drafts and delegated context',()=>{
 const c=setup();c.DEV.drafts[2]={title:'Özel taslak'};c.DEV.delegationId=7;c.resetDevelopment();
 assert.equal(Object.keys(c.DEV.drafts).length,0);assert.equal(c.DEV.delegationId,null);
});
test('snapshot presentation escapes human text instead of rendering stored markup',()=>{
 const c=setup();c.esc=s=>String(s||'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
 const html=c.developmentArtifactView({title:'<img onerror=alert(1)>',summary:'<script>bad</script>',outcomes:[{text:'<svg/onload=bad>'}],modules:[]});
 assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img '));assert.ok(html.includes('&lt;svg'));
});

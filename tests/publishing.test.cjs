const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../app/static/js/publishing.js'),'utf8');
function setup(){const c=vm.createContext({});vm.runInContext(source,c);return c}
test('a newer publication revision preserves unsaved catalog metadata and its original version',()=>{
 const c=setup(),data={id:1,revision:2,code:'A',title:'İlk',description:'İlk açıklama'};
 const draft=c.publicationDraft(data);draft.title='İnsan taslağı';draft.dirty=true;
 const result=c.publicationDraft({...data,revision:3,title:'Diğer kullanıcı'});
 assert.equal(result.title,'İnsan taslağı');assert.equal(result.expected_version,2);
});
test('catalog editor submits metadata only, never mutating reviewed outcomes or source ids',()=>{
 const c=setup(),result=c.publicationPayload({expected_version:1,code:'A',title:'Ders',description:'Açıklama',source_review_id:3,outcomes:[{text:'tamper'}],dirty:true});
 assert.deepEqual(Object.keys(result),['expected_version','code','title','description']);
});
test('account reset discards publication drafts and delegation',()=>{
 const c=setup();c.PUB.drafts[1]={title:'Özel'};c.PUB.delegationId=7;c.resetPublishing();
 assert.equal(Object.keys(c.PUB.drafts).length,0);assert.equal(c.PUB.delegationId,null);
});
test('version comparison escapes user-authored added removed and changed content',()=>{
 const c=setup();c.esc=s=>String(s||'').replaceAll('<','&lt;').replaceAll('>','&gt;');
 const section={added:['<img src=x>'],removed:['<svg>'],changed:[{before:'<script>',after:'<iframe>'}]};
 const result=c.publicationDiff({from:{version_number:1},to:{version_number:2},metadata:section,outcomes:section,modules:section,topics:section});
 assert.ok(!result.includes('<img '));assert.ok(!result.includes('<script>'));assert.ok(result.includes('Eklenen'));assert.ok(result.includes('Çıkarılan'));assert.ok(result.includes('Değiştirilen'));
});

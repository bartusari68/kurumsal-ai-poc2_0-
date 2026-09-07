const {test}=require('node:test');const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../app/static/js/operations.js'),'utf8');
function setup(){const c=vm.createContext({PORTAL:{user:{},selectedId:7,accountGeneration:1}});vm.runInContext(source,c);return c}
test('delegation headers apply only to the selected request workflow routes',()=>{
 const c=setup();c.OPS.delegationId=12;
 assert.equal(c.operationsHeaders('/api/admin/requests/7/actions',{})['X-Delegation-ID'],'12');
 assert.equal(c.operationsHeaders('/api/requests/7',{})['X-Delegation-ID'],'12');
 for(const route of ['/api/admin/requests/8/actions','/api/operations/notifications','/api/admin/requests','/api/chat','/api/requests/analyze','/api/intake','/api/taxonomy'])assert.equal(c.operationsHeaders(route,{})['X-Delegation-ID'],undefined);
});
test('reset discards delegated context without editing request ownership',()=>{
 const c=setup();c.OPS.delegationId=12;c.OPS.form={reason:'Private draft'};c.resetOperations();
 assert.equal(c.OPS.delegationId,null);assert.equal(c.OPS.form.reason,undefined);assert.equal(c.PORTAL.selectedId,7);
});
test('late unread count response cannot enter another account',async()=>{
 const c=setup();let resolve;const node={textContent:'new account'};c.$=()=>node;c.apiRequest=()=>new Promise(r=>resolve=r);
 const task=c.refreshOperationsCount();c.PORTAL.accountGeneration++;resolve({unread_count:42});await task;
 assert.equal(node.textContent,'new account');
});
test('older unread result cannot overwrite a newer count',async()=>{
 const c=setup(),pending=[];const badge={textContent:''},bell={setAttribute(){}};c.$=id=>id==='#operationsCount'?badge:bell;c.apiRequest=()=>new Promise(r=>pending.push(r));
 const first=c.refreshOperationsCount(),second=c.refreshOperationsCount();pending[1]({unread_count:2});await second;pending[0]({unread_count:9});await first;assert.equal(badge.textContent,2);
});
test('operations routes are explicit and do not hijack intake or normal workspaces',()=>{
 const c=setup();c.renderOperationsInbox=()=>{};c.renderOperationsNotifications=()=>{};
 for(const route of ['portal-inbox','portal-notifications'])assert.equal(c.operationsRoute(route),true);
 for(const route of ['submitter-request','admin-panel','portal-detail','portal-delegations'])assert.equal(c.operationsRoute(route),false);
});

/* Operations views consume backend recipients, action policy and delegation scope. */
var OPS;
function resetOperations(){OPS={generation:0,countRevision:0,delegationId:null,offset:0,form:{},busy:false};var bell=typeof $==='function'?$('#operationsBell'):null;if(bell)bell.remove()}
resetOperations();
function operationsHeaders(path,headers){
  var result=Object.assign({},headers||{}),match=path.match(/^\/api\/(?:admin\/)?requests\/(\d+)(?:\/(?:actions|status|refer|decisions|review-and-advance|analysis))?$/);
  if(OPS.delegationId&&match&&Number(match[1])===PORTAL.selectedId)result['X-Delegation-ID']=String(OPS.delegationId);
  return result;
}
function mountOperations(){
  if(!PORTAL.user)return;
  var target=document.querySelector('.top-actions');if(!target)return;
  if(!$('#operationsBell')){var button=document.createElement('button');button.id='operationsBell';button.className='btn operations-bell';button.dataset.page='portal-notifications';button.type='button';button.innerHTML='<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg><span>Bildirimler</span><span id="operationsCount" class="badge b-blue">0</span>';target.prepend(button)}
  refreshOperationsCount();
}
async function refreshOperationsCount(){
  if(typeof PORTAL==='undefined'||!PORTAL.user)return;
  var generation=PORTAL.accountGeneration,s=OPS,revision=++s.countRevision;
  try{var value=await apiRequest('/api/operations/notifications/count');if(s!==OPS||generation!==PORTAL.accountGeneration||revision!==s.countRevision)return;var badge=$('#operationsCount'),bell=$('#operationsBell');if(badge)badge.textContent=value.unread_count;if(bell)bell.setAttribute('aria-label','Bildirimler, '+value.unread_count+' okunmamış')}
  catch(error){if(s===OPS&&generation===PORTAL.accountGeneration){var badge=$('#operationsCount');if(badge)badge.textContent='—'}}
}
function operationsRoute(route){
  if(['portal-inbox','portal-notifications'].indexOf(route)<0)return false;
  OPS.offset=0;if(route==='portal-inbox')renderOperationsInbox();else renderOperationsNotifications();return true;
}
function operationsPager(data){return '<div class="portal-pagination"><span>'+data.total+' kayıt</span><div><button class="btn sm" id="operationsPrev" '+(data.offset===0?'disabled':'')+'>Önceki</button> <button class="btn sm" id="operationsNext" '+(data.offset+data.limit>=data.total?'disabled':'')+'>Sonraki</button></div></div>'}
function bindOperationsPager(data,reload){$('#operationsPrev').onclick=function(){OPS.offset=Math.max(0,OPS.offset-20);reload()};$('#operationsNext').onclick=function(){OPS.offset+=20;reload()}}
async function renderOperationsInbox(){
  var epoch=PORTAL.epoch;$('#appView').innerHTML=pageHead('İşlerim','Şu anda sizden beklenen işlemler.')+'<section class="card" id="operationsContent">'+portalSkeleton('İşleriniz yükleniyor')+'</section>';
  try{var data=await apiRequest('/api/operations/inbox?limit=20&offset='+OPS.offset);if(epoch!==PORTAL.epoch)return;
    var items=data.items.map(function(item){return Object.assign({},item,{subcategory:item.action_required})});
    $('#operationsContent').innerHTML=(items.length?developmentTable(items,true):portalEmpty('Şu anda bekleyen işiniz yok','Sizden işlem beklendiğinde bu listede görünecek.'))+operationsPager(data);
    bindOperationsPager(data,renderOperationsInbox);
  }catch(error){if(epoch===PORTAL.epoch)$('#operationsContent').innerHTML=portalError(error)}
}
async function renderOperationsNotifications(){
  var epoch=PORTAL.epoch;$('#appView').innerHTML=pageHead('Bildirimler','Talebiniz ve sizden beklenen işlemler hakkında güncellemeler.','<button class="btn" id="operationsReadAll">Tümünü okundu işaretle</button>')+'<section class="card" id="operationsContent">'+portalSkeleton('Bildirimler yükleniyor')+'</section>';
  $('#operationsReadAll').onclick=async function(){this.disabled=true;try{await apiRequest('/api/operations/notifications/read-all',{method:'POST'});if(epoch===PORTAL.epoch){refreshOperationsCount();renderOperationsNotifications()}}catch(error){if(epoch===PORTAL.epoch){this.disabled=false;portalShowError(error)}}};
  try{var data=await apiRequest('/api/operations/notifications?limit=20&offset='+OPS.offset);if(epoch!==PORTAL.epoch)return;
    $('#operationsContent').innerHTML=(data.items.length?'<div class="operations-notifications">'+data.items.map(function(item){return '<article class="operations-notification '+(!item.read_at?'unread':'')+'"><div><h2>'+esc(item.title)+'</h2><p>'+esc(item.message)+'</p><span class="caption">'+portalDateTime(item.created_at)+(item.request_id?' · Talep #'+item.request_id:'')+'</span></div><div class="inline-actions">'+(item.request_id?'<button class="btn" data-notification-open="'+item.id+'">'+(item.publication_id?'Ders sürümünü aç':item.development_id?'Çalışmayı aç':'Talebi aç')+'</button>':'')+(!item.read_at?'<button class="link-btn" data-notification-read="'+item.id+'">Okundu işaretle</button>':'<span class="caption">Okundu</span>')+'</div></article>'}).join('')+'</div>':portalEmpty('Henüz bildiriminiz yok','Önemli işlem güncellemeleri burada görünecek.'))+operationsPager(data);
    document.querySelectorAll('[data-notification-open],[data-notification-read]').forEach(function(button){button.onclick=async function(){var id=Number(button.dataset.notificationOpen||button.dataset.notificationRead),item=data.items.find(function(row){return row.id===id});button.disabled=true;try{await apiRequest('/api/operations/notifications/'+id+'/read',{method:'POST'});if(epoch!==PORTAL.epoch)return;refreshOperationsCount();if(button.dataset.notificationOpen){if(item.publication_id)openPublication(item.publication_id,item.delegation_id);else if(item.development_id)openDevelopment(item.development_id,item.delegation_id);else openPortalRequest(item.request_id,PORTAL.isAdmin,item.delegation_id)}else renderOperationsNotifications()}catch(error){if(epoch===PORTAL.epoch){button.disabled=false;portalShowError(error)}}}});bindOperationsPager(data,renderOperationsNotifications);
  }catch(error){if(epoch===PORTAL.epoch)$('#operationsContent').innerHTML=portalError(error)}
}
if(typeof window!=='undefined'){window.addEventListener('focus',refreshOperationsCount);setInterval(function(){if(!document.hidden)refreshOperationsCount()},30000)}

/* Small, permission-aware integration workspace. Secrets and raw claims never
   enter this view; the server returns only sanitized provider state. */
var INTEGRATIONS={epoch:0};
function integrationStatusBadge(provider){
  var enabled=provider&&provider.enabled,configured=provider&&provider.configured;
  return '<span class="badge '+(enabled?'b-green':configured?'b-amber':'b-gray')+'">'+(enabled?'Etkin':configured?'Hazır':'Yapılandırılmadı')+'</span>';
}
function integrationProviderCard(provider){
  var sync=provider.last_sync, result=provider.last_result;
  var resultLabel=result==='COMPLETED'?'Tamamlandı':result==='FAILED'?'Başarısız':result==='RUNNING'?'Sürüyor':'Henüz çalışmadı';
  var last=sync?(portalDateTime(sync.completed_at||sync.started_at)):'—';
  return '<article class="card integration-provider"><div class="section-title"><div><div class="eyebrow">'+esc(provider.kind||'PROVIDER')+'</div><h2>'+esc(provider.label||provider.id)+'</h2></div>'+integrationStatusBadge(provider)+'</div><p class="caption">'+(provider.enabled?'Bu bağlantı, yalnızca sunucu yapılandırması üzerinden kullanılabilir.':provider.configured?'Yapılandırma bulundu; yönetici tarafından etkinleştirilebilir.':'Bu ortamda dış bağlantı kurulmaz.')+'</p><div class="integration-provider-meta"><span>Son eşitleme</span><strong>'+esc(last)+'</strong><span>Sonuç</span><strong>'+esc(resultLabel)+'</strong></div></article>';
}
function integrationSummary(data){
  var sync=data.last_sync,conflicts=Number(data.pending_conflicts||0),communication=data.communication||{},counts=communication.counts||{};
  var syncLabel=sync?(sync.status==='COMPLETED'?'Tamamlandı':sync.status==='RUNNING'?'Sürüyor':'Başarısız'):'—';
  return '<div class="grid kpis kpis-four portal-stats">'+
    kpi('Açık çatışma',conflicts,'Yönetici incelemesi bekleyen kimlik/alan farkı')+
    kpi('Son eşitleme',syncLabel,sync?(sync.users_seen+' kullanıcı görüldü'):'Henüz uygulanmış eşitleme yok')+
    kpi('Bekleyen teslim',counts.PENDING||0,'Harici bildirim kuyruğu')+
    kpi('Başarısız teslim',counts.FAILED||0,'Sınırlı yeniden deneme ile izlenir')+
    '</div>';
}
function integrationSyncActions(directory){
  var disabled=!(directory&&directory.enabled);
  return '<section class="card integration-sync"><div class="section-title"><div><div class="eyebrow">DİZİN EŞİTLEME</div><h2>Güvenli senkronizasyon</h2></div>'+
    '<span class="caption">Önce dry-run, sonra açıkça uygula</span></div><p>Dry-run hiçbir kullanıcı, organizasyon veya yetki kaydını değiştirmez. Uygulama yalnızca sunucu tarafında yapılandırılmış sağlayıcı ile yapılır.</p><div class="inline-actions"><button class="btn" data-integration="dry-run" '+(disabled?'disabled':'')+'>Dry-run çalıştır</button><button class="btn primary" data-integration="apply" '+(disabled?'disabled':'')+'>Eşitlemeyi uygula</button><span id="integrationSyncMessage" role="status"></span></div></section>';
}
function integrationIdentityMarkup(){
  return '<section class="card integration-identities"><div class="section-title"><div><div class="eyebrow">KİMLİK KAYNAKLARI</div><h2>Kullanıcı kimlik özeti</h2></div><span class="caption">Yalnızca güvenli özet</span></div><p class="caption">Kimlik kaynağı, organizasyon ve eşitleme durumu görünür; ham claims ve belirteçler gösterilmez.</p><label class="field"><span>Kullanıcı ara</span><input id="integrationIdentitySearch" type="search" maxlength="160" placeholder="Kullanıcı adı veya görünen ad"></label><div id="integrationIdentityList" class="integration-identity-list"></div><div id="integrationIdentityDetail" class="integration-identity-detail" aria-live="polite"></div></section>';
}
function integrationIdentityRows(items){
  if(!items||!items.length)return '<p class="caption">Eşleşen kullanıcı bulunamadı.</p>';
  return '<div class="table-wrap"><table class="request-table integration-identity-table"><thead><tr><th>Kullanıcı</th><th>Kimlik kaynağı</th><th>Organizasyon</th><th>Durum</th><th><span class="sr-only">İşlem</span></th></tr></thead><tbody>'+items.map(function(item){return '<tr><th scope="row">'+esc(item.display_name)+'<span class="request-table-category">'+esc(item.username)+'</span></th><td>'+esc((item.authentication_source||['LOCAL']).join(', '))+'</td><td>'+esc([item.organization,item.unit].filter(Boolean).join(' · ')||'Kayıt yok')+'</td><td>'+esc(item.active?'Aktif':'Pasif')+'</td><td><button class="btn sm" data-integration-user="'+Number(item.id)+'">Ayrıntıyı aç</button></td></tr>'}).join('')+'</tbody></table></div>';
}
async function renderIntegrationIdentities(){
  var host=$('#integrationIdentityList');if(!host)return;var epoch=INTEGRATIONS.epoch,search=$('#integrationIdentitySearch').value||'';host.innerHTML=portalSkeleton('Kimlikler yükleniyor');
  try{var data=await apiRequest('/api/integrations/users?limit=100&search='+encodeURIComponent(search));if(epoch!==INTEGRATIONS.epoch)return;host.innerHTML=integrationIdentityRows(data.items||[])}catch(error){if(epoch===INTEGRATIONS.epoch)host.innerHTML=portalError(error)}
}
function renderIntegrationIdentityDetail(data){
  var org=data.organization||{},manager=data.manager||{};return '<div class="integration-identity-detail-card"><div class="section-title"><h3>'+esc(data.display_name||data.username)+'</h3><button class="link-btn" data-integration-close>Gizle</button></div><dl class="integration-detail-grid"><div><dt>Kimlik kaynağı</dt><dd>'+esc((data.authentication_source||[]).join(', ')||'LOCAL')+'</dd></div><div><dt>Dış kimlik bağlı mı?</dt><dd>'+esc(data.external_identity_linked?'Evet':'Hayır')+'</dd></div><div><dt>Organizasyon</dt><dd>'+esc(org.name||org.unit||org.organization||'Kayıt yok')+'</dd></div><div><dt>Yönetici</dt><dd>'+esc(manager.display_name||'Atanmadı')+'</dd></div><div><dt>Eşitleme bağlantısı</dt><dd>'+esc((data.sync_status||{}).active_external_links?'Aktif':'Pasif / yok')+'</dd></div><div><dt>Son görülme</dt><dd>'+esc(portalDateTime((data.sync_status||{}).last_seen_at))+'</dd></div></dl></div>';
}
function renderIntegrationContent(host,data){
  var directory=(data.providers||[]).find(function(item){return item.id==='directory'})||{};
  host.innerHTML=integrationSummary(data)+'<section class="integration-provider-grid">'+(data.providers||[]).map(integrationProviderCard).join('')+'</section>'+integrationSyncActions(directory)+
    integrationIdentityMarkup()+'<section class="card integration-notes"><div class="section-title"><div><div class="eyebrow">GÜVENLİK</div><h2>Veri ve yetki sınırları</h2></div><span class="badge b-blue">Yerel çalışma</span></div><ul><li>Kimlik sağlayıcı sırları ve tokenlar arayüze gönderilmez.</li><li>Bilinmeyen dış grup veya pozisyon otomatik olarak yönetici rolü oluşturmaz.</li><li>Pasif kullanıcıların geçmiş talepleri ve audit kayıtları korunur.</li></ul></section>';
}
async function renderIntegrationsPanel(selector){
  var host=typeof selector==='string'?$(selector):selector;if(!host)return;
  var epoch=++INTEGRATIONS.epoch;host.innerHTML=portalSkeleton('Kurumsal entegrasyonlar yükleniyor');
  try{var data=await apiRequest('/api/integrations');if(epoch!==INTEGRATIONS.epoch)return;renderIntegrationContent(host,data);renderIntegrationIdentities()}
  catch(error){if(epoch===INTEGRATIONS.epoch)host.innerHTML=portalError(error)+'<button class="btn" data-integration="refresh">Yeniden yükle</button>'}
}
async function renderIntegrationsPage(){
  $('#appView').innerHTML='<div data-no-translate>'+pageHead('Kurumsal Entegrasyonlar','Kimlik, organizasyon ve isteğe bağlı iletişim bağlantılarının güvenli durumunu yönetin.')+'<div id="integrationsPageContent"></div></div>';
  renderIntegrationsPanel('#integrationsPageContent');
}
function integrationsRoute(route){
  if(route!=='portal-integrations')return false;
  if(!PORTAL.isAdmin){state.currentPage='submitter-home';return true}
  renderIntegrationsPage();return true;
}
document.addEventListener('click',function(event){
  var button=event.target.closest('[data-integration]');if(!button)return;
  var action=button.dataset.integration;
  if(action==='refresh'){renderIntegrationsPanel(button.closest('#integrationsPageContent')||'#portalAdminContent');return}
  if(action!=='dry-run'&&action!=='apply')return;
  var message=$('#integrationSyncMessage');button.disabled=true;
  apiRequest('/api/integrations/directory/sync',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({provider:'directory',dry_run:action==='dry-run',apply:action==='apply'})})
    .then(function(result){if(message)message.textContent=(action==='dry-run'?'Dry-run tamamlandı. ':'Eşitleme tamamlandı. ')+(result.summary&&result.summary.users_seen||0)+' kullanıcı görüldü.';renderIntegrationsPanel(button.closest('#integrationsPageContent')||'#portalAdminContent')})
    .catch(function(error){if(message)message.textContent=error.message;button.disabled=false});
});
document.addEventListener('input',function(event){if(event.target&&event.target.id==='integrationIdentitySearch'){clearTimeout(INTEGRATIONS.searchTimer);INTEGRATIONS.searchTimer=setTimeout(renderIntegrationIdentities,250)}});
document.addEventListener('click',function(event){
  var button=event.target.closest('[data-integration-user]');
  if(button){var detail=$('#integrationIdentityDetail');if(!detail)return;detail.innerHTML=portalSkeleton('Kimlik ayrıntısı yükleniyor');apiRequest('/api/integrations/users/'+Number(button.dataset.integrationUser)+'/identity').then(function(data){if(detail)detail.innerHTML=renderIntegrationIdentityDetail(data)}).catch(function(error){if(detail)detail.innerHTML=portalError(error)});return}
  if(event.target.closest('[data-integration-close]')){var detail=$('#integrationIdentityDetail');if(detail)detail.innerHTML='';}
});

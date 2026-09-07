from pathlib import Path
p=Path('app/static/js/app.js')
s=p.read_text(encoding='utf-8')
def between(start,end): return s[s.index(start):s.index(end)]
header='''/* TUSAŞ live portal: shared rendering, API access and accessible navigation. */
var state={currentRole:'submitter',currentPage:'submitter-home'};
var LIVE_AI={status:'checking',message:'Yapay zekâ bağlantısı kontrol ediliyor.',health:null};
// Request content and unsent drafts stay in memory only.
var LIVE_REQUEST={text:'',result:null,busy:false,error:''};
var DOC_INDEX={report:null,error:'',syncing:false,promise:null,timer:null,offset:0};
/* ---------------- SELECTORS / FORMATTERS ---------------- */
'''
helpers=between('function $(selector)','function currentPersona(')+between('function badge(text)','function sourceComposition(')+between('function navIcon(name)','function renderShell(')
helpers+='function renderShell(){return renderPortalShell()}\n'
routing='''/* ---------------- ROUTING ---------------- */
function render(){
  if(!PORTAL.user)state.currentPage='portal-login';
  else if(PORTAL.isAdmin&&state.currentPage!=='admin-panel'){state.currentPage='admin-panel';PORTAL.adminTab='requests'}
  else if(!PORTAL.isAdmin&&!/^(submitter-|portal-)/.test(state.currentPage))state.currentPage='submitter-home';
  renderShell();
  if(renderPortalRoute(state.currentPage))return;
  state.currentPage=PORTAL.user?(PORTAL.isAdmin?'admin-panel':'submitter-home'):'portal-login';
  renderPortalRoute(state.currentPage);
}
'''
documents=between('function paintDocumentIndex()','/* ---------------- MODALS')
documents=documents.replace('PDF bilgi kaynağı · Test paneli','Eğitim bilgi kaynakları').replace('Bu dosya listesi geliştirme ve test içindir; son kullanıcı ekranının parçası olmayacaktır.','Yalnızca aramada hazır dosyalar yeni analizlerde kullanılır. Değişen içerikleri eşitleyerek bilgi havuzunu güncel tutun.')
modals=between('var lastFocus=null;','function openSignalDetail(')
events='''document.addEventListener('click',function(event){
  var pageButton=event.target.closest('[data-page]');
  if(pageButton){
    if(pageButton.dataset.page==='admin-panel'){PORTAL.adminTab='requests';PORTAL.filter='';PORTAL.search='';PORTAL.offset=0}
    state.currentPage=pageButton.dataset.page;render();focusPageStart();return;
  }
  var button=event.target.closest('[data-action]');if(!button)return;
  var action=button.dataset.action;
  if(action==='retry-ai'){checkAIHealth(true);return}
  if(action==='documents-prev'||action==='documents-next'){
    DOC_INDEX.offset=Math.max(0,DOC_INDEX.offset+(action==='documents-next'?20:-20));
    loadDocumentStatus().catch(function(error){DOC_INDEX.error=error.message;paintDocumentIndex()});return;
  }
  if(action==='sync-documents'){ensureDocumentIndex().then(function(){toast('PDF klasörü güncel. Yeni analizler hazır dosyaları kullanacak.')}).catch(function(error){toast(error.message)});return}
  if(action==='close-modal'){closeModal();return}
  if(action==='print')window.print();
});
'''
navigation=between('function setMobileMenu(open)','/* ---------------- INIT')
init="document.addEventListener('DOMContentLoaded',function(){initPortal()});\n"
p.write_text(header+helpers+routing+documents+modals+events+navigation+init,encoding='utf-8')
print('Live application core:',len(s),'->',p.stat().st_size,'bytes; synthetic data/renderers removed.')

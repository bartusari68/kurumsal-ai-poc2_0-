from pathlib import Path
p=Path('app/static/js/portal.js')
s=p.read_text(encoding='utf-8')
start=s.index('function renderPortalLogin()')
end=s.index('function renderPortalShell()',start)
s=s[:start]+'''function renderPortalLogin(){
  $('#appView').innerHTML=renderExperienceLogin();
  bindExperienceLogin({
    authenticate:function(credentials){return apiRequest('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials)})},
    onAuthenticated:function(session){clearPortalAccount();acceptPortalSession(session);render();if(!PORTAL.isAdmin)checkAIHealth()}
  });
}
'''+s[end:]
start=s.index('function renderPortalShell()')
end=s.index('function renderPortalRoute(',start)
block=s[start:end]
block=block.replace("if(guest){$('#sidebar').innerHTML='';return}","if(guest){$('#sidebar').innerHTML='';enhanceExperienceShell({user:null,page:state.currentPage,admin:false});return}")
block=block.replace("'Yönetici Paneli'","'Çalışma Merkezi'")
block=block.replace('  renderAIConnectionStatus();','  renderAIConnectionStatus();\n  enhanceExperienceShell({user:PORTAL.user,page:state.currentPage,admin:PORTAL.isAdmin});')
s=s[:start]+block+s[end:]
s=s.replace('/* Live employee portal. Demonstration screens remain separate and admin-only. */','/* Account-scoped live employee and manager workspaces. */')
p.write_text(s,encoding='utf-8')

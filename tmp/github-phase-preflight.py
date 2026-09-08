import json,os,subprocess,urllib.request
settings=os.environ.copy();settings['GIT_TERMINAL_PROMPT']='0';settings['GCM_INTERACTIVE']='never'
result=subprocess.run(['git','-c','safe.directory=C:/Users/Administrator/Desktop/kurumsal-ai-poc','credential','fill'],input='protocol=https\nhost=github.com\n\n',capture_output=True,text=True,env=settings,check=True)
credential=dict(line.split('=',1) for line in result.stdout.splitlines() if '=' in line)
request=urllib.request.Request('https://api.github.com/repos/bartusari68/kurumsal-ai-poc2_0-',headers={'Authorization':'Bearer '+credential['password'],'Accept':'application/vnd.github+json','User-Agent':'kurumsal-ai-phase-publish'})
with urllib.request.urlopen(request,timeout=20) as response: data=json.load(response)
report={'repository':data['full_name'],'private':data['private'],'can_push':data.get('permissions',{}).get('push'),'default_branch':data['default_branch']}
print(json.dumps(report))
if not report['private']:raise RuntimeError('Repository is not private; publishing stopped')
if not report['can_push']:raise RuntimeError('Repository write permission is unavailable')

from pathlib import Path
p=Path('app/static/css/experience.css')
s=p.read_text(encoding='utf-8')
a=s.index('.experience-stars{');b=s.index('.experience-space-light{',a)
s=s[:a]+'.experience-starfield{position:absolute;inset:0;opacity:.48}.experience-starfield img{width:100%;height:100%;object-fit:cover;display:block}\n'+s[b:]
a=s.index('/* The authenticated page');b=s.index('/* Bright,',a)
s=s[:a]+'''/* Move the actual login composition towards the viewer, revealing the workspace. */
.experience-entry{position:fixed;inset:0;z-index:var(--z-transition);pointer-events:none;overflow:hidden;background:#040913;transform-origin:74% 48%;will-change:transform,opacity;animation:experience-entry-zoom 800ms cubic-bezier(.25,.65,.25,1) forwards}
.experience-entry>.experience-login{width:100%;height:100%;margin:0;pointer-events:none}
.experience-entry .experience-earth-canvas{transition:none;opacity:1}
@keyframes experience-entry-zoom{0%{transform:scale(1) translateZ(0);opacity:1}40%{opacity:1}100%{transform:scale(1.65) translateZ(0);opacity:0}}

'''+s[b:]
s+='''
/* High-resolution maps remain crisp; reserve the right-hand panel for entry. */
.experience-earth-fallback{transform:none;object-fit:cover}
.experience-auth{backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)}
@media(min-width:721px){
  .experience-auth{border-radius:16px;background:linear-gradient(145deg,#142038ed,#091220f5);border-color:#9bb4da32;box-shadow:0 24px 80px #00000035}
  .experience-login-layout{grid-template-columns:minmax(0,1fr) minmax(340px,410px);gap:clamp(30px,6vw,100px)}
  .experience-planet-scene{width:clamp(1000px,105vw,1820px);height:clamp(1000px,105vw,1820px);left:clamp(-280px,-17vw,-180px);top:-85px}
  .experience-story-copy{padding:16px 0 0;max-width:420px}
  .experience-story-copy>p{color:#e0e8f6}.experience-story h1{font-weight:500}
}
@media(min-width:1700px){.experience-planet-scene{left:-340px;top:-125px}}
@media(min-width:721px) and (max-width:1050px){.experience-planet-scene{left:-335px;top:-45px;width:1150px;height:1150px}}
@media(max-width:720px){.experience-entry{transform-origin:50% 65%}.experience-auth{border-radius:12px}.experience-starfield{opacity:.32}}
@media(prefers-reduced-motion:reduce){.experience-entry{display:none;animation:none}.experience-earth-canvas{transition:none}}
'''
p.write_text(s,encoding='utf-8')
# The case-specific overrides follow the existing general workflow styles.
p=Path('app/static/css/workflow.css');s=p.read_text(encoding='utf-8')
if s.startswith('.case-breadcrumb'):
    end=s.index('\n/*')
    s=s[end:]+'\n'+s[:end]
    p.write_text(s,encoding='utf-8')
p=Path('app/static/index_tusas_faz31.html');s=p.read_text(encoding='utf-8');p.write_text(s.replace('20260907-5','20260907-6'),encoding='utf-8')

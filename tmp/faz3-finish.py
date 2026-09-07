from pathlib import Path
p=Path('app/static/js/portal.js');s=p.read_text(encoding='utf-8')
s=s.replace("analyst?'Analiz bekliyor':'Birimde bekliyor',analyst?(summary.IN_REVIEW||0):(summary.REFERRED||0)", "'Aksiyon bekliyor',summary.actionable!=null?summary.actionable:(analyst?(summary.IN_REVIEW||0):(summary.REFERRED||0))")
s=s.replace("owner=(item.current_owner||{}).label||(item.status==='REFERRED'?item.department_label:config.owner)", "owner=(item.current_owner||{}).label||'Aksiyon sahibi bilgisi mevcut değil'")
s=s.replace("esc((process.current_owner||{}).label||config.owner)", "esc((process.current_owner||{}).label||'Aksiyon sahibi bilgisi mevcut değil')")
s=s.replace("esc((process.next_action||{}).label||config.next)", "esc((process.next_action||{}).label||'Beklenen işlem bilgisi mevcut değil')")
p.write_text(s,encoding='utf-8')

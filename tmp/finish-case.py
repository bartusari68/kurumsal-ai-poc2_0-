from pathlib import Path
p=Path('app/static/js/portal.js');s=p.read_text(encoding='utf-8')
s=s.replace("foreground=admin&&portalReviewAlreadyRecorded(result)","foreground=admin&&(portalReviewAlreadyRecorded(result)||!(result.permissions||{}).can_review||result.status==='RESOLVED')")
s=s.replace("var selectedDepartment=!approved?$('#decisionDepartment').value:routing.department,useExisting=", "var selectedDepartment=(!approved?$('#decisionDepartment').value:routing.department)||(routing.auto_selected?routing.department:null),useExisting=")
p.write_text(s,encoding='utf-8')

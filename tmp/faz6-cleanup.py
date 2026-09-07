from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=root/'app/operations.py';s=p.read_text(encoding='utf-8');a=s.index('def visibility_condition(');b=s.index('def can_see(',a);s=s[:a]+s[b:]
s=s.replace('from datetime import timedelta','from datetime import datetime, timedelta').replace("__import__('datetime').datetime.fromisoformat",'datetime.fromisoformat')
s=s.replace("'action_required': actions[0]['label'], 'last_action': last.note if last else None,", "'action_required': actions[0]['label'],")
s=s.replace("if assignee is None and assignment and assignment.responsible_scope == scope:", "if 'assignee_id' not in details and 'after' not in details and assignee is None and assignment and assignment.responsible_scope == scope:")
p.write_text(s,encoding='utf-8')
p=root/'app/models.py';s=p.read_text(encoding='utf-8');s=s.replace('DecisionAnalysisLink, RequestSubmission):', 'DecisionAnalysisLink, RequestSubmission, DelegationAudit, EscalationRecord):');p.write_text(s,encoding='utf-8')
p=root/'tests/test_workflow_core.py';s=p.read_text(encoding='utf-8');s=s.replace('patch("app.workflow_core.datetime") as clock:', 'patch("app.workflow_core.utc_now") as clock:').replace('clock.utcnow.return_value = datetime.utcnow() + timedelta(minutes=2)', 'clock.return_value = __import__("app.time_policy", fromlist=["utc_now"]).utc_now() + timedelta(minutes=2)');p.write_text(s,encoding='utf-8')

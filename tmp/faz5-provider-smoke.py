"""No request/DB creation, no local PDFs; synthetic intake text only."""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.intake import clarify, ai, IntakeOutput
from app.schemas import IntakeRequest
from fastapi import HTTPException

async def main():
    report = []
    original_call = ai.chat_json
    async def checked_call(*args, **kwargs):
        value = await original_call(*args, **kwargs)
        try:
            IntakeOutput.model_validate(value)
        except Exception as error:
            print(json.dumps({'validation': error.errors(include_input=False, include_context=False)}, ensure_ascii=False), flush=True)
            Path('tmp/faz5-synthetic-invalid.json').write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        return value
    ai.chat_json = checked_call
    for case, message in [
        ('clear', 'Sentetik yazılım testi: Haftalık Excel raporları için 5 dosyayı elle birleştiriyorum. Power Query ile birleştirmeyi otomatikleştirmek istiyorum. Temel Excel biliyorum; yalnızca kendi raporlarım için bu eğitimi talep ediyorum.'),
        ('vague', 'Sentetik yazılım testi: Excel eğitimi istiyorum.')]:
        try:
            result = await clarify(IntakeRequest(message=message), 'synthetic-provider-test')
            report.append({'case': case, 'status': result['status'], 'questions': result['question_count'],
                           'draft_length': len(result['draft'] or ''), 'question': result['question'], 'context': result['context']})
            if case == 'vague' and result['status'] == 'needs_more_info':
                followup = await clarify(IntakeRequest(token=result['token'], message='Haftalık rapor için dosyaları elle birleştiriyorum. Power Query ile otomatik birleştirme yapmak istiyorum.'), 'synthetic-provider-test')
                report[-1]['after_answer'] = {'status': followup['status'], 'questions': followup['question_count'], 'draft_length': len(followup['draft'] or '')}
        except HTTPException as error:
            report.append({'case': case, 'http_status': error.status_code, 'safe_error': error.detail})
        print(json.dumps(report[-1], ensure_ascii=False), flush=True)
    Path('tmp/faz5-provider-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

asyncio.run(main())

"""Built-in templates. No institution-specific delayed follow-up is assumed."""
from copy import deepcopy
from .utils import json_loads

OUTCOMES={'RESOLVED':'Tamamen karşılandı','PARTIALLY_RESOLVED':'Kısmen karşılandı','NOT_RESOLVED':'Karşılanmadı'}
PROGRESS={'NONE':'Gelişmedi','PARTIAL':'Kısmen gelişti','CLEAR':'Belirgin gelişti'}
SOURCES={'PARTICIPANT':'Katılımcı','AUTHORIZED_REVIEWER':'Yetkili değerlendirici'}
STATES={'PENDING':'Değerlendirme bekliyor','COMPLETED':'Değerlendirme tamamlandı'}
TEMPLATES={
 'FEEDBACK':{'title':'Katılımcı geri bildirimi','timing':'immediate','description':'Eğitimin ihtiyacınıza katkısını kendi deneyiminize göre değerlendirin.','questions':[
  {'id':'relevance','type':'rating','label':'İçerik ihtiyacınıza uygun muydu?','min':1,'max':5},
  {'id':'expectations','type':'rating','label':'Beklenen kazanımları karşıladı mı?','min':1,'max':5},
  {'id':'applicability','type':'rating','label':'İçerik işinizde uygulanabilir miydi?','min':1,'max':5},
  {'id':'overall','type':'rating','label':'Genel değerlendirmeniz','min':1,'max':5},
  {'id':'comment','type':'free_text','label':'Açıklamanız','required':False,'max_length':3000}]},
 'LEARNING':{'title':'Katılımcı öz değerlendirmesi','timing':'immediate','description':'Öncesine kıyasla ilerlemenizi belirtin. Bu bildirim bir sınav sonucu veya yetkinlik belgesi değildir.','questions':[]},
 'APPLICATION':{'title':'İşe uygulama / ihtiyaç sonucu','timing':'delayed','description':'Başlangıç ihtiyacının ne ölçüde karşılandığını belirtin. Bu kayıt talebi kendiliğinden kapatmaz.','questions':[
  {'id':'application','type':'single_choice','label':'Öğrendiklerinizi işinizde kullanabildiniz mi?','options':{'YES':'Evet','PARTLY':'Kısmen','NO':'Hayır','NOT_YET':'Henüz uygulama fırsatım olmadı'}},
  {'id':'problem_persists','type':'single_choice','label':'Başlangıç problemi devam ediyor mu?','options':{'YES':'Evet','PARTLY':'Kısmen','NO':'Hayır'}},
  {'id':'outcome','type':'outcome_rating','label':'Başlangıçtaki ihtiyacınız ne ölçüde karşılandı?','options':OUTCOMES},
  {'id':'comment','type':'free_text','label':'Gözleminiz / açıklamanız','required':False,'max_length':3000}]}
}
# Optional deployment configuration, e.g. {'APPLICATION': timedelta(...)}.
# Empty means no automatic delayed follow-up. Manual scheduling remains available.
FOLLOW_UP_DELAYS={}
MIN_PERCENT_SAMPLE=5
REPEATED_SIGNAL_COUNT=2  # A descriptive repeated observation, never an automatic decision.


def template(kind,version):
    value=deepcopy(TEMPLATES[kind]);value.update(code=kind,revision=1)
    if kind=='LEARNING':
        value['questions']=[{'id':f'outcome_{i}','outcome_id':row.get('id'),'type':'single_choice',
            'label':row['text'],'options':PROGRESS} for i,row in enumerate(json_loads(version.outcomes_json,[]))]
        value['questions'].append({'id':'comment','type':'free_text','label':'Açıklamanız','required':False,'max_length':3000})
    return value

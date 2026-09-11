"""Explainable planning rules; no ranking, investment or employee decisions."""
from .position_policy import MIN_AGGREGATE_USERS, require_manager
from .evaluation_policy import MIN_PERCENT_SAMPLE, REPEATED_SIGNAL_COUNT

SCOPE = 'ORGANIZATION'
STATES = {'OPEN': 'Açık', 'UNDER_REVIEW': 'İncelemede', 'DECIDED': 'Karar kaydedildi', 'CLOSED': 'Kapalı'}
TRANSITIONS = {'REVIEW': ('OPEN', 'UNDER_REVIEW', 'İncelemeye al'),
               'DECIDE': ('UNDER_REVIEW', 'DECIDED', 'Kararı kaydet'),
               'CLOSE': ('DECIDED', 'CLOSED', 'Planlama konusunu kapat')}
DECISIONS = {'NO_ACTION': 'İşlem gerekmiyor', 'MONITOR': 'İzlemeye devam',
             'CREATE_NEW_LEARNING_NEED': 'Yeni eğitim ihtiyacı',
             'START_COURSE_ENRICHMENT': 'İçerik zenginleştirme',
             'PLAN_ADDITIONAL_SESSIONS': 'Ek eğitim oturumu planlama'}
HANDOFFS = {'CREATE_NEW_LEARNING_NEED': 'REQUEST', 'START_COURSE_ENRICHMENT': 'DEVELOPMENT',
            'PLAN_ADDITIONAL_SESSIONS': 'SESSION'}
SIGNALS = {'CONTENT_GAP': 'İçerik kapsamı yok', 'CONTENT_IMPROVEMENT': 'İçerik inceleme sinyali',
           'CAPACITY_SIGNAL': 'Planlı kapasite incelemesi', 'DEMAND_SIGNAL': 'Talep mevcut',
           'REPEATED_NEED': 'Eğitim sonrası tekrarlayan ihtiyaç', 'HEALTHY_COVERAGE': 'Olumlu kapsam ve sonuç',
           'INSUFFICIENT_DATA': 'Sonuç verisi yetersiz'}

def disclosed(count, people):
    return count if count == 0 or people >= MIN_AGGREGATE_USERS else None

def partition(rows):
    """Suppress the whole partition, including totals, if subtraction exposes a small cell."""
    return all(r['people'] >= MIN_AGGREGATE_USERS for r in rows if r['count'])

def classify(row, generated_at):
    signals = []
    def add(kind, explanation, version=None):
        signals.append({'type': kind, 'label': SIGNALS[kind], 'skill_id': row['skill_id'],
            'course_version_id': version, 'scope': SCOPE, 'generated_at': generated_at,
            'explanation': explanation, 'evidence_counts': {
                'planned_profiles': row['planned_profiles'], 'observed_needs': row['observed_needs'],
                'open_needs': row['open_needs'], 'published_versions': row['published_versions']},
            'source_references': {'skill_id': row['skill_id'], 'position_revision_ids':row['planned_revision_ids'],
                'collections':['request_skill_needs','course_skill_mappings','training_enrollments','learning_evaluations'],
                'course_version_ids': [version] if version else [v['id'] for v in row['catalog']]}})
    demand = row['planned_profiles'] > 0 or (row['observed_needs'] or 0) > 0
    if demand: add('DEMAND_SIGNAL', 'Pozisyon gereksinimleri ve doğrulanmış talepler ayrı kaynaklar olarak izlenir.')
    if demand and not row['published_versions']: add('CONTENT_GAP', 'Talep kaynağı mevcut; bu yetkinliğe bağlı güncel yayımlanmış ders sürümü yok.')
    if (row['open_needs'] or 0) > 0 and row['published_versions'] and row['training']['upcoming_sessions'] == 0:
        add('CAPACITY_SIGNAL', 'Açık ihtiyaç ve yayımlanmış içerik var; gelecekte başlayacak planlanmış oturum yok. Talep sayısı katılımcı sayısı değildir.')
    if (row['repeated_needs'] or 0) > 0:
        add('REPEATED_NEED', 'Aynı kişinin aynı yetkinlik için eğitim tamamlandıktan sonra açtığı yeni ihtiyaçlar var. Eğitim başarısızlığı sonucu çıkarılmaz.')
    sufficient = False
    for v in row['catalog']:
        for outcome in v['outcomes']:
            if outcome['state'] != 'SUFFICIENT': continue
            sufficient = True
            negative = sum(outcome['distribution'].get(k, 0) for k in ('PARTIALLY_RESOLVED', 'NOT_RESOLVED', 'NONE'))
            if negative >= REPEATED_SIGNAL_COUNT:
                add('CONTENT_IMPROVEMENT', f"Sürüm {v['version_number']}: {outcome['source_label']} / {outcome['type_label']} içinde tekrarlayan düşük sonuç bildirimi. Yalnızca bu sürüme aittir.", v['id'])
    current = [v for v in row['catalog'] if v['current']]
    if not current or any(not v['outcomes'] or any(o['state']!='SUFFICIENT' for o in v['outcomes']) for v in current):
        add('INSUFFICIENT_DATA', f'Güncel sürüm ve değerlendirme türü başına en az {MIN_PERCENT_SAMPLE} farklı katılımcı ve açıklanabilir hücreler gereklidir; gizlenen veri olumlu sonuç sayılmaz.')
    if sufficient and row['published_versions'] and row['open_needs'] == 0 and row['repeated_needs'] == 0 and not any(s['type'] == 'CONTENT_IMPROVEMENT' for s in signals):
        if current and all(v['outcomes'] and all(o['state'] == 'SUFFICIENT' and o['type'] == 'APPLICATION' and o['distribution'].get('RESOLVED', 0) == o['count'] for o in v['outcomes'] if o['type'] == 'APPLICATION') and any(o['type'] == 'APPLICATION' and o['state'] == 'SUFFICIENT' for o in v['outcomes']) for v in current):
            add('HEALTHY_COVERAGE', 'Güncel içerikte yeterli işe uygulama sonucu olumlu; açıklanabilir açık ihtiyaç veya tekrarlayan ihtiyaç sinyali yok. Kapsam garantisi değildir.')
    return signals

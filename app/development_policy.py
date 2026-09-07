"""Learning design lifecycle; deliberately separate from request resolution."""
from .workflow_policy import DEPARTMENTS

WORK_TYPES = {'NEW_COURSE': 'Yeni ders', 'COURSE_ENRICHMENT': 'Ders zenginleştirme'}
STATES = {
    'DRAFT': {'label': 'Başlangıç taslağı', 'editable': True, 'terminal': False, 'next': 'İhtiyacı ve tasarım kapsamını incele'},
    'ANALYSIS': {'label': 'Kapsam analizi', 'editable': True, 'terminal': False, 'next': 'Tasarım brief’ini netleştir'},
    'DESIGN': {'label': 'İçerik tasarımı', 'editable': True, 'terminal': False, 'next': 'Kazanımları ve içerik taslağını hazırla'},
    'REVIEW': {'label': 'İnceleme bekleniyor', 'editable': False, 'terminal': False, 'next': 'Tasarımı incele ve kararını kaydet'},
    'READY': {'label': 'Tasarım çıktısı hazır', 'editable': False, 'terminal': True, 'next': 'Tasarım uygulamaya hazır; talebin çözümü ayrıca doğrulanır'},
    'CANCELLED': {'label': 'Çalışma iptal edildi', 'editable': False, 'terminal': True, 'next': 'Çalışma sonlandırıldı'},
}
EDITABLE = tuple(state for state, spec in STATES.items() if spec['editable'])
TERMINAL = tuple(state for state, spec in STATES.items() if spec['terminal'])
EVENT_LABELS = {'CREATED': 'Eğitim geliştirme işi oluşturuldu', 'EDIT': 'Tasarım içeriği kaydedildi',
    'START_ANALYSIS': 'Kapsam analizi başlatıldı', 'START_DESIGN': 'İçerik tasarımı başlatıldı',
    'SUBMIT_REVIEW': 'İncelemeye gönderildi', 'APPROVE': 'Tasarım çıktısı hazır olarak onaylandı',
    'REQUEST_REVISION': 'Düzeltme istendi', 'ASSIGN': 'Sorumluluk ve hedef tarihi güncellendi',
    'CANCEL': 'Çalışma iptal edildi'}
ACTIONS = {
    'START_ANALYSIS': {'label': 'Kapsam analizine başla', 'sources': ('DRAFT',), 'target': 'ANALYSIS', 'required': ('summary',)},
    'START_DESIGN': {'label': 'İçerik tasarımına başla', 'sources': ('ANALYSIS',), 'target': 'DESIGN', 'required': ('summary', 'target_output')},
    'SUBMIT_REVIEW': {'label': 'İncelemeye gönder', 'sources': ('DESIGN',), 'target': 'REVIEW', 'required': ('summary', 'target_output', 'outcomes', 'modules', 'enrichment_changes')},
    'APPROVE': {'label': 'Tasarımı hazır olarak onayla', 'sources': ('REVIEW',), 'target': 'READY', 'required': ('review_snapshot',)},
    'REQUEST_REVISION': {'label': 'Düzeltme iste', 'sources': ('REVIEW',), 'target': 'DESIGN', 'required': ('note',)},
    'ASSIGN': {'label': 'Sorumlu ve hedef tarihi kaydet', 'sources': (*EDITABLE, 'REVIEW'), 'target': None, 'required': ()},
    'CANCEL': {'label': 'Çalışmayı iptal et', 'sources': (*EDITABLE, 'REVIEW'), 'target': 'CANCELLED', 'required': ('note',)},
}
for rule in ACTIONS.values():
    rule.update(roles=tuple(DEPARTMENTS), owner='responsible_unit_and_optional_assignee', terminal=rule['target'] in TERMINAL)


def available(item, principal, can_act):
    return [dict(code=code, **rule) for code, rule in ACTIONS.items()
            if can_act and principal.role in rule['roles'] and item.state in rule['sources']]

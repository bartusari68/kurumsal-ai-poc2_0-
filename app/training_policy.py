"""Single lifecycle and capability vocabulary, independent of content publication."""
from .portal_auth import ROLES, MANAGERS

STATES = {'DRAFT': 'Taslak', 'SCHEDULED': 'Planlandı', 'IN_PROGRESS': 'Devam ediyor',
          'COMPLETED': 'Tamamlandı', 'CANCELLED': 'İptal edildi'}
MODES = {'IN_PERSON': 'Yüz yüze', 'ONLINE': 'Çevrim içi', 'HYBRID': 'Hibrit'}
ATTENDANCE = {'UNKNOWN': 'Henüz girilmedi', 'ATTENDED': 'Katıldı', 'ABSENT': 'Katılmadı', 'EXCUSED': 'Mazeretli'}
COMPLETION = {'PENDING': 'Bekliyor', 'COMPLETED': 'Tamamladı', 'NOT_COMPLETED': 'Tamamlamadı'}
TRANSITIONS = {
    'SCHEDULE': {'from': ('DRAFT',), 'to': 'SCHEDULED', 'label': 'Oturumu planla'},
    'START': {'from': ('SCHEDULED',), 'to': 'IN_PROGRESS', 'label': 'Eğitimi başlat'},
    'COMPLETE': {'from': ('IN_PROGRESS',), 'to': 'COMPLETED', 'label': 'Oturumu tamamla'},
    'CANCEL': {'from': ('DRAFT','SCHEDULED','IN_PROGRESS'), 'to': 'CANCELLED', 'label': 'Oturumu iptal et'},
}
CAPABILITIES = {'edit': ('DRAFT','SCHEDULED'), 'enroll': ('DRAFT','SCHEDULED'),
    'attendance': ('IN_PROGRESS','COMPLETED'), 'completion': ('IN_PROGRESS','COMPLETED')}
EVENTS = {'CREATED': 'Eğitim oturumu oluşturuldu', 'EDIT': 'Oturum bilgileri güncellendi',
    'RESCHEDULED': 'Eğitim zamanı değiştirildi', 'TRAINER_CHANGED': 'Eğitmen değiştirildi',
    'ENROLLED': 'Katılımcı kaydedildi', 'REMOVED': 'Katılımcı kaydı kaldırıldı',
    'ATTENDANCE': 'Devam bilgileri kaydedildi', 'FINALIZE_ATTENDANCE': 'Devam bilgileri kesinleştirildi',
    'COMPLETION': 'Tamamlanma bilgileri kaydedildi',
    **{code: rule['label'] for code, rule in TRANSITIONS.items()}}
EVENTS.update({'SCHEDULE':'Oturum planlandı', 'START':'Eğitim başladı',
               'COMPLETE':'Oturum tamamlandı', 'CANCEL':'Oturum iptal edildi'})
NOTICE_TITLES = {'START':'Devam bilgileri bekleniyor',
                'FINALIZE_ATTENDANCE':'Tamamlanma işlemi bekleniyor'}


def capabilities(row, authorized):
    return {name: authorized and row.status in states for name, states in CAPABILITIES.items()}


def actions(row, authorized):
    return [{'code': code, 'label': rule['label']} for code, rule in TRANSITIONS.items()
            if authorized and row.status in rule['from']]

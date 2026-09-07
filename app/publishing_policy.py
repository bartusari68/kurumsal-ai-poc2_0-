"""Catalog publication permissions and lifecycle, independent of design states."""
from .workflow_policy import DEPARTMENTS
STATES = {'DRAFT': 'Ders taslağı', 'READY_FOR_PUBLISH': 'Yayınlamaya hazır',
          'PUBLISHED': 'Yayında', 'ARCHIVED': 'Önceki sürüm'}
ACTIONS = {
    'PREPARE': {'label': 'Yayınlamaya hazırla', 'source': 'DRAFT', 'target': 'READY_FOR_PUBLISH'},
    'RETURN_DRAFT': {'label': 'Taslağa geri al', 'source': 'READY_FOR_PUBLISH', 'target': 'DRAFT'},
    'PUBLISH': {'label': 'Yayınla', 'source': 'READY_FOR_PUBLISH', 'target': 'PUBLISHED'},
}
for rule in ACTIONS.values():
    rule['roles'] = tuple(DEPARTMENTS)
EVENTS = {'CREATED': 'Ders sürümü taslağı oluşturuldu', 'EDIT': 'Katalog bilgileri güncellendi',
    'PREPARE': 'Ders sürümü yayınlamaya hazırlandı', 'RETURN_DRAFT': 'Yayın hazırlığı taslağa alındı',
    'PUBLISH': 'Ders sürümü yayımlandı', 'ARCHIVE': 'Önceki ders sürümü arşivlendi',
    'DOCUMENT_LINKED': 'PDF kaynağı ders sürümüne bağlandı', 'LEGACY': 'Mevcut katalog kaydı sürüm geçmişine alındı'}

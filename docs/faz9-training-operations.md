# Faz 9 — Eğitim operasyonları

Yayımlanmış güncel CourseVersion üzerinden bağımsız TrainingSession oluşturulur.
İçerik sürümü SQL guard ile sabittir; yeni katalog yayını oturumu değiştirmez.
Eski sürümde planlanmış oturum, sürüm arşivlense de devam eder.

## Yetki ve yaşam döngüsü

Merkezi `training_policy.py`: DRAFT → SCHEDULED → IN_PROGRESS → COMPLETED.
DRAFT, SCHEDULED ve IN_PROGRESS gerekçeyle CANCELLED olabilir. İptal edilen
oturumda operasyon ve katılımcı sonucu kaydedilemez.

Mevcut yönetici rollerinden sorumlu birim oturumu yönetir. Katalogda birim
biliniyorsa başka birim oturum açamaz. Eski katalogda birim bilinmiyorsa yetkili
kullanıcı kendi mevcut rol kapsamını kullanır. Koordinatör atanırsa operasyonu
o kişi veya geçerli vekili yürütür. İhtiyaç analizi diğer birimlerin oturumlarını
okuyabilir. Eğitmen ilişkisi yeni yönetici yetkisi vermez. Çalışan yalnızca kendi
katılımını görür; diğer katılımcıların kayıtları ve özel audit detayları gizlidir.
Vekâlet aynı rol/organizasyon ve geçerlilik süresi kontrollerini reuse eder.

Taslakta eğitmen ve tarihler boş olabilir. Planlamak için eğitmen, başlangıç,
bitiş ve eğitim biçimine uygun fiziksel konum/bağlantı gerekir. İç eğitmen mevcut
aktif kullanıcıdır; dış eğitmen yalnızca görüntüleme bilgisidir. Sahte hesap yoktur.

## Kayıt ve sonuç

Enrollment üzerinde session/user unique constraint vardır. Kapasite boşsa
sınırsızdır. Oturum record-version CAS kilidi kayıt, düzenleme, devam ve
tamamlanma işlemlerini aynı transaction içinde sıralar. SQL kapasite trigger'ları
ek koruma sağlar. Toplu sonuç girişinde her enrollment sürümü ayrıca kontrol
edilir; tek bir stale satır tüm işlemi geri alır.

Devam ile tamamlanma ayrıdır. Devam kesinleştirilmeden ve aktif katılımcıların
tamamlanma durumu belirtilmeden oturum tamamlanamaz. Sonradan devam düzeltmesi
kesinleştirme tarihini temizler; tekrar kesinleştirme İşlerim'e düşer.
Completion bir yetkinlik değerlendirmesi değildir ve RequestWorkflow'u kapatmaz.
Kaynak talep isteğe bağlıdır; seçilirse katılımcıya ait ve operatörün erişimine
açık olmalıdır. CourseVersion'ın kaynak karar/geliştirme zinciri ve enrollment'ın
kendi kaynak ihtiyacı ayrıca korunur.

## Bildirim, migration ve mevcut borç

Dört additive tablo: training_sessions, training_enrollments, training_events,
training_notifications. Eski tablolar yeniden oluşturulmaz, eski veri dönüştürülmez.
DDL ve guard kurulumu idempotenttir. Eğitim bildirimi için sahte Request/RequestEvent
oluşturulmaz; companion bildirim tablosu aynı Bildirimler/okunmamış sayaç/okundu
altyapısına bağlanır. Yerel bildirim, oturum olayıyla aynı transaction'da yazılır;
event+recipient unique constraint ve on-conflict duplicate koruması kullanılır.
Bildirimler API'sinde eğitim bildirimlerinin kimliği negatif, mevcut bildirimlerin
kimliği pozitiftir. Birleşik bildirim sıralama ve pagination SQL UNION üzerinden yapılır.

Birleşik İşlerim kuyruğunun son yetki/aksiyon filtresi ve pagination'ı Python'da
kalır. Mevcut request/development/publication aksiyon politikalarını SQL'de tekrar
ifade etmek bu fazın düşük riskli optimizasyon sınırını aştığı için taşınmadı.
Eğitim operasyonları listesinin yetki, durum, gün, arama ve pagination'ı SQL'dedir.

Saatler mevcut UTCDateTime ile UTC tutulur; tarih filtresi kurumun UTC+03:00
takvim günüdür. Form tarayıcının yerel saatini açık UTC zamanına dönüştürür.

İzole sentetik testler gerçek PDF'leri ve API anahtarlarını dış servise göndermez.
Gerçek veritabanına sentetik oturum veya eğitim kaydı eklenmez.

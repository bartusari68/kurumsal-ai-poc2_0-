# Faz 14 — Learning Governance + Policy

Faz 14, mevcut katalog ve eğitim akışına eklenen yönetişim katmanıdır. Ders
yayın sürümleri değişmez; sahiplik, inceleme zamanı ve aktif/emekli yaşam
döngüsü `course_governance` tablosunda tutulur. İnceleme başlatıldığında dersin
mevcut sürümü tek seferlik anlık görüntü olarak kaydedilir; insan kararı ve
gerekçesi `governance_reviews` / `governance_events` geçmişinde saklanır.

Zorunlu eğitim politikaları yalnızca mevcut `PositionProfile` kayıtlarına ve
yayımlanmış derslere bağlanabilir. Değişiklik yeni bir politika sürümüdür;
geçmiş sürümler silinmez. Pozisyon ataması veya çalışanın “Zorunlu
Eğitimlerim” görünümü, aktif politika sürümünden `LearningRequirement` üretir.
Gereksinim yalnızca eşleşen ders sürümüne bağlı, iptal edilmemiş bir oturumun
tamamlanmış `Enrollment` kaydıyla karşılanır; otomatik kayıt yapılmaz.

Yönetici API’leri `/api/governance` altında, çalışanların kişisel görünümü
`/api/governance/requirements/mine` altında sunulur. Emeklilik eylemi gelecekteki
oturum, aktif geliştirme, bekleyen yayın veya aktif politika gibi kesin
engelleri; tekil kapsam ve açık portföy kaydı gibi uyarıları ayrı gösterir.

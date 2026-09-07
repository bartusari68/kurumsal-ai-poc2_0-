# Uygun içerik bulunamadığında analiz hatası — 4 Eylül 2026

## Neden

Arama adayları her zaman uygun eğitim değildir. Model, konu ile ilgisiz adaylar
için `coverage=YOK` ve `course_assessments=[]` döndürebilir. Servis bu geçerli
negatif sonucu da eksik değerlendirme sayıp `AI_INVALID_RESPONSE` / HTTP 502
üretiyordu. Kısa bağlantı testi başarılı olduğu için bağlantı kontrolü bu sorunu
tespit etmiyordu. Fizik–itki talebi ve tamamen sentetik, ilgisiz derslerle gerçek
modelden bu yanıt biçimi yeniden üretildi. Önceki sunucu kayıtlarında ayrıntılı
istisna nedeni tutulmadığından eski dört hatanın her biri ayrıca doğrulanamadı.

## Değişiklik

- Açık `YOK` kararı ve boş ders değerlendirmesi geçerli sonuçtur. Talep kaydolur,
  katalog uyumu %0 olur, önerilen ders listesi boş kalır ve ihtiyaç analizine açılır.
- Olumlu `VAR` / `KISMEN_VAR` iddiaları geçerli ders değerlendirmesi olmadan hâlâ
  reddedilir. Kaynak ve puan doğrulamaları gevşetilmedi.
- Aynı hizmet hatası formda ikinci kez gösterilmez; talep metni değiştirilmez.
- Geçersiz yanıt, zaman aşımı, kota ve bağlantı ayarı sorunları çalışan için
  anlaşılır mesajlarla ayrılır. Model/anahtar/sağlayıcı gövdesi paylaşılmaz.
- Sunucu hata kaydına yalnızca yol, bileşen ve güvenli hata kodu eklenir.

## Doğrulama

- 87 arka plan testi ve 25 arayüz testi geçti (112 toplam).
- `scripts/diagnose_analysis.py --unrelated`: gerçek model + tamamen sentetik
  talep/dersler; `YOK`, boş değerlendirme, %0, `IN_REVIEW`, tek kayıt doğrulandı.
- Aynı testin ilgili ders senaryosu: uygun ders ve %85 uyum, `IN_REVIEW`.
- Canlı model testleri yalnızca bellek içi veritabanına yazdı. Gerçek kullanıcı
  talepleri, ders PDF'leri ve hesaplar bu testler tarafından değiştirilmedi.
- Gerçek PDF içeriklerini dış hizmete yeniden göndererek deneme işlemi güvenlik
  kontrolünde engellendi; bu işlem yapılmadı. Sentetik testler bu sınırın dışında
  yalnızca kodda yazılı örnek içerikleri kullandı.

Bu bulgu yalnızca eşleşme bulunmaması yolunu düzeltir; sağlayıcının tüm olası
yanıt/hizmet hatalarına karşı garanti değildir.

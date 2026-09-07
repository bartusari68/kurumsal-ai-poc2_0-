# Analiz bağlantı hatası ve test dosya listesi

4 Eylül 2026

## Doğrulanan kök neden

Yerel sunucuya analiz istekleri ulaşıyordu; uygulama bunları genel 502 hatasıyla
yanıtlıyordu. Sentetik bir sınıflandırma çağrısı, sağlayıcıdan HTTP 429 ve
`openrouter_free_tier_daily` / `free-models-per-day` hatasını aldı. Bildirilen günlük
sınır 50, kalan hak 0, yenilenme zamanı 5 Eylül 2026 00.00 UTC / 03.00 Türkiye saatiydi.
Bu bilgi, gözlem anındaki sağlayıcı yanıtıdır; gelecekteki hesap durumunu garanti etmez.

Eski sağlık kontrolü yalnızca embedding isteğini doğruluyordu. Analiz modeli
kotası dolduğunda bile yeşil görünebiliyordu. Ayrıca gerçek analizde oluşan hata
arayüzdeki daha önce alınmış yeşil durumu geçersiz kılmıyordu.

## Uygulanan değişiklikler

- Sağlayıcı hataları kodlanır: günlük kota, geçici istek sınırı, kredi/yetki,
  zaman aşımı ve diğer sağlayıcı sorunları ayrılır. Ham hata gövdesi dışarı verilmez.
- Analiz, embedding ve rerank bağlantıları birlikte kontrol edilir. Başarılı
  sonuç 10 dakika saklanır; ortak kilit eşzamanlı sayfa yüklemelerinin kontrolü
  çoğaltmasını önler. Gerçek işlem hatası saklanan yeşil durumu bozar.
- Kota, kalan hak ve varsa yeniden deneme zamanı ekranda açıklanır. Kota varken
  analiz düğmesi kapalıdır; yazılan metin formda korunur.
- Model çağrılarının toplam bekleme bütçesiyle tarayıcının analiz bekleme süresi
  uyumlu hale getirildi. Dosya hazırlığı ayrı ilerleme akışında kalır.
- Dosya paneli şimdilik test amaçlı açık tutuldu. Silinen kaynaklar ve silinmiş
  etiketleri API listesinde bulunmaz. Eşitlemede türetilmiş arama/indeks/öğrenilmiş
  eşleştirme kayıtları temizlenir; geçmiş talep ve insan incelemeleri korunur.
- Dosya listesi 20'şer gösterilir; bu sınır yalnızca görüntüleme içindir.

## Doğrulama

- 45 Python ve 14 JavaScript testi başarılı: kota ayrımı, gerçek ağ hatası,
  zaman aşımı, hatalı yanıt, sağlık kontrolü önbelleği/eşzamanlılık, silinen kaynağın
  listeden/indeksten çıkması, yeniden ekleme ve 1.000 kaynaklık sayfalama dahil.
- Canlı API: `status=ok`, `ai_status=quota`, limit 50 / kalan 0. Tarayıcıda
  `YZ kullanım sınırı`, yenilenme zamanı ve devre dışı analiz düğmesi doğrulandı.
- Canlı analiz uç noktası aynı sentetik isteğe açıklamalı 429 döndürdü.
  Talep kayıt sayısı test öncesinde ve sonrasında 8 kaldı.
- Mevcut klasörde 8 PDF, 8 hazır kaynak, 0 bekleyen ve 0 hatalı dosya vardı.
  Önceki rapordan farklı olarak `ABC_tmptrp5wx53.pdf` tekrar diskte mevcut;
  bu yüzden mevcut dosyalar arasında gösterilmesi doğrudur.

Kota dolu olduğu için bu değişiklikten sonra yeni bir **başarılı canlı analiz**
doğrulanamadı. Başarı akışı otomatik testlerde sınandı; gerçek sağlayıcıyla yeniden
doğrulama için kotanın açılması gerekiyor. Ücretli model, hesap veya anahtar değişmedi.

Mevcut kaynak PDF'lere ve geçmiş taleplere dokunulmadı. Değişiklik öncesi veritabanı
kopyası `backups/20260904-quota-fix-app.db` konumunda. Doğrudan geri yüklemek sonraki
kayıtları kaybettirebilir; toplu geri yükleme yerine gerektiğinde seçici geri alma yapılmalı.

## Canlıya geçiş sınırı

Test paneli hâlâ kullanıcı arayüzünde açıktır. Listeyi gizlemek tek başına erişim
kontrolü değildir; canlıya geçişte yönetici yetkilendirmesi/SSO gerekir. Sayfalama
1.000 derslik sunucu performansını kanıtlamaz; mevcut tam klasör taraması ve
bellekte vektör araması POC sınırları içindedir. Bu değişiklik bir üretim yayını değildir.

Sağlayıcı davranışı için resmi başvuru: [OpenRouter kullanım sınırları](https://openrouter.ai/docs/api_reference/limits).

# Kurumsal çalışma deneyimi — 7 Eylül 2026

Bu geliştirme AI 2.0 / `kurumsal-ai-poc` uygulamasındaki talep değerlendirmesini sadeleştirir; canlı ekranları ortak bir tasarım sistemiyle yeniler. Kullanıcının görev metni, mevcut kod, önceki hesap/yetki tercihleri, TUSAŞ Marka Kılavuzu ve paylaşılan giriş taslağı esas alınmıştır.

## Karar ve ilerleme

Eski akışta aynı eğitim ihtiyacı onaydan sonra bir kutuyla tekrar doğrulanıyor, ardından ikinci açıklama ve birim seçimiyle yönlendiriliyordu. Yeni akışta tek gerekçe ve tek gönderim vardır:

| Değerlendirme | Sonraki işlem |
|---|---|
| Mevcut ders bütün ihtiyacı karşılıyor | Çözüm planına al; tasarım birimi seçtirme. |
| Yeni ders veya eksik içeriğin zenginleştirilmesi gerekli | Kayıtlı/güncel hedefi kullan ve ilgili tasarım iş listesine ilet. |
| Hedef birim belirlenemiyor | Aynı değerlendirme formunda yalnız bu eksik bilgiyi iste. |
| Eğitim dışı, belirsiz veya kritik ihtiyaç | Analiz ekibinde tut; otomatik eğitim kararı üretme. |
| YZ önerisi tamamen yanlış | Gerekçeli ret kaydı ekle; analiz ekibine döndür ve önceki aktif sevki kapat. |

`POST /api/admin/requests/{id}/review-and-advance` yalnız ihtiyaç analizi rolüne açıktır. Karar, durum, sevk, kişi izi ve sürüm artışı tek işlemde kaydedilir. Eksik hedef, eski sürüm, değişmiş PDF veya kayıt hatası kısmi karar bırakmaz. Önceki `/decisions` ve `/refer` uçları uyumluluk için korunmuştur.

İşin gönderileceği birim ile insanın ilk YZ birim önerisini doğru/yanlış bulması ayrı alanlardır. Böylece sadece eksik operasyonel hedefi seçmek, YZ kararını yanlışlıkla "düzeltildi" olarak etiketlemez. İnsan geçmişindeki sonraki birim oyları fiilen kaydedilen hedefe dayanır.

## Süreç görünürlüğü

Talep sahibi, oluşturma ve son işlem zamanı, mevcut durum, aksiyon sahibi, sıradaki işlem ve adımlar gösterilir. Zaman çizelgesi kişi/rol, karar, zaman ve gerekçeyi kronolojik olarak bir araya getirir. Geçmişte kişi adı tutulmayan olaylar açıkça belirtilir; sonradan kişi adı uydurulmaz. Yeni olaylar kişi bilgisiyle değiştirilemez geçmişe eklenir.

Mevcut hesap tablosunda çalışanın resmî organizasyonu veya tam kurum şeması bulunmuyor. Arayüz bu alanı "Organizasyon bilgisi tanımlanmamış" olarak gösterir. Konu sınıflandırması çalışanın organizasyonu yerine kullanılmaz. Hedef çözümleme, mevcut yapılandırılmış konu kuralları ve insan/sevk kayıtlarıyla sınırlıdır; kurumun bütün şeflikleri keşfedilmiş gibi davranmaz.

## Ekranlar

- Adlı hesap ve sunucu tarafı rol sınırları korunur; üç yönetici hesabı ayrıdır.
- Analist ve tasarım birimleri role uygun iş merkezini görür. Çalışan kendi ihtiyaçlarını ve yanıt bekleyen taleplerini takip eder.
- Gerçek durum sayıları, talep tablosu, arama, hızlı filtreler, en yeni/en eski/son güncellenen sıralaması ve sayfalama kullanılır. Sahte bildirim veya örnek grafik yoktur.
- Durum ve sıralama tercihi hesap bazında saklanır. Talep arama metni ve taslaklar tarayıcı depolamasına yazılmaz. Sekme içi gezinme ve hata sırasında taslak korunur; hesap değişiminde temizlenir. Sayfanın kapatılması veya tamamen yenilenmesi bellekteki gönderilmemiş taslağı sonlandırır.
- Daraltılabilir masaüstü menüsü, mobil menü, gerçek talep araması ve Ctrl/Cmd+K kısayolu vardır. Formlarda yüklenme, hata, boş sonuç ve eski kayıt sürümü durumları açıklanır.
- Eski sentetik sunum kayıtları ve bunları yöneten kullanılmayan sayfa/olay kodları yüklenen `app.js` dosyasından çıkarıldı. Ortak çekirdek yaklaşık 128 bin karakterden 19 KB dosyaya indi. Mevcut kayıtlar ve önceki kaynak kopyası yedekte korundu.

## Giriş ve marka

Büyük eğik Dünya, gündüz/gece ışığı, şehir ışıkları, bulut katmanı ve sağda koyu saydam giriş paneli kullanılır. Dünya gerçek haritaların WebGL küresine uygulanmasıyla yavaş döner. Yeni bir grafik kütüphanesi eklenmemiştir. WebGL olmadığında üretilen durağan görsel gösterilir.

Giriş başarılı olduğunda kısa bir geçiş oynar. Ses varsayılan olarak kapalıdır; kullanıcı açabilir. Azaltılmış hareket tercihinde hareket/geçiş devre dışıdır; arka plana alınan sayfada çizim durur, giriş tamamlanınca kaynaklar bırakılır.

Marka kılavuzunun ana/tamamlayıcı renkleri, logo güvenli alanı ve değiştirilmemiş beyaz logo kullanılır. Gündelik veri ekranları açık ve okunabilir kalır. Gotham için yalnız yerel lisanslı font aranır; bulunmazsa Segoe UI/Arial kullanılır.

Kaynak adresleri ve üretilen yedek görselin tam istemi [varlık kaydındadır](../app/static/assets/experience/README.md).

## Doğrulama ve mevcut sınırlar

İş akışı testleri sentetik içerik ve ayrı SQLite veritabanıyla çalışır. Tarayıcı doğrulaması için önceki sentetik AI testinin kopyası `tmp/experience-preview/preview.db` altında kullanılır; asıl havuza test talebi eklenmez.

Bu turda asıl havuzun başlangıç kopyası `backups/20260907-experience/app.db` olarak alındı. Kopya 20 talep, 6 insan kararı, 8 ders ve 593 arama parçası içerir. Kayıt/PDF koruma kontrolü bu kopyayla karşılaştırılır. Önceki turdaki 18 talep sayısı tarihsel bir ölçümdür.

Çalışan/analist/birim yetkileri, atomik onay-sevk, belirsiz hedef, kategori düzeltmesi, kaynak doğrulama, eski sürüm çatışması, işlem başarısızlığında geri alma ve isimli geçmiş testleri vardır. Arayüz testleri aynı kararın tekrar gönderilmesini, ters sırada gelen filtre yanıtlarını, hesap/taslak sınırlarını ve doğru süreç metinlerini denetler.

Bu sürümde bildirim yetkili birimin uygulama içi iş listesidir. Kurumsal e-posta/Teams, insan kaynakları organizasyon verisi ve SSO bağlantıları mevcut projede tanımlı değildir. Bunlar sağlanmadan kurum geneli canlı entegrasyon tamamlanmış sayılmaz. SQLite/tek süreçli çalışma, OCR ve kurum uzmanlarınca etiketlenmiş geniş doğrulama veri kümesi sınırlamaları önceki AI kaydında açıklanmıştır.

Testlerin geçmesi her olası talepte sıfır hata garantisi değildir. Bu sürüm insan kararını takip eder ve benzer taleplerde kontrollü karar desteği üretir; dil modelinin ağırlıklarını kendiliğinden yeniden eğitmez veya denetimsiz kurum çapında yetki kullanmaz.

### Son doğrulama sonuçları

- **144 Python testi başarılı**; **54 JavaScript testi başarılı** (50 portal + 4 giriş davranışı). Üç yüklenen uygulama JavaScript dosyasının sözdizimi temiz.
- Sentetik %97 talep tek onayla `ACTION_PLANNED` oldu; birim seçimi istenmedi. %46 talep tek hedef seçimi ve tek gerekçeyle mühendislik eğitim tasarımına geçti. Her iki işlem de tarayıcıda kişi ve zamanıyla doğrulandı.
- Son çalışan/yönetici listeleri ve ayrıntıları aynı aksiyon sahibini gösterdi. Teknik deneme hesabı yalnız #3, mühendislik hesabı yalnız #2 talebini gördü; yanlış birimin doğrudan ayrıntı çağrısı 404 aldı. Sonuç `tmp/experience-preview/role-report.json` içinde.
- Son tasarım 1280 × 720 masaüstünde tam yüksekliğe sığdı. 390 × 844 mobil viewport testinde sayfanın yatay taşması yoktu; menü, giriş ve çıkış çalıştı. Hatalı giriş alanları korudu. Kayıtlı onay sonrası tekrar değerlendirme bölümü kapalı, sonraki işlem açık geldi. Kanıt bağlantısı ayrıntıyı doğrudan açtı.
- Durum seçimi listeyi ayrı bir filtre düğmesine gerek olmadan güncelledi; sıralama ve hesap tercihi kontrol edildi. Son tarayıcı denetiminde konsol hatası yoktu.
- Asıl uygulamanın dört adlı hesabı ve yetkisiz çağrıların reddi doğrulandı. AI bağlantı kontrolü `connected` döndü; asıl havuzda 8 PDF aramaya hazırdı. Bu tur gerçek belgeler dış sağlayıcıya test amacıyla gönderilmedi.
- Son koruma kontrolü: 20 talep, 27 ders eşleşmesi, 6 insan kararı, 33 işlem olayı, 5 yönlendirme, 8 ders, 593 arama parçası ve 8 kaynak PDF önceki kopyayla aynı. Yeni kimlik tablosu eklenmesi mevcut satırları değiştirmedi.

```text
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
node --test tests/frontend.test.cjs tests/experience.test.cjs
.venv\Scripts\python.exe scripts/verify_portal_live.py
.venv\Scripts\python.exe scripts/verify_portal_preservation.py --backup backups/20260907-experience/app.db
```

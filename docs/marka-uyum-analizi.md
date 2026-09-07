# TUSAŞ marka uyumu ve arayüz değerlendirmesi

Tarih: 4 Eylül 2026  
Kaynak: Kullanıcının sağladığı `C:/Users/Administrator/Downloads/Marka-Kılavuzu.pdf`, v1.0 / Temmuz 2021, 58 PDF sayfası.

## Sonuç

Mevcut prototipin ortak arayüzü, kılavuzun kurumsal renkleri, amblem geometrisi, güvenli boşluk ve tipografi ilkeleri temel alınarak yenilendi. Yönetim özeti ve canlı talep ekranları yeniden düzenlendi; aynı bileşen dili diğer rol ekranlarına da uygulandı. Bu çalışma, kurumsal marka onayı veya üretime geçiş onayı değildir.

**Tam tipografi uyumu henüz tamamlanmış değildir.** PDF içindeki Gotham örnekleri, tarayıcıda kullanılabilir tam ve lisanslı bir WOFF2 paketi yerine geçmez. Mevcut bilgisayarda ve projede Gotham webfont dosyası bulunmadığı için Segoe UI / Arial geçici karşılıkları kullanılır. Lisanslı yerel Gotham kurulumu varsa tanımlanan Book, Medium ve Bold ağırlıkları kullanılabilir.

## Kılavuzun tamamından çıkarılan kararlar

Aşağıdaki numaralar PDF görüntüleyicideki 1 tabanlı sayfa numaralarıdır; basılı sayfa numaraları farklıdır. Tüm 58 sayfanın metni çıkarıldı, tamamı görsel olarak incelendi. Renk ve güvenli alan sayfaları ayrıca tek tek büyütülerek kontrol edildi.

| PDF sayfaları | İçerik | Platforma etkisi |
| --- | --- | --- |
| 1–10 | Kapak, içerik, marka stratejisi ve değerler | Güvenilir, açık, insan odaklı dil; veri, öneri ve kararın ayrı gösterimi |
| 11–16 | Amblem oranı, sabit açı, renk ve ters kullanım | Amblem döndürülmez, eğilmez, esnetilmez; kurumsal mavi-kırmızı korunur |
| 17–25 | Logo tipografisi, oranları, rengi ve güvenli alanı | Mevcut tam Türkçe logo görseli korunur; çevresine logo genişliğinin en az onda biri kadar boşluk verilir |
| 26–35 | Tek renk, tek satır, dikey ve diğer logolarla kullanım | Tek satır/dikey istisnalar varsayılan ekran kimliğine taşınmaz; beyaz logo mavi yüzeyde kullanılır |
| 36–37 | Kurumsal ve tamamlayıcı renkler | Ortak renk değişkenlerinin ana kaynağı |
| 38–42 | Ürünlere özel renk paletleri | Genel öğrenme platformunun kurumsal temasına rastgele eklenmez |
| 43–53 | Amblem ve logo desenleri | Ölçü kuralları incelendi; veri ekranlarında okunabilirlik için dekoratif desen kullanılmadı |
| 54–56 | Gotham ailesi ve tipografi kuralları | Book/Medium/Bold ağırlık yapısı; harfler yatay/dikey esnetilmez; lisanslı webfont beklenir |
| 57–58 | Kaynak notu ve kapanış amblemi | Temiz amblem yol geometrisi 58. sayfadaki vektör çiziminden alındı |

### Renk kararları ve kaynak içi tutarsızlıklar

| İşlev | HEX | Kullanım |
| --- | --- | --- |
| Kurumsal mavi | `#263685` | Yan menü, ana eylemler, veri grafikleri |
| Kurumsal kırmızı | `#DD140E` | Amblem, kritik durum vurgusu |
| Kurumsal gri | `#4D4D4D` | Yardımcı metin ve veri kaynağı ayrımı |
| Açık nötr | `#F8F7F7` | Sayfa zemini |
| Tamamlayıcı sarı | `#D29F13` | Sınırlı uyarı ve gösterim ortamı vurgusu |
| Koyu tamamlayıcı | `#1E1A34` | Başlıklar ve koyu yüzeyler |
| Nötr siyah | `#222223` | Ana metin |

Kılavuzda mavi için verilen HEX ile bazı RGB rakamları birbiriyle tam örtüşmüyor. Bazı tek renk örneklerindeki kırmızı/gri kodları da ana kurumsal renk sayfasından farklı. Web arayüzünde **36. PDF sayfasındaki kurumsal HEX değerleri** esas alındı. Tamamlayıcı renkler 37. sayfadan alındı. Başarı mesajlarındaki yeşil, yalnızca işlevsel durum rengidir; logonun veya kurumsal ana paletin yerine kullanılmaz.

### Logo ve font birbirinden ayrıdır

- Logo, projede zaten bulunan tam Türkçe görselden ayrı bir dosyaya çıkarıldı. Logo yazısı HTML metniyle yeniden üretilmedi; oranı değiştirilmedi. Bu dosyanın kurumsal olarak onaylı güncel Türkçe logo olduğu ayrıca marka sahibi tarafından teyit edilebilir.
- Önceki küçük amblem PNG’sinin kenarında kesik logo yazısı parçaları vardı. Aktif kullanım temiz, ölçeklenebilir SVG ile değiştirildi. Orijinal kılavuz geometrisi ve ana renkleri korundu.
- Kılavuzun 54. sayfasındaki Gotham örneklerinde gömülü `JEZMHZ+Gotham-BookTr`, `Gotham-MediumTr`, `Gotham-BoldTr` gibi alt-küme CFF/Type1 fontlar bulunuyor. Bunlar tam webfont paketi veya web kullanım lisansı kanıtı değildir. PDF fontları sökülüp webfont olarak dağıtılmadı.
- Lisanslı Gotham Book, Medium ve Bold WOFF2 dosyaları sağlandığında yerel olarak sunulup `platform.css` içindeki font tanımlarına bağlanabilir. Uygulama şu anda dış font hizmetine bağlanmaz.

## Kod ve dosya yapısı değerlendirmesi

Uygulamaya ait Python kaynakları, başlangıç ve yapılandırma dosyaları, testler ve arayüzün stil/komut bölümleri incelendi. Üçüncü taraf sanal ortam paketlerinin tamamı, ikili veritabanı içeriği ve gizli `.env` değerleri bu marka incelemesinin kod kapsamına dahil edilmedi.

| Alan | Bulgular / yapılan işlem |
| --- | --- |
| `app/main.py`, `services.py`, `ai.py` | Gerçek analiz, PDF arama ve servis hata davranışı korunur; bu marka çalışmasında model veya servis sözleşmesi değiştirilmedi |
| `models.py`, `schemas.py`, `database.py`, `config.py`, `utils.py` | Mevcut veri/ayar yapısı korundu; veritabanı göçü veya içerik değişikliği yapılmadı |
| `app/static/index_tusas_faz31.html` | Büyük gömülü stil, kod ve görseller ayrıldı; anlamlı sayfa kabuğu, içerik atlama bağlantısı ve erişilebilir menü işaretleri eklendi |
| `app/static/css/platform.css` | Ortak renkler, tipografi, boşluklar, bileşenler ve masaüstü/tablet/telefon yerleşimleri |
| `app/static/js/app.js` | Beş rol ve mevcut iş akışları; yeni yönetim özeti ve canlı talep deneyimi |
| `app/static/js/i18n-tr.js` | Kayıt kimliklerini, özgün metni ve form değerlerini bozmayan Türkçeleştirme |
| `app/static/assets/brand/` | Ayrı yerel logo ve temiz SVG amblem |
| `tests/` | Servis, statik dosya ve arayüz gerileme kontrolleri |

Önceden devre dışı bırakılmış Faz 31 kodu artık tarayıcıya gönderilmez. Eski tek dosyalı arayüz ve bu kod, geri alınabilir biçimde `backups/20260904-brand/` içinde korunur. Yerel demo kayıtları sıfırlanmadı. API anahtarı, yüklenmiş PDF’ler ve veritabanı değiştirilmedi.

## Görünür ve davranışsal iyileştirmeler

- Yönetim özeti: inceleme gündemi, altı temel gösterge, kaynak dağılımı, öne çıkan ihtiyaçlar, anket katılımı ve karar sonuçları.
- Ortak tasarım: ölçülü başlıklar, okunabilir alanlar, tutarlı kartlar, tablolar, düğmeler, durum etiketleri ve çizgi simgeleri.
- Canlı talep: açıklayıcı örnek, karakter sayacı, bilgi güvenliği uyarısı, servis durumu, gönderim sırasında kilitleme, hata ve sonuç görünümü.
- Talep taslağı ve sonucu, sayfalar arasında aynı oturum belleğinde korunur; canlı metin demo `localStorage` kaydına yazılmaz. Sayfa yenilendiğinde bu geçici bellek temizlenir. Gönderilen talep sunucuda mevcut iş akışına göre kayıt edilir.
- PDF kanıtı: sayfa ve arama skoru ayrı gösterilir. Skorun doğruluk/güven yüzdesi olmadığı ve yapay zekâ çıktısının ilk değerlendirme olduğu açıkça belirtilir.
- Türkçe arayüz: uzun ifadeler önce çevrilir; `NEED-0028` gibi kimlikler değiştirilmez; çeviri seçeneklerin gönderilen değerlerini değiştirmez; özgün talep/kanıt metinleri arayüz çevirisinden korunur.
- Erişilebilirlik: klavye odağı, pencere içinde odak dolaşımı, Escape ile kapanma, mobil menü durumu, içerik atlama bağlantısı, etiketli alanlar ve azaltılmış hareket tercihi.
- Mobil: kartlar yeniden sıralanır, veri tabloları kendi bölgelerinde yatay kayar; sayfanın tamamı yatay taşmaz.

## Doğrulama ve sınırlar

8 Python testi ve 8 JavaScript testi geçti. Bunlar servis yanıt sözleşmesini, yerel marka dosyalarını, kimlik korumasını, çeviri sırasını, seçenek değerlerini, metin kaçışını ve grafik ölçeğini kapsar. Tarayıcıda beş rolün menüleri, ihtiyaç/tasarım ayrıntıları, karar penceresi, klavye davranışı ve canlı talep taslağı kontrol edildi.

Son tarayıcı kontrolünde 1440, 1024 ve 390 piksel genişliklerinde toplam **66 rol/menü geçişi** sınandı: boş başlık, sayfa geneli yatay taşma veya açık kalan mobil menü bulunmadı. Kontrol boyunca tarayıcı hata/uyarı kaydı görülmedi. İhtiyaç ve tasarım aktarımı ayrıntıları telefonda ayrıca incelendi. Karar penceresinde Tab odağı pencere içinde kaldı; Escape kapanınca odak çağıran düğmeye döndü. Türkçe görünen öncelik seçeneklerinin `Low / Medium / High / Critical` veri değerleri korundu. Canlı talep formunda 47 karakterlik sentetik taslak, ana sayfaya gidip geri dönüldüğünde aynen korundu; deneme metni gönderilmeden temizlendi.

Bu doğrulama yeni bir gerçek talebi sağlayıcıya göndermeyi veya yeni bir karar kaydetmeyi gerektirmedi. Canlı servis bağlantısı sağlık kontrolüyle doğrulandı; analiz çıktı şablonu sentetik test yanıtıyla sınandı. Mevcut canlı uçtan uca analiz akışının bu turda yeniden çalıştırıldığı iddia edilmez.

Üretime geçiş için ayrı çalışma gerektiren konular:

1. Marka sahibi teyidi ve lisanslı Gotham webfontlarının eklenmesi.
2. Gerçek kimlik doğrulama, SSO ve sunucu tarafında rol/yetki denetimi. Ekrandaki rol seçimi bir demo kontrolüdür; güvenlik sınırı değildir.
3. Gizli kurumsal veri için onaylı servis/barındırma ve veri yönetimi. Bu prototipte yalnızca sentetik veya paylaşımı onaylı veri kullanılmalıdır.
4. Yönetim ekranlarının sentetik veri yerine kurumsal kaynaklarla entegrasyonu.
5. Kapsamlı erişilebilirlik denetimi, yük/güvenlik testleri ve gerçek kullanıcı kabul testleri.

Sonuç olarak görsel marka uyumu ve kullanım kalitesi iyileştirilmiştir; eksik font ve üretim gereksinimleri nedeniyle “yüzde yüz kurumsal uyumlu ve üretime hazır” ifadesi kullanılmaz.

# Çalışan portalı, yönetici ayrımı ve açıklanabilir uyum

Doğrulama tarihi: 4 Eylül 2026. Yerel geliştirme sürümü; kurumsal canlıya geçiş onayı değildir.

**Sonraki sürüm notu:** Aşağıdaki tarayıcı-kimliği ve tek yönetici girişine ait
açıklamalar ilk portal sürümünü belgeler. Güncel sürüm kullanıcı adı/parola ve
dört rol kullanır; güncel erişim ve yönlendirme için
[Hesap rolleri ve yönlendirme](hesap-rolleri-ve-yonlendirme.md) belgesini okuyun.

## Çalışanın gördüğü alan

Sol menü: Genel Bakış → Talep İlet → Yönetici Paneli → Gönderdiğim Talepler → Çözüme Ulaşanlar.

Talep formu kullanılabilir içerik genişliğini kullanır. Sağdaki rehber ve bilgi
güvenliği kutuları kaldırıldı. Dış analiz hizmetine veri gönderildiğini açıklayan
kısa bir satır formun altında korunur. Model, klasör, dosya hazırlık listesi,
ham benzerlik skorları ve geliştirici ayrıntıları çalışan ekranında yer almaz.

Sonuçlar ders adı, kısa içerik özeti, konu başlıkları, ihtiyaç bazında karşılanan
ve eksik kalan noktalar ile uyum yüzdesini içerir. PDF sayfa alıntıları ve ham
metin parçaları çalışan yanıtlarından çıkarılmıştır. İçerik kanıtları analiz ve
yönetici denetimi için sunucuda korunur; arama hâlâ PDF içeriğine dayanır.

Ana sayfa ve takip listeleri gösterim verisi değil, bu tarayıcıdan gönderilen
gerçek taleplerin kayıtlarını kullanır. Arama, durum filtresi ve sayfalama vardır.
Talep ayrıntısı ilk analizi, açıklamaları ve durum değişikliği geçmişini korur.

- Yeni analiz **İncelemede** başlar; yüksek uyum otomatik olarak çözüm değildir.
- Yönetici **Çözüm planlandı**, **Ek bilgi bekleniyor**, **İncelemede** veya
  **Çözüme ulaştı** durumlarını açıklama girerek kaydeder.
- Çalışan ihtiyacının karşılandığını açıklayarak bildirebilir; çözülmüş talebi
  yeniden incelemeye açabilir. Kritik talepleri çalışan kapatamaz.
- Aynı kayda eşzamanlı güncelleme gelirse eski sürümün yeni bilgiyi ezmesi engellenir.

## Yönetici alanı ve erişim

Yönetici Paneli, Talep İlet'in hemen altındadır. İçeride üç bölüm bulunur:

1. **Talep yönetimi:** Tüm kayıtlar, arama/filtre, durum ve çalışanla paylaşılan not.
2. **İçerik ve bağlantı:** PDF durumu/eşitleme, model ve bağlantı ayrıntıları.
3. **Kategori rehberi:** Ana grupların sınırları ve alt kategorilerin açıklamaları.

Önceki sunum ekranları yönetici girişinden sonra ayrı bir düğmeyle açılır;
gösterim verileri gerçek çalışan talep kayıtları değildir.

Yerel yönetici parolası ilk çalıştırmada rastgele oluşturulur. İlk erişim bilgisi
`data/admin-access.txt` dosyasındadır; bu dosyayı paylaşmayın veya kaynak kontrolüne
eklemeyin. Doğrulama kaydı `data/admin-auth.json` içinde tuzlu PBKDF2-SHA256 özeti
olarak tutulur. Yeniden başlatma parolayı değiştirmez. Yönetici oturumu 8 saattir;
yanlış girişler için geçici deneme sınırı vardır. Parola yanıtlara/loglara basılmaz.

Yönetim API'leri sunucuda yetki kontrolü yapar; yalnızca arayüzden gizlenmez.
Çalışan çerezi HttpOnly ve SameSite=Strict'tir, sunucuda yalnızca özeti tutulur.
Başka tarayıcı bir çalışanın kaydını numarasını bilerek okuyamaz/değiştiremez.

**Sınır:** Bu sürümde çalışan kimliği tarayıcı çerezine bağlıdır; personel hesabı
ve SSO değildir. Çerez silinirse çalışan geçmiş erişimini kaybeder, yönetici
kayıtları korur. Ortak bilgisayarı kullanan kişiler aynı tarayıcı geçmişini
paylaşır. Canlıya geçişte personel hesabı/SSO, kurumsal rol ve ekip kapsamları,
HTTPS, parola/oturum yaşam döngüsü, veri saklama politikası ve güvenlik incelemesi
gereklidir. Tek sunucu işlemi varsayımı devam eder.

## Kategoriler

Sürüm: `2026-09-v1`. **11 ana grup ve 34 alt kategori** vardır. Eğitim/süreç/araç
ihtiyacı konu kategorisinden ayrı bir eksendir. Model alt kategori kimliği seçer;
görünen ana/alt adlar sunucudaki sözlükten gelir. Geçersiz veya belirsiz seçimler
zorla başka gruba atanmaz; kapsam netleştirme ve insan incelemesine yönelir.

| Ana grup | Alt kategori sayısı | Ayırıcı odak |
|---|---:|---|
| Veri Analizi ve Raporlama | 4 | Excel, BI, istatistik ve veri akışları |
| Yazılım Geliştirme ve Otomasyon | 5 | C++, .NET, Python, web ve DevOps |
| Ürün ve Sistem Mühendisliği | 4 | Tasarım, simülasyon, sistem ve gömülü sistem |
| Üretim, Bakım ve Operasyon | 3 | Üretim, bakım ve tedarik |
| Kalite ve Süreç İyileştirme | 3 | Kalite sistemi, kök neden ve yalın iyileştirme |
| Emniyet, İş Güvenliği ve Çevre | 3 | İş güvenliği, ürün emniyeti ve çevre |
| Dijital Araçlar ve Yapay Zekâ | 3 | Yapay zekâ kullanımı, iş birliği ve kurumsal uygulama |
| Bilgi ve Siber Güvenlik | 2 | Farkındalık ile teknik güvenlik ayrımı |
| Proje ve İş Yönetimi | 3 | Proje, risk ve iş yönetimi |
| Liderlik ve Kişisel Yetkinlikler | 3 | Liderlik, iletişim ve kişisel verimlilik |
| Kapsam Netleştirme | 1 | Belirsiz/çok genel ihtiyacın insanla netleştirilmesi |

Kesin ad ve sınırların kaynağı `app/taxonomy.py` ve yönetici kategori rehberidir.
Önceki kayıtlar kendiliğinden yeniden sınıflandırılmaz.

## Uyum yüzdesi

Sürüm: `fit-v1-70-20-10`. Her ders için üç bileşen toplanır:

| Bileşen | En fazla puan | Hesaplama |
|---|---:|---|
| İhtiyaçların karşılanması | 70 | Her istenen ihtiyaç: **tam=1, kısmi=0,5, desteklenmiyor=0**. Ortalama × 70. |
| İçerik ilgisi | 20 | Destekleyici kanıtların yeniden sıralama skoru × 20. |
| Anlamsal benzerlik | 10 | Destekleyici kanıtların anlamsal benzerliği × 10. |

İkinci ve üçüncü bileşende yalnızca o derse ait doğrulanmış kanıt referanslarının
en yüksek geçerli değeri kullanılır. Geçersiz/başka derse ait referanslar sayılmaz;
yinelenen ihtiyaç satırları puan şişiremez. Hiç desteklenen ihtiyaç yoksa sonuç
%0'dır. Değerler güvenli aralığa sınırlandırılır. Bileşenler bir ondalık basamakla
gösterilir, toplam tam yüzdeye yuvarlanır. %80 ve üzeri güçlü, %50–79 kısmi,
%1–49 sınırlı uyum olarak adlandırılır.

İnsan geri bildirimi aday bulma/sıralamayı etkileyebilir, bu yüzdeye doğrudan
bonus eklemez. Kullanıcı ayrıntıyı “Uyum oranı nasıl hesaplandı?” ile açabilir.
Bu oran **kalibre edilmiş doğruluk olasılığı veya eğitim başarısı garantisi
değildir**. Ağırlıklar açıklanabilir ilk sürüm kuralıdır; daha iyi doğruluk
iddiası için etiketli talep–ders değerlendirme kümesiyle ölçüm gerekir.

## Doğrulama kaydı

- 76 sunucu testi ve 19 arayüz testi: toplam **95 başarılı test**.
- Gerçek yerel arama + Groq analizi: Excel/Power Query/Pivot ihtiyacı doğru
  alt kategoriye ayrıldı, öneri **%95** uyum gösterdi.
- C++/mutex/atomic/CUDA testi C++ alt kategorisine ayrıldı. En iyi öneri **%58**
  oldu; CUDA/GPU konusu karşılanmıyor olarak ayrıldı. İkinci öneri %44'tü.
- Tarayıcıdan gönderim, kayıt ayrıntısı, çözüm bildirimi, çözülenler listesi,
  sayfa yenilemede kalıcılık, yeniden inceleme ve tekrar çözüm akışları denendi.
- Yönetici giriş ekranı tarayıcıda; parola doğrulama, yönetim verilerine erişim,
  çıkış ve çalışan erişiminin reddi gerçek HTTP çağrılarıyla doğrulandı.
  Giriş sonrası yönetici sekmelerinin tamamı için tarayıcı uçtan uca testi yapılmadı.
- 390 piksel dar ekran formu ve mobil menü kontrol edildi; yatay taşma görülmedi.
  Kontrol edilen tarayıcı oturumunda JavaScript hata/uyarı kaydı yoktu.
- Doğrulamada 8 PDF ve 593 arama parçası hazırdı. Önceki 10 talep korunur;
  sahipliği bilinmediği için çalışanlara topluca atanmaz, yöneticiye görünür.
- Yeni iki sentetik kayıt bırakıldı: #11 Excel iş akışı testi (çözüldü),
  #12 C++ kısmi uyum testi (incelemede). Gerçek eğitim tamamlama beyanları değildir.
- Geçiş öncesi SQLite yedeği: `backups/20260904-portal-workflow-app.db`.
  Eski kayıtlar ve kaynak PDF bütünlüğü için `scripts/verify_portal_preservation.py`;
  canlı yetki/bağlantı kontrolü için `scripts/verify_portal_live.py` vardır.

Bin ders/yüksek eşzamanlı kullanıcı yük testi, kurumsal SSO ve OCR bu değişikliğin
kapsamında değildir. Yerel sürüm çalışır; üretim ölçeği ayrıca doğrulanmalıdır.

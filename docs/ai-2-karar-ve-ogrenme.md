# AI 2.0 — Talep, içerik ve insan kararı akışı

7 Eylül 2026. Proje: `kurumsal-ai-poc`. Konuşmada kullanılan AI 2.0 aynı uygulamayı ifade eder.

## Bu geliştirmede tamamlanan akış

Çalışan ihtiyacını yazar veya PDF'den metin çıkarıp düzenler. Yapay zekâ ihtiyacı kategorize eder, ayrı kazanımlara böler, güncel ders PDF'lerinde arar ve kanıta dayalı uyum hesaplar. Sonuç talep havuzuna kaydedilir. Analiz ekibi ihtiyacın gerçekliğini, eksik/fazla kapsamını ve sorumlu birimi değerlendirir; ardından mevcut teknik veya mühendislik eğitim tasarım şefliğine yönlendirir. İlgili şeflik kendi değerlendirmesini ayrıca kaydeder. Çalışan durumunu ve kendisine açık açıklamaları takip eder.

Her talep başlangıçta insan incelemesindedir. Ders önerilmesi, ihtiyacın karşılandığı veya görevin tamamlandığı anlamına gelmez.

## Eşleşme politikası

| Uyum | İşlem |
|---|---|
| %0–40 | Yeterli ders eşleşmesi yok. Eğitim ihtiyacı için yeni ders taslağı analiz ekibine sunulur. |
| %40 üzerinde, tama yakın yeterlilik doğrulanmamış | Kısmi eşleşme. Mevcut içerik, eksik kazanımlar ve uzman doğrulaması gerektiren alanlar gösterilir. |
| %95–100, tüm kazanımlar tam ve güçlü/doğrulanmış kanıt | Mevcut dersin uygunluğunu onaylama önerisi. |

Eğitim dışı süreç, araç, bilgi ve performans desteği ihtiyaçları ayrı değerlendirilir. Kritik içerik öncelikli insan incelemesine gider. Bu alanlar sırf ders eşleşmedi diye otomatik yeni eğitime dönüştürülmez.

Uyum; ihtiyaçların karşılanması 70 puan, içerik ilgisi 20 puan, anlamsal benzerlik 10 puandan oluşur. Her bileşen aynı ihtiyaç sayısına bölünür. Dört ihtiyaçtan yalnız birini karşılayan bir içerik en fazla %25 alabilir. Tam karşılanan ihtiyaç 1, kısmi 0,5, desteklenmeyen 0 ağırlık taşır. İnsan kararlarından gelen arama önceliği bu yüzdeye eklenmez. Uyum yüzdesi doğruluk olasılığı veya başarı garantisi değildir.

Olumlu içerik değerlendirmeleri, gerçekten modele gönderilen ders parçasından kısa bir alıntıyla doğrulanır. Ders, ihtiyaç ve kanıt kimlikleri doğrulanır; başka derse ait veya uydurulmuş kanıt kabul edilmez. Eksik/kesilmiş JSON, yanlış vektör sayısı, yinelenen sıralama ve API hataları **ders yok** sonucu olarak saklanmaz.

Arama en güçlü üç dersin kanıtlarını çeşitlendirir; aynı uzun belgenin bütün sonuçları kaplaması azaltılır. Sonuç tüm PDF kataloğunun kesin olarak eksiksiz anlamsal tarandığı iddiası değildir: aday getirme ve model yorumu örnek bir kurum veri kümesiyle ölçülmelidir.

## Yönetici ekranı

1. **Talep yönetimi:** talebi açın; kazanımları, eksikleri, mevcut ders bağlantısını ve önerilen sorumlu birimi inceleyin.
2. **Yapay zekâ kararını değerlendirin:** Onaylıyorum / Düzeltiyorum / Tamamen yanlış seçin. Düzeltmede kategori, ders, sorumlu birim ve kapsamı değiştirin; gerekçeyi bir kez yazın. Eğitim önerisini onaylamak aynı ihtiyacın ikinci bir kutuyla doğrulanmasını gerektirmez.
3. **Talebi onayla ve ilerlet:** karar, durum, yönlendirme ve kişi bilgisi tek veritabanı işleminde kaydedilir. Tam karşılayan mevcut ders çözüm planına alınır; yeni veya eksik içerik ilgili tasarım birimine iletilir. Kayıtlı hedef varsa kullanılır; hedef bulunamazsa aynı formda bir kez seçilir. Yalnız yönlendirmeden sonra ilgili tasarım hesabı talebi görür. Eğitim dışı, belirsiz ve kritik ihtiyaçlar bu işlemle otomatik eğitim onayına dönüştürülmez.
4. Tasarım birimi aynı talepte kendi kararını kaydeder. İlk yapay zekâ sonucu ve önceki insan kararları değişmez.
5. **Kararlar ve ihtiyaç raporu:** onay/düzeltme/ret, incelenmeyen talepler, birim bazlı kararlar, tekrarlayan ihtiyaçlar, doğrulanmış ihtiyaç sayıları ve eksik/fazla kapsam sinyallerini inceleyin.

Yönlendirme ve bildirim uygulama içindeki yetkili birim iş listesiyle sağlanır. E-posta, Teams veya kurumsal iş emri sistemine dış bildirim entegrasyonu eklenmemiştir.

## İnsan kararlarından öğrenme

Her kayıt kişi, rol, zaman, talep sürümü, ilk analiz ve gerekçeli insan kararını taşır. Eski ekran sürümüyle üzerine yazma engellenir. Karar geçmişine yeni satır eklenebilir; uygulama ve SQLite katmanlarında geçmiş satırların değiştirilmesi/silinmesi engellenir. Mevcut tabloya geçiş idempotent koruma kurulumu kullanır.

Raporun genel ölçümlerinde her talebin en son kararı bir örnektir. Birim karşılaştırmasında her talep ve rolün son kararı sayılır. Böylece analiz ekibinin onayı ile tasarım biriminin düzeltmesi ayrı görülebilir.

Doğrulanmış ders kararları aynı niyetli sonraki aramalarda en fazla 0,05 sıralama katkısı sağlar. Aynı talebe tekrar karar vermek örnek sayısını artırmaz. Son karar retse veya PDF içeriği değişmişse eski olumlu katkı kullanılamaz. Kategori/birim karar dağılımı ve çelişkiler analiste gösterilir; otomatik gizli kategori değişikliği yapılmaz.

Bu, insan geri bildirimi kullanan arama ve karar desteğidir. Dil modelinin ağırlıklarını yeniden eğitmez. Otomatik karar verme etkin değildir. Gelecekte özerklik için kurum uzmanlarının etiketlediği ayrı bir doğrulama kümesi, kategori bazlı hata ölçümü, veri kayması takibi, geri alma ve yetki politikası gerekir. Sadece insanın AI önerisine katılım yüzdesi bu yeterliliği ölçmez.

## PDF talep eki

Talep İlet ekranındaki PDF alanı 10 MB / 100 sayfa sınırında yerel metin çıkarır. Metin önce düzenlenebilir önizlemede görünür; çalışan **Talep metnine ekle** işleminden sonra normal talep gönderimini yapar. Toplam talep 5.000 karakterdir. Ek okuma tek başına talep oluşturmaz, belgeyi ders havuzuna eklemez ve sağlayıcıya göndermez. Analiz gönderildiğinde düzenlenen talep metni normal AI akışına girer.

Şifreli/bozuk/metinsiz belgeler açıkça reddedilir. Metin çıkarılamayan sayfalar ve kesilen metin uyarıyla gösterilir. Okuyucu ayrı süreçte 20 saniyelik sınırla çalışır. Taranmış görüntü PDF'leri için OCR henüz yoktur. Ders yüklemelerinin sınırı 30 MB'dır.

## Önceki AI entegrasyonu doğrulaması

- Mevcut veri havuzu başlangıç kontrolü: 8 PDF, 593 arama parçası, 18 geçmiş talep; 8 PDF aramaya hazır.
- Gerçek Groq Qwen 3.8 27B + yerel BGE araması, yalnız oluşturulan sentetik PDF'lerle ayrı bir veritabanında test edildi.
- Pivot tablo ve aylık raporlama: **%97**, tam eşleşme politikası.
- Pivot tablo + sonlu elemanlar gerilme analizi: **%46**, kısmi eşleşme; gerilme analizi eksik olarak ayrıldı.
- Seramik sır hazırlama ve fırın programı: **%0**, yeni ders ihtiyacı taslağı.
- Analist onayı, teknik birime yönlendirme, teknik birim düzeltmesi ve tarayıcı üzerinden gerekçeli ret kaydı doğrulandı.
- Tam doğrulama: **122 Python testi ve 37 arayüz testi başarılı**.
- Çalışan sonucu, yönetici talep/karar/rapor ekranları tarayıcıda incelendi. 390 px genişlikte yatay taşma görülmedi.
- Ayrı sentetik çıktı: `tmp/e2e-20260907-084313/report.json`. Gerçek taleplerin içine test kaydı eklenmedi.
- Normal uygulama `127.0.0.1:8000` üzerinde açıldı; gerçek durum kontrolünde analiz, embedding ve rerank bileşenlerinin üçü de bağlı. Dört yerel hesabın rolü ve yetkisiz erişimin reddi doğrulandı. Son veri kontrolü: 18 talep, 8 ders, 593 parça; gerçek havuzda test insan kararı yok.
- Bozuk sanal ortam başlatıcısı mevcut Python 3.12 çalışma ortamına bağlandı. Önceki yapılandırma `backups/20260907-runtime/pyvenv.cfg` altında korundu.

Bu bölüm önceki entegrasyon testinin tarihsel kaydıdır. Güncel çalışma merkezi ve tek işlemli akışın doğrulaması için [kurumsal deneyim geliştirme kaydını](kurumsal-deneyim-20260907.md) inceleyin.

Tam test komutları:

```text
.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/frontend.test.cjs
```

Gerçek sağlayıcı testi isteğe bağlıdır ve API kotası tüketir; sadece sentetik belge kullanır:

```text
.venv\Scripts\python.exe scripts/verify_ai_end_to_end.py
```

## Kurum geneline geçiş sınırları

Bu çalışma yerel POC'yi geliştirir. Mevcut yapı hâlâ tek sunucu süreci, SQLite ve dört yerel hesaba/role dayanır. Kurum geneli üretim için SSO, merkezi rol/birim kaydı, HTTPS, ortak iş kuyruğu, merkezi veri tabanı, yedekleme/izleme ve kurum onaylı veri işleme ortamı gerekir. Şu anda tanımlı tasarım birimleri teknik eğitim ve mühendislik eğitimidir; diğer birimler için resmî sahiplik eşlemeleri henüz tanımlanmamıştır.

Yerel embedding ve rerank tüm sistemi kurum içinde tutmaz: talep ve seçilen ders parçaları dil modeli sağlayıcısına gönderilir. Dış sağlayıcıyla paylaşımı onaylı içerik kullanılmalıdır.

API bağlantısının çalışması ve testlerin geçmesi sıfır hata veya her talepte anlamsal doğruluk garantisi değildir. Pozitif kanıt doğrulaması, hata ayrımı ve insan karar izi bu riski yönetmek için uygulanmıştır.

Sağlayıcı doğrulamasında kullanılan resmî belgeler: [Groq JSON ve yapılandırılmış yanıtlar](https://console.groq.com/docs/structured-outputs), [Groq kullanım sınırları](https://console.groq.com/docs/rate-limits). JSON biçimi tek başına içerik doğruluğunu doğrulamaz.

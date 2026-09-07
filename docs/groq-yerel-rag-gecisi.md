# Groq + yerel PDF aramasına geçiş

Tarih: 4 Eylül 2026. Kapsam: bu bilgisayarda çalışan geliştirme/test ortamı.

## Düzeltilen bağlantı

Önceki uygulama yalnızca OpenRouter adresi ve anahtarını kullanıyordu.
Yeni `.env` ise Groq analiz modeli ve yerel BAAI arama modellerini seçiyordu.
Yalnızca anahtarı değiştirmek bu iki mimariyi birbirine bağlamıyordu.

Analiz ve sohbet artık seçilen Groq adresine, Groq anahtarıyla gider.
PDF vektörleri BAAI/BGE-M3 ile, adayların yeniden sıralanması
BAAI/BGE-Reranker-v2-M3 ile bu bilgisayarda hesaplanır. Groq anahtarı
embedding/rerank uçlarına veya OpenRouter'a gönderilmez. Önceki
OpenRouter desteği ayrı anahtar ve açık sağlayıcı seçimiyle korunur.

Canlı form testinde ayrıca Groq'un kısa süreli kullanım sınırı (HTTP 429)
gözlendi. Sağlayıcının `Retry-After` başlığında 0–30 saniye arasında açık
bir bekleme verdiği geçici Groq analiz/sohbet reddi, bu süre ve küçük güvenlik
payından sonra **yalnızca bir kez** yeniden denenir. Günlük kota, yetki
hatası, belirsiz ağ hatası, uzun veya geçersiz bekleme için otomatik tekrar
yapılmaz. İkinci ret gerçek hata olarak gösterilir; başka ücretli modele
otomatik geçilmez. Bu davranış [Groq sınır başlıklarını](https://console.groq.com/docs/rate-limits)
kullanır; sağlayıcının kotasını artırmaz.

API anahtarı ve seçilen modeller korundu. Canlı testte Groq, OTPM (dakikalık
çıktı tokenı) sınırını 1000, reddettiği bir isteği 1155 token olarak bildirdi.
Bu nedenle `.env` içinde yalnızca `PRIMARY_REASONING_EFFORT=none` ve
`MAX_OUTPUT_TOKENS=900` ayarları değiştirildi. Kısa JSON yanıtları için
sınıflandırma ve kapsama yönergeleri de kısaltıldı. Son sentetik doğrudan testte
sınıflandırma 255, kapsama 129 çıktı tokenıyla HTTP 200 döndü. Bu sayılar
o denemeye aittir; her talebin aynı miktarı kullanacağı garanti edilmez.

Kaynak PDF'leri değiştirilmedi. Arama dizini yenilenmeden önce veritabanı
`backups/20260904-groq-app.db` dosyasına yedeklendi.
Eski taleplerin ve insan değerlendirmelerinin silinmesi bu geçişin parçası değildir.

## Yerel modeller

Modellerin kaynak kodu uzaktan çalıştırılmaz. Kurulumda resmi Hugging Face
depolarından sabit sürümler indirilir; model ağırlıklarının boyutu ve SHA-256
bütünlüğü doğrulanır. Uygulama çalışırken yalnızca yerel dosyalar yüklenir.

| Bileşen | Sabit sürüm |
| --- | --- |
| BAAI/bge-m3 | `5617a9f61b028005a4858fdac845db406aefb181` |
| BAAI/bge-reranker-v2-m3 | `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e` |

Bu bilgisayarda CPU, dört iş parçacığı, iki metinlik küçük partiler ve
1024 token sınırı kullanılır. Tek anda tek model bellekte tutulur; ağır
hesaplama sunucunun diğer isteklere yanıt vermesini engellememesi için
ayrı çalışma kuyruğundadır. İlk PDF hazırlığı ve model değişimleri CPU'da
bekleme yaratabilir. Bu kurulum 1000 ders için bir kapasite garantisi değildir.

BGE-M3 için normalize edilmiş 1024 boyutlu CLS vektörü kullanılır.
NVIDIA modellerine özgü `query:` / `passage:` önekleri yerel BGE'ye eklenmez.
Sıralama modelinin ham çıktısı sigmoid ile dönüştürülür. Arama skorları
doğruluk/güven yüzdesi olarak sunulmaz.

## PDF güncelliği

Model/sürüm, token sınırı veya parçalama ayarları değişirse eski vektörler
arama dışında kalır ve yeniden hazırlanır. Mevcut ayarlar 1000 karakterlik
parçalar ve 150 karakter örtüşmedir. Dosya değişikliği SHA-256 ile saptanır.
Değişmeyen ve hazır olan PDF her talepte baştan hesaplanmaz.

Silinen PDF durum listesinden kaybolur; eşitlemede türetilmiş arama verisi
temizlenir. Talep/değerlendirme geçmişi ayrı tutulur. Test paneli kullanıcının
istediği gibi şimdilik görünürdür. Klasör arka planda sürekli izlenmez;
eşitleme düğmeyle ve analiz/sohbet öncesinde yapılır.

## Çalıştırma ve sınırlar

- İlk veya temiz kurulum: `kurulum.cmd`; yaklaşık 4,6 GB model ağırlığı indirir.
- Normal açılış: `baslat.cmd`; tek sunucu işlemi çalıştırır.
- Adres: `http://127.0.0.1:8000/`.
- Anahtar/model değişikliği: sunucuyu durdurup yeniden başlatın.
  Arayüzdeki bağlantı kontrolü `.env` dosyasını yeniden yüklemez.
- `FALLBACK_LLM_MODEL` ve güven eşiği henüz otomatik ikinci model çalıştırmaz.
  Bu geçiş birincil analiz, yerel arama/sıralama ve sohbet yolunu kapsar.
- Yönetim ekranlarının gösterim verileri ve demo rol seçimi gerçek kurumsal
  kimlik doğrulama değildir. Üretim yetkilendirmesi, SSO ve çok kullanıcılı
  yük/kapasite çalışması ayrıca gereklidir.
- Arama yereldir, ancak talep ve seçilen PDF kanıt parçaları analiz/sohbet
  için Groq'a gönderilir. Bu nedenle sistem bütünüyle kurum içi kapalı değildir.

## Kaynaklar

- [Groq OpenAI uyumluluğu](https://console.groq.com/docs/openai)
- [Seçilen Qwen modeli](https://console.groq.com/docs/model/qwen/qwen3.8-27b)
- [BGE-M3 resmi model kartı](https://huggingface.co/BAAI/bge-m3)
- [BGE reranker resmi model kartı](https://huggingface.co/BAAI/bge-reranker-v2-m3)

## Son kontrol — gerçek ortam

Son sunucu ayarlarıyla tamamlanan kontroller:

| Kontrol | Sonuç |
| --- | --- |
| PDF klasörü | 8/8 hazır, 0 bekleyen, 0 hatalı |
| Arama dizini | 593 parça, her vektör 1024 boyutlu; tamamı yeni yerel BGE sürümünde |
| Bağlantı | Analiz, embedding ve rerank: `connected` |
| Tarayıcıdan Excel talebi | Başarılı; Talep No 9, kategori Veri Analitiği ve Raporlama, kapsama `VAR` |
| Excel kaynakları | Excel Ileri Seviye Sentetik Ders; görünür ve kayıtlı kanıt sayfaları 2, 10, 11 |
| Ayrı C++ sohbet testi | Başarılı; 25,76 saniye. Yüksek Performans / Concurrency belgesinin 9, 10, 14. sayfaları yanıt içinde belirtildi |
| Kalıcılık | Önceki 8 talep korunmuş, yalnızca başarılı 9 numaralı yeni test talebi eklenmiş |
| Geçmiş bütünlüğü | Yedekle karşılaştırmada eski talepler, eşleşmeler ve insan değerlendirmeleri birebir aynı |
| PDF bütünlüğü | Eski ve yeni dizindeki kaynak içerik özetleri aynı; PDF'ler değiştirilmemiş |
| Otomatik kontroller | 60 Python + 14 arayüz testi geçti; bağımlılık uyumsuzluğu yok |
| Tarayıcı | Başarılı sonuç ekranında kontrol edilen hata/uyarı günlüğü boş |

Excel ve C++ kontrolleri farklı dersleri ve sayfaları döndürdü; arama yalnızca
ABC belgesine bağlı değildir. Silme/değiştirme davranışı ayrıca izole geçici
PDF ve veritabanlarıyla test edildi; bu doğrulama için kullanıcının gerçek
PDF'leri silinmedi. C++ sohbet denemesi yeni talep kaydı oluşturmaz.

Sentetik test başarıları genel doğruluk veya tüm konular için kapsama garantisi
değildir. Dış servis kotası hâlâ geçerlidir. Büyük eşzamanlı kullanıcı yükü,
1000 ders kapasitesi ve üretim güvenliği bu kontrollerde doğrulanmış değildir.

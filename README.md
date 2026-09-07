# Kurumsal AI – Eğitim Talep POC

GitHub'dan alınan tam sistem kopyası ve büyük model dosyalarının kurulumu:
[Karşılaştırma kopyası yönergesi](docs/github-comparison-copy.md).

Yerel çalışan portalı ve ayrı yönetici alanı bulunan uçtan uca RAG prototipi.

**7 Eylül 2026 — AI 2.0:** %40/%95 karar politikası, PDF kanıtı doğrulama,
talep PDF'inden düzenlenebilir metin alma, gerekçeli insan onayı/düzeltme/ret,
birim bazlı karar geçmişi ve tekrarlayan ihtiyaç raporu eklendi.
Kullanım, canlı sentetik doğrulama ve üretim sınırları:
[AI 2.0 karar ve öğrenme akışı](docs/ai-2-karar-ve-ogrenme.md).

## Yeni çalışan ve yönetici deneyimi

Uygulama **kullanıcı adı ve parola giriş ekranıyla** açılır. Hesabın rolüne göre
çalışan veya yönetici alanı otomatik seçilir. **Talep İlet** geniş ve sade bir
formdur; **Gönderdiğim Talepler** ve **Çözüme Ulaşanlar** gerçek kayıtları izler.
İlk yerel hesap erişim bilgileri `data/portal-accounts.txt` dosyasındadır;
parolaları paylaşmayın. İhtiyaç analizi hesabı önceki yönetici parolasını korur.

- 11 ana grup / 34 alt kategori ve sınırları açıklanan kategori rehberi.
- Ders başlığı, içerik özeti ve konu bazlı öneriler; çalışana PDF sayfa alıntısı yok.
- Açıklanabilir uyum: ihtiyaç kapsamı 70 + içerik ilgisi 20 + anlamsal benzerlik 10.
  Yüzde bir başarı olasılığı değildir; bileşenleri sonuç kartında açılabilir.
- Kayıtlı durumlar, açıklamalar ve çözüm/yeniden inceleme geçmişi.
- PDF eşitleme, model durumu ve tüm talepler yalnızca ihtiyaç analizi yöneticisinde.
- Teknik/mühendislik eğitim tasarım yöneticileri ayrı hesaplarla, yalnızca analizi
  tamamlanıp kendi şefliklerine yönlendirilmiş talepleri görür.
- Durum filtresi seçim anında, metin araması yazarken uygulanır.

Çalışan kimliği artık kullanıcı hesabına bağlıdır; aynı hesap başka tarayıcıda
aynı geçmişi görür. Kurumsal SSO henüz yoktur. Önceki sahipliği bilinmeyen kayıtlar
ihtiyaç analizi yöneticisine görünür. Güncel akış ve hesap bilgileri:
[Hesap rolleri ve yönlendirme](docs/hesap-rolleri-ve-yonlendirme.md).
Önceki kategori/uyum tasarımı: [Çalışan portalı ve uyum](docs/calisan-yonetici-kategori-uyum.md).

## Bu sürüm ne yapıyor?

1. Ders PDF'i yükler ve sayfa bazlı metin çıkarır.
2. Metni chunk'lara böler.
3. Seçilen yerel **BAAI BGE-M3** modeliyle sayfa parçalarının anlamsal vektörlerini üretir.
4. Talep geldiğinde embedding similarity ile aday içerikleri getirir.
5. Yerel **BAAI BGE Reranker v2 M3** ile adayları yeniden sıralar.
6. Groq üzerindeki **Qwen 3.8 27B** ile talebi ana/alt kategorilere ayırır; ihtiyaç bazında kapsama değerlendirmesini sunucuda açıklanabilir uyum yüzdesine dönüştürür.
7. İnsan onayı/düzeltme/ret kararlarını kişi, rol, ilk AI sonucu, gerekçe ve sürümle değiştirilemez `RequestDecision` geçmişine kaydeder.
8. Güncel PDF'yle doğrulanmış son insan kararlarını aynı niyetli sonraki taleplerde sınırlı arama önceliği olarak kullanır; uyum yüzdesini artırmaz. Eski `LearnedMapping` kayıtları yeni karar akışında güvenilir oy olarak kullanılmaz.
9. Ders kanıtlarına dayalı basit chatbot sağlar; yanıt kaynaklarını ders adıyla sunar.
10. Talepleri çalışan hesabına bağlı saklar; analiz ve tasarım şefliği erişimini sunucuda ayırır.

> API anahtarı yoksa veya sağlayıcıya ulaşılamıyorsa sistem sahte bir yapay zekâ sonucu üretmez. Arayüz açıkça `YZ kapalı` veya `YZ bağlantı hatası` gösterir ve canlı analiz düğmesini devre dışı bırakır.

### Bağlantı ve kullanım kotası

Yönetici alanındaki `YZ bağlı` durumu yalnızca embedding değil, **analiz + embedding + rerank**
bileşenlerinin küçük gerçek bağlantı testlerinden sonra gösterilir. Bu bir anlık
hazırlık kontrolüdür; sonraki istek için başarı garantisi değildir. Başarılı kontrol
10 dakika saklanır; sayfa yenilemek gereksiz yere yeni model isteği tüketmez.
Sağlayıcı hatası bu durumu hemen geçersiz kılar. Genel hata 60 saniye, bildirilen
kota engeli en az yeniden deneme zamanına kadar saklanır. **Durumu yeniden kontrol
et** düğmesi, örneğin hesap limiti değiştirildikten sonra, yeni kontrol yapar.

- Günlük kota / geçici hız sınırı: `YZ kullanım sınırı`, 429 ve açık hata kodu.
- Kredi yetersizliği: `YZ kredi gerekli`; otomatik satın alma veya ücretli modele geçiş yapılmaz.
- Sağlayıcı zaman aşımı: uygulamanın kapalı olmasından ayrı bir uyarı.
- Yerel sunucuya gerçekten erişilemiyorsa: `Sunucuya erişilemiyor`.

Groq'un açıkça bildirdiği en fazla 30 saniyelik geçici beklemeler, tek otomatik
yeniden denemeyle karşılanır. Günlük kota veya yetki hatasında tekrar döngüsü
başlatılmaz; ikinci başarısızlık kullanıcıya gösterilir.

Yönetici görünümünde kota yanıtında mevcutsa sınır, kalan hak ve sağlayıcının yeniden deneme zamanı
Türkiye saatiyle gösterilir. Bir kullanıcı analizi birden fazla model çağrısı
yapar; 50 API isteği, 50 tamamlanmış analiz anlamına gelmez. Başarısız analiz bir
başarı kaydı olarak saklanmaz. Hata yanıtlarına API anahtarı, hesap kimliği veya
ham sağlayıcı yanıtı eklenmez. Ayrıntılı olay doğrulaması: [Kota hatası](docs/ai-kota-hatasi.md).

## Kurulum

Windows'ta Python 3.12 ile doğrulanmıştır. Mevcut `.env` dosyasını değiştirmeden
önce içindeki anahtarı ve ayarları koruyun; dosyayı topluca örnek dosyayla ezmeyin.

1. Yeni kurulumda `.env.example` dosyasını `.env` adıyla kopyalayın.
2. `GROQ_API_KEY` alanına kendi Groq anahtarınızı ekleyin.
3. **kurulum.cmd** dosyasını çalıştırın. Kütüphaneleri ve toplam yaklaşık 4,6 GB
   model ağırlığını indirir, bütünlük ve gerçek yerel çıkarım testi yapar.
4. **baslat.cmd** dosyasını çalıştırın.

```env
GROQ_API_KEY=
GROQ_BASE_URL=https://api.groq.com/openai/v1
PRIMARY_LLM_MODEL=qwen/qwen3.8-27b
EMBEDDING_PROVIDER=local
EMBEDDING_MODEL=BAAI/bge-m3
RERANK_PROVIDER=local
RERANK_MODEL=BAAI/bge-reranker-v2-m3
```

Anahtar/model ayarı değişince sunucuyu durdurup yeniden başlatın. **Durumu yeniden
kontrol et** sağlayıcıyı yeniden sınar; `.env` dosyasını çalışan süreçte yeniden
yüklemez. `LLM_MODEL` verilmişse `PRIMARY_LLM_MODEL` değerinden önceliklidir.

Yerel modeller `data/models` altında sabit sürümleriyle tutulur. İstek sırasında
internetten model veya Python kodu indirilmez; uzaktan model kodu çalıştırılmaz.
CPU varsayılanı 4 iş parçacığı ve 2 metinlik küçük partilerdir. Belleği sınırlamak
için tek model yüklü tutulur ve model işlemleri sunucu olay döngüsünün dışında
sırayla çalışır. CPU üzerinde büyük klasörün ilk hazırlanması zaman alabilir.

Bu hesabın canlı testinde dakikada 1000 çıktı tokenı sınırı görüldüğünden kısa
JSON analizi için `PRIMARY_REASONING_EFFORT=none` ve `MAX_OUTPUT_TOKENS=900`
doğrulandı. Uzun düşünme/yanıt ayarları küçük bağlantı testi başarılı olsa bile
gerçek analizi kullanım sınırına takabilir. Bu değerler kota artırımı değildir.

`CHUNK_SIZE` ve `CHUNK_OVERLAP` karakter cinsindedir. Model, sürüm, yerel
token sınırı veya parçalama ayarı değişince arama dizini yeniden hazırlanır.
`FALLBACK_LLM_MODEL` ve güven eşiği alanları otomatik ikinci görüşü bu sürümde
etkinleştirmez; arama skoruna yapay bir güven yüzdesi anlamı yüklenmez.

OpenRouter desteği korunur. Kullanılacaksa `LLM_PROVIDER=openrouter`,
`OPENROUTER_API_KEY`, uygun model adları ve uzak arama için
`EMBEDDING_PROVIDER=openrouter` / `RERANK_PROVIDER=openrouter` seçilmelidir.
Groq anahtarı hiçbir zaman OpenRouter arama hizmetine gönderilmez.

Geçişin kapsamı, yerel model sürümleri ve doğrulama kaydı:
[Groq + yerel PDF araması](docs/groq-yerel-rag-gecisi.md).

Tarayıcı:

```text
http://127.0.0.1:8000
```

## Önerilen demo akışı

### Klasörden otomatik PDF eşitleme

PDF dosyalarını `data/pdfs/` klasörüne veya onun alt klasörlerine koyabilirsiniz.
Her yeni canlı analiz ve sohbet araması öncesinde bu klasör arama diziniyle eşitlenir.
**Yönetici Paneli → İçerik ve bağlantı** bölümündeki **PDF klasörünü eşitle**
düğmesiyle hazırlığı önceden başlatabilir, dosya durumlarını inceleyebilirsiniz.
Çalışan talep gönderdiğinde hazırlık otomatik tetiklenir; kendisine dosya listesi
yerine kısa hazırlık/analiz ilerleme mesajları gösterilir.

- Yeni PDF: otomatik kayıt oluşturulur, sayfalara/metin parçalarına ayrılır ve indekslenir.
- Değişen PDF: dosya içeriğinin SHA-256 özetiyle saptanır, aynı kayıt altında yeniden indekslenir.
- Değişmeyen PDF: tekrar embedding isteği gönderilmez. Model veya parçalama sürümü değişirse yeniden hazırlanır.
- Silinen PDF: durum listesi yenilendiğinde adı ve silinmiş etiketi dahil tamamen görünmez olur. Eşitlemede arama parçaları, indeks kaydı ve türetilmiş öğrenilmiş eşleştirmeleri temizlenir. Eski talep/insan değerlendirmesi geçmişi ve o geçmişin ders referansı korunur.
- İşlenemeyen PDF: hata nedeni gösterilir. Eksik dizinle sessizce analiz yapılmaz; dosya düzeltilip eşitleme yeniden çalıştırılmalıdır.

İlk hazırlık büyük belgelerde birkaç dakika sürebilir; ilerleme dosya ve parça
bazında gösterilir. Bir dosyada hata olursa başarıyla tamamlanan diğer dosyalar
korunur, yeniden denemede yalnızca hazır olmayan dosyalar işlenir. Eşitleme kaynak
PDF dosyalarını silmez veya değiştirmez. Yeniden indekslemede yalnızca türetilmiş
arama parçaları atomik olarak değiştirilir; geçmiş kanıt özetleri korunur.

`PDF_DIR` farklı bir klasör gösterebilir. Göreli dosya yolları uygulamanın bulunduğu
proje klasörüne göre çözülür. Klasör dışına yönelen dosya bağlantıları takip edilmez.
Desteklenen dosya türü PDF'dir; görüntü tabanlı PDF'ler için OCR henüz eklenmemiştir.
Doğrudan kopyalanan PDF'lerde ad dosya adından, benzersiz kod göreli yoldan üretilir.

İlgili uçlar: `GET /api/documents/status`, `POST /api/documents/sync` (202),
`GET /api/courses` (yalnızca mevcut ve aramaya hazır kaynaklar).
Durum listesi `offset` ve `limit` ile sayfalanır (varsayılan 20, en fazla 100).
Toplam sayılar bütün klasörü kapsar; sayfalama aramanın kapsamını daraltmaz.
PDF paneli **Eğitim bilgi kaynakları** adıyla yalnızca ihtiyaç analizi yöneticisine görünür.
Yukarıdaki içerik yönetim uçlarında ihtiyaç analizi hesabı yetkisi zorunludur.
İndeks tamamlanamadan doğrudan analiz/sohbet çağrılırsa 409 döner; çalışan yanıtı
dosya envanteri içermez. Canlıya geçişte yerel girişin yerini kurumsal kimlik ve
rol kapsamları almalıdır.
Bu POC eşitlemeyi **tek sunucu işlemi** içinde sıraya alır; çoklu worker veya çoklu
sunucu kurulumu için ortak iş kuyruğu/kilit eklenmelidir. Klasör arka planda sürekli
izlenmez; eşitleme analiz/sohbet öncesinde veya düğmeye basıldığında tetiklenir.

> Yerel aramada PDF vektörleri ve sıralama bilgisayarda üretilir. Groq'a talep
> metni ve kapsama/sohbet için seçilen PDF kanıt parçaları gönderilir. Uzak
> embedding seçilirse PDF parçaları o sağlayıcıya da gider. Yalnızca sentetik
> veya ilgili sağlayıcıyla paylaşımı onaylı bilgi kullanın.

- `TTCCP105 - Microsoft Office Eğitimi` gibi 5-20 PDF ekleyin.
- “Excel'de pivot tablo ve formüller konusunda gelişmek istiyorum.” talebi gönderin.
- Sonuçtaki ders özetini, karşılanan/eksik konuları ve uyum yüzdesini inceleyin.
- **Uyum oranı nasıl hesaplandı?** bölümünde puan bileşenlerini açın.
- **Gönderdiğim Talepler** üzerinden sonucu ve durum geçmişini izleyin.
- Yönetici Paneli'nde talebi açıp açıklamayla durumunu güncelleyin.
- Sentetik bir talepte çözüm ve yeniden inceleme akışını deneyin. İçerik önerisi
  talebi otomatik kapatmaz; gerçek tamamlanma olmadan tamamlandı bildirmeyin.

## Veri güvenliği

Yerel arama, bütün sistemi kurum içi kapalı bir sistem yapmaz: analiz ve sohbet
seçili dış dil modeli sağlayıcısında çalışır. Gerçek gizli şirket bilgilerini
kurum onayı olmadan bu hizmetlere göndermeyin. POC için sentetik veya paylaşımı
onaylı veriler kullanın. Yerel hesap ve rol kontrolleri kurumsal
kimlik doğrulama yerine geçmez. Canlıya geçiş için SSO/rol kapsamları, HTTPS ve
sağlayıcı/veri güvenliği onayı ayrıca gereklidir.

## Sonraki teknik adımlar

- SQLite cosine search → PostgreSQL + pgvector
- OCR (taranmış PDF)
- Hybrid BM25 + vector search
- Rol/yetki modeli ve SSO
- Merkezi, kurumsal denetim izi (talep durum geçmişi bu sürümde vardır)
- Daha gelişmiş feedback-aware reranking
- Evaluation dataset ve retrieval metrikleri
- On-prem model serving

## Marka uyumlu arayüz — 4 Eylül 2026

TUSAŞ Marka Kılavuzu'nun tamamı incelenerek ortak arayüz yenilendi. Ayrıntılı
kararlar, kaynak sayfaları ve açık kalan koşullar: [Marka uyum analizi](docs/marka-uyum-analizi.md).

- Sayfa kabuğu: `app/static/index_tusas_faz31.html`
- Tasarım sistemi: `app/static/css/platform.css`
- Canlı çalışan/yönetici iş akışları: `app/static/js/portal.js`
- Canlı portal ortak işlevleri: `app/static/js/app.js`
- Türkçeleştirme: `app/static/js/i18n-tr.js`
- Yerel marka dosyaları: `app/static/assets/brand/`

Çalışan portalı ve role özel Yönetici Paneli gerçek kayıtları kullanır.
Önceki sentetik sunum ekranları ve rol seçici yüklenen uygulama kodundan çıkarılmıştır.
Gerçek hesap rolü sunucuda belirlenir.

Gotham webfontları projeye dahil değildir. Yerel lisanslı Gotham bulunmazsa
Segoe UI / Arial kullanılır; tam tipografi uyumu için lisanslı webfont gerekir.

Testler:

```text
.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/frontend.test.cjs tests/experience.test.cjs
```

## Kurumsal çalışma deneyimi — 7 Eylül 2026

Tek işlemle insan kararı ve ilerleme, otomatik hedef çözümleme, isimli süreç geçmişi,
role uygun iş merkezi ve Dünya temalı giriş uygulanmıştır. Davranış, doğrulama ve
kurum entegrasyonu sınırları: [Geliştirme kaydı](docs/kurumsal-deneyim-20260907.md).

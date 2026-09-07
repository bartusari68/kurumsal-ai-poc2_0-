# PDF klasörü / RAG eşitleme düzeltmesi

4 Eylül 2026

> Aşağıdaki canlı sayımlar ilk eşitleme düzeltmesinin anlık görüntüsüdür.
> Daha sonraki kota hatası, silinen kayıtların görünümden temizlenmesi ve
> güncel 8 PDF doğrulaması [sonraki düzeltme notunda](ai-kota-hatasi.md) yer alır.

## Doğrulanan neden

`data/pdfs` klasöründe 7 yeni PDF varken veritabanında yalnızca `ABC` ders kaydı ve
ona bağlı 4 eski parça vardı. `retrieve()` doğrudan `course_chunks` tablosunu
okuyordu. Elle kopyalanan PDF'leri keşfeden, içerik değişimini saptayan veya silinen
PDF'leri aramadan çıkaran bir eşitleme adımı yoktu. ABC kaynak dosyası silinmiş
olmasına rağmen eski parçalar sorguya aday olabiliyordu.

## Uygulanan çözüm

- Analiz/sohbetten önce `data/pdfs` ve alt klasörleri taranır; uzantı büyük/küçük harfi fark etmez.
- Yeni `document_index` tablosu kaynak yolu, içerik özeti, model/parçalama sürümü,
  durum, hata, sayfa ve parça sayısını tutar. Eski kurs kayıtları da bu takibe alınır.
- SHA-256 ile içerik değişikliği bulunur; yalnızca değişen veya henüz hazır olmayan
  dosyalar yeniden işlenir. Değişmeyen kaynaklar için yeniden embedding üretilmez.
- Yeni/güncellenmiş içerik hazır olmadan eski sürümü aramada kullanılmaz. Vektörler
  tamamen hazırlandıktan sonra türetilmiş parçalar tek işlemde değiştirilir.
- Diskte olmayan kaynaklar yeni aramalardan ve aktif kurs listesinden çıkarılır.
  Geçmiş talep, eşleşme ve insan değerlendirmesi kayıtları korunur.
- Analiz sürerken kaynak silinir/değişirse eski kanıtla sonuç verilmez; yeniden analiz istenir.
- İşlenemeyen dosya açıkça raporlanır; eksik kapsam sessizce tamamlanmış gibi sunulmaz.
- API yüklemesi ve klasör eşitlemesi aynı indeksleme mekanizmasını kullanır.
  Geçersiz ders kodları ve mevcut dosyanın üzerine yazma girişimleri reddedilir.
- Göreli klasör/veritabanı yolları uygulamanın proje köküne bağlandı.
- Canlı talep ekranına dosya sayıları, dosya bazlı durum, ilerleme ve eşitleme
  düğmesi eklendi. Analiz düğmesi önce eşitlemeyi bekler, ardından talebi gönderir.

## Canlı doğrulama

| Ölçüm | Sonuç |
| --- | --- |
| Diskteki PDF | 7 |
| Aramaya hazır PDF | 7 |
| Güncel arama parçası | 373 |
| Bekleyen / hatalı dosya | 0 / 0 |
| Silinmiş ve arama dışında tutulan eski kayıt | ABC |
| Otomatik kontroller | 27 Python + 8 JavaScript testi geçti |

Tarayıcıda oluşturulan **8 numaralı sentetik doğrulama talebi**, Excel / PivotTable /
Power Query konulu aramada `Excel_Ileri_Seviye_Sentetik_Ders.pdf` dosyasını ve 5, 2,
4. sayfalardaki kanıtları döndürdü. ABC sonuçlarda bulunmadı. Bu bir insanın gerçek
eğitim talebi değildir; doğrulama amacıyla kaydedilmiştir.

Yeni talep kaydı oluşturmayan ikinci gerçek arama, C++ concurrency / atomics /
memory model konularında `Sentetik_CPP_Yuksek_Performans_Concurrency_15_Sayfa.pdf`
dosyasını; ilk üç sırada 10, 11 ve 1. sayfaları getirdi. Bu aramada da ABC yoktu.

## Kapsam ve geri alınabilirlik

Kaynak PDF'ler silinmedi veya değiştirilmedi. Eşitleme öncesi veritabanı kopyası
`backups/20260904-rag-sync/app.db` konumunda tutuluyor. Bu kopya eşitleme öncesi
durumu içerir; doğrudan geri yüklenmesi sonradan oluşan kayıtları da geri alır.

Tarama sürekli bir dosya izleyicisi değildir; analiz/sohbet öncesinde veya manuel
eşitlemeyle çalışır. Tek sunucu işlemi kullanan yerel POC içindir. Çoklu worker
kurulumunda ortak kilit ve kalıcı iş kuyruğu gerekir. OCR, PDF dışı dosya türleri ve
gizli kurumsal veri için üretim güvenlik onayı bu değişikliğin kapsamı dışındadır.

Dosya içerikleri, embedding için mevcut yapılandırılmış AI sağlayıcısına gider.
Bu nedenle klasöre yalnızca sentetik veya sağlayıcıyla paylaşımı onaylı belgeler konmalıdır.

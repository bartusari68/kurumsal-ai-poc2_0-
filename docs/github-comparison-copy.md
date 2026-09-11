# Tam sistem karşılaştırma kopyası

Bu depo kod, arayüz, testler, dokümantasyon, PDF havuzu, mevcut SQLite
veritabanı, yerel hesap dosyaları, yedekler ve çalışma dosyalarını içerir.
`.env` ve `.venv` aktarılmaz. Ortamı yeniden kurarken `.env.example`
üzerinden kendi ayarlarınızı oluşturun.

İki büyük model ağırlığı GitHub dosya sınırlarına uyum için kayıpsız
parçalanmıştır. Özgün dosyalar yerelde korunur; depoda bütün baytları
`model-transfer/` altında Git LFS ile saklanır. Manifest her parçanın ve
özgün dosyanın SHA-256 özetini içerir.

Klonlamadan sonra:

```powershell
git lfs install
git lfs pull
python scripts/restore_model_files.py
```

Araç parçaları doğrular, özgün model yollarına birleştirir ve bütün dosya
özetini kontrol eder. Mevcut doğru model dosyalarını değiştirmez.
Faz 12 karşılaştırma kopyasındaki veritabanı SQLite backup API ile tutarlı
anlık kopya olarak yüklenmiştir; çalışan veritabanı değiştirilmemiştir.

Mimari karşılaştırmada uygulama kodunu, testleri, veri miktarını ve hazır
model ağırlıklarını ayrı ölçün. Depo boyutu tek başına mimari kalite ölçütü değildir.

Faz sonunda testleri ve veri bütünlüğü doğrulamasını geçen değişiklikler commit ve
push edilir. Faz 13 isteğiyle yükleme kapsamı güncellendi: kaynak kod, kaynak
testleri, uygulama varlıkları ve dokümantasyon açık dosya listesiyle alınır.
Generated/temp/test çalıştırma çıktıları, canlı veritabanı ve yedekleri yeni faz
commitlerine alınmaz. Önceden yüklenen karşılaştırma kopyaları geçmişte korunur.
`python scripts/stage_phase_snapshot.py --phase 13 --paths app/portfolio.py`
gibi açık dosya listesi kullanılır; araç artık toplu add-all veya veritabanı
kopyası oluşturmaz. Normal push sonrası uzak main ile yerel HEAD eşleşmesi doğrulanır.

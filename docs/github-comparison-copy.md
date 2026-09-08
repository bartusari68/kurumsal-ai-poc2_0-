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
Aktif veritabanı SQLite backup API ile tutarlı bir anlık kopya olarak
commit edilir; çalışan uygulamanın veritabanı değiştirilmez.

Mimari karşılaştırmada uygulama kodunu, testleri, veri miktarını ve hazır
model ağırlıklarını ayrı ölçün. Depo boyutu tek başına mimari kalite ölçütü değildir.

Faz 12'den itibaren testleri geçen her fazın sonunda commit ve push yapılır.
Yükleme öncesi `python scripts/stage_phase_snapshot.py --phase 12` benzeri komut,
tüm karşılaştırma içeriğini ve canlı veritabanının tutarlı SQLite yedeğini Git
indexine alır. `.env` türevleri ve sanal ortamlar dışarıda kalır; `.env.example`
korunur. Araç uygulamanın veritabanını değiştirmez. Normal push sonrası uzak
`main` commit'i doğrulanır; zorla geçmiş değiştirilmez.

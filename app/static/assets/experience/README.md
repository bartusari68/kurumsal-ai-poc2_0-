# Dünya varlıkları

Bu dosyalar giriş ekranında yerel olarak sunulur. Kullanıcının tarayıcısı NASA veya görsel üretim servisine bağlanmaz. Haritalar görsel tasarım malzemesidir; güncel uydu verisi veya operasyonel coğrafi bilgi olarak sunulmaz.

| Dosya | Kaynak ve amaç |
|---|---|
| earth-day.webp | NASA Blue Marble Next Generation, Aralık 2004, topoğrafya ve batimetri. Reto Stöckli / NASA Earth Observatory. 2048 × 1024 WebP. |
| earth-night.webp | NASA Earth Observatory, Night Lights 2012. Robert Simmon; Suomi NPP VIIRS verisi, Chris Elvidge / NOAA National Geophysical Data Center. 2048 × 1024 WebP. |
| earth-clouds.webp | NASA Blue Marble Clouds. Reto Stöckli / NASA Goddard Space Flight Center. 2048 × 1024 WebP. |
| earth-day-4k.webp | Aynı NASA gündüz kaynağının 5400 × 2700 özgün sürümünden 4096 × 2048 WebP; büyütme uygulanmadı. |
| earth-night-4k.webp | NASA Night Lights 2012, 13500 × 6750 özgün haritadan 4096 × 2048 WebP; büyütme uygulanmadı. |
| stars-1280.webp / stars-1920.webp / stars-3840.webp | NASA/Goddard Space Flight Center Scientific Visualization Studio, Deep Star Maps; 8192 × 4096 haritanın ekvator bölgesinden 3840 × 2160 kaynak. Mobil 1280 × 720, normal masaüstü 1920 × 1080, yüksek DPR 3840 × 2160. |
| earth-day-night.webp / earth-still-2k.webp / earth-still-4k.webp | Uygulamanın aynı WebGL küresinin 4096 × 4096 olarak çizilmiş durağan çıktısı; 1024, 2048 ve 4096 piksel WebP. Büyük durağan görüntüler yalnızca WebGL çalışmadığında yüklenir. |

Resmî varlık adresleri:

- [Gündüz haritası](https://eoimages.gsfc.nasa.gov/images/imagerecords/73000/73909/world.topo.bathy.200412.3x5400x2700.jpg)
- [Gece ışıkları haritası](https://eoimages.gsfc.nasa.gov/images/imagerecords/79000/79765/dnb_land_ocean_ice.2012.3600x1800.jpg)
- [Bulut haritası](https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57747/cloud_combined_2048.jpg)
- [NASA Blue Marble açıklaması](https://science.nasa.gov/gallery/earth-blue-marble/)

Ek kaynaklar ve hazırlama:

- [NASA yüksek çözünürlüklü gece haritası](https://assets.science.nasa.gov/content/dam/science/esd/eo/images/imagerecords/79000/79765/dnb_land_ocean_ice.2012.13500x6750.jpg)
- [NASA Deep Star Maps ve atıf bilgisi](https://svs.gsfc.nasa.gov/3895/). NASA/Goddard Space Flight Center Scientific Visualization Studio; Ernie Wright ve Tom Bridgman.
- [Yıldız haritası kaynağı](https://svs.gsfc.nasa.gov/vis/a000000/a003800/a003895/starmap_8k.jpg)
- `scripts/prepare-login-assets.cjs`: mevcut kaynakları WebP ve responsive boyutlara dönüştürür; uygulamaya çalışma zamanı bağımlılığı eklemez.

Dünya 15 dakika yerine 12 dakikada bir tur atar (%25 hız artışı). GPU çizimi masaüstünde en fazla 2160, mobilde 1024 piksel ve 24 fps ile sınırlıdır. Gizli sekmede durur; azaltılmış hareket tercihinde sabit kare gösterilir. Gece, gündüz ve bulut dokuları görsel sunum amaçlı farklı dönemlere ait kompozitlerdir.

Marka logosu mevcut `assets/brand/logo-white.png` dosyasıdır; üretilmemiş ve geometrisi değiştirilmemiştir.

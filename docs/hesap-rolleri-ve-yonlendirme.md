# Hesaplar, roller ve eğitim tasarımına yönlendirme

4 Eylül 2026 — çalışan ve yönetici alanları artık ortak bir kullanıcı adı/parola
girişi kullanır. Önceki tarayıcı-kimliği sistemi yeni oturumları yetkilendirmez.

## Hesaplar

| Kullanıcı adı | Rol | Görünür talepler ve yetki |
|---|---|---|
| `calisan` | Çalışan | Kendi hesabından talep oluşturur, kendi kayıtlarını ve sonuçlarını takip eder. |
| `ihtiyac_admin` | İhtiyaç Analizi Yöneticisi | Tüm talepleri inceler; eğitim ihtiyacını doğrular, analiz sonucunu kaydeder ve ilgili şefliğe yönlendirir. İçerik/bağlantı yönetimi de bu roldedir. |
| `teknik_admin` | Teknik Eğitim Tasarım Yöneticisi | Yalnızca analizi tamamlanıp Teknik Eğitim Tasarım Şefliğine aktif olarak yönlendirilmiş talepleri görür ve yönetir. |
| `muhendislik_admin` | Mühendislik Eğitim Tasarım Yöneticisi | Yalnızca analizi tamamlanıp Mühendislik Eğitim Tasarım Şefliğine aktif olarak yönlendirilmiş talepleri görür ve yönetir. |

Bu dört yerel test hesabının erişim bilgileri **`data/portal-accounts.txt`**
dosyasındadır. Üç yöneticinin kullanıcı adı ve parolası birbirinden farklıdır.
İhtiyaç analizi hesabına önceki yönetici parola özeti taşındı; bu kurulumda
istenen `1234` parolası korunmuştur. Diğer üç hesap için farklı rastgele parolalar
oluşturuldu. Parolalar giriş ekranında veya loglarda yayımlanmaz.

Erişim dosyası yalnızca teslim notudur; içindeki metni değiştirmek veritabanındaki
parolayı değiştirmez. Uygulama yeniden başlayınca hesaplar/parolalar sıfırlanmaz.
Yeni bir çalışan hesabı ayrı bir `PortalUser` kaydı olarak açılabilir; aynı rolün
birden çok kullanıcıyla çalışması test edilmiştir. Self-servis kayıt, kullanıcı
yönetimi ve parola sıfırlama ekranı bu değişikliğin kapsamına dahil değildir.

## İş akışı

1. Çalışan kendi hesabıyla giriş yapar ve talebi gönderir. İlk yapay zekâ sonucu
   hazırlanır; talep **İhtiyaç analizinde** başlar.
2. İhtiyaç analizi yöneticisi metni, önerileri ve eksikleri değerlendirir.
3. Eğitim gerekiyorsa **Analizi tamamla ve şefliğe yönlendir** formunda:
   - İlgili eğitim tasarım şefliğini seçer.
   - En az 10 karakterlik ihtiyaç analizi sonucunu yazar.
   - Analizin tamamlandığını ve eğitim ihtiyacının doğrulandığını onaylar.
4. İşlem başarılı olunca talep **Eğitim tasarımına yönlendirildi** durumuna geçer.
   Yalnızca seçilen şefliğin yöneticisi o anda erişim kazanır. Diğer şeflik
   talebi, arama sonuçlarını veya onun sayaçlarını göremez.
5. İlgili tasarım yöneticisi çözüm planı/ek bilgi/çözüm durumunu açıklamayla
   kaydeder. Talebi ihtiyaç analizine geri gönderebilir fakat başka bir şefliğe
   kendisi yönlendiremez.
6. İhtiyaç analizine geri alınan talebin tasarım birimi erişimi kaldırılır.
   Birimin yeniden görmesi için ihtiyaç analizi yöneticisinin yeni yönlendirmesi
   gerekir. Başka şefliğe aktarım da önceki şefliğin erişimini kaldırır.

Çalışan çözülmüş talebi yeniden açabilir. Ek bilgi istenmişse açıklamasını
göndererek yeniden ihtiyaç analizine alabilir. Kritik talebi çalışan kapatamaz.
Yüksek içerik uyumu eğitim ihtiyacını insan adına onaylamaz ve talebi kapatmaz.

Konu taksonomisi (ör. Excel/C++/sistem mühendisliği) ile yönlendirilecek eğitim
tasarım birimi ayrı alanlardır. Formdaki sınır açıklaması teknik uygulama/araç/
üretim becerileri ile mühendislik tasarım/analiz/entegrasyonunu ayırır. Nihai
birim seçimi ihtiyaç analizi yöneticisine aittir; otomatik, geri alınamaz bir
kurumsal karar verilmez.

## Filtre düzeltmesi

Önceki arayüzde durum seçimi yalnızca form gönderildiğinde uygulanıyordu.
Artık **durum değişikliği anında** listeyi yeniler. Metin araması kısa yazma
aralığından sonra otomatik uygulanır; Filtrele/Enter da kullanılabilir. Arama ve
durum birlikte uygulanır, yeni filtrede sayfa başlangıca döner. Eski ağ yanıtları
son seçimin sonuçlarını ezemez. Sonuç yoksa önceki kayıtlar ekranda bırakılmaz.
Sunucu bilinmeyen durum değerlerini açıkça reddeder.

## Yetki ve oturum sınırları

- Rol, istemcide seçilmez; kullanıcı hesabından sunucuda belirlenir.
- Parolalar tuzlu PBKDF2-SHA256 (600.000 tur) özeti olarak tutulur.
- Yeni oturum çerezi HttpOnly, SameSite=Strict, HTTPS varsa Secure'dür.
- Oturum 8 saat sürer; girişte oturum belirteci yenilenir, çıkışta iptal edilir.
- Süresi bitmiş/pasif hesabın çerezi ve önceki parola-only yönetici çerezi
  yetki sağlamaz. Çıkışta özel ekran verisi temizlenir; gecikmiş analiz yanıtı
  başka hesaba geçildiğinde gösterilmez.
- Veri uçları giriş gerektirir. Çalışan başka çalışanın talebini numarasını
  bilerek okuyamaz, değiştiremez veya sohbet bağlamında kullanamaz.
- Tasarım yöneticileri ham içerik/model yönetimini ve diğer şefliğin taleplerini
  açamaz. Denetim yalnızca ekran gizlemekten ibaret değildir.
- Çalışan geçmişi hesap kimliğine bağlıdır; aynı hesapla başka tarayıcıdan görünür.

Bu bir **yerel test kurulumu**dur. Kurumsal SSO/MFA, kullanıcı açma-kapama süreçleri,
güçlü parola politikası, HTTPS dağıtımı, merkezi denetim izi ve yük/güvenlik
incelemesi üretim öncesinde ayrıca gerekir. `1234` canlı kullanım için uygun değildir.

## Veri koruma ve doğrulama

- Geçiş yedeği: `backups/20260904-account-roles-140111.db`.
- Önceki 15 talep, 18 eşleşme, 5 iş akışı, 13 durum olayı, değerlendirme ve
  öğrenilmiş eşleştirme değişmeden korundu. 8 PDF / 593 arama parçası korundu;
  PDF SHA-256 özetleri doğrulandı.
- Eski tarayıcıya ait kayıtların gerçek hesap sahibi bilinmediğinden bu kayıtlar
  rastgele bir çalışana atanmadı. İhtiyaç analizi yöneticisi görmeye devam eder;
  şefliklere ancak açık yönlendirmeyle açılır.
- 84 sunucu testi + 24 arayüz testi: **108 başarılı test**.
- Canlı dört hesapla giriş, girişsiz erişimin reddi, birime özel erişim, geri
  gönderme ve yeniden yönlendirme gerçek HTTP çağrılarıyla sınandı.
- Sentetik #16 talebi gerçek yerel arama + Groq analiziyle oluşturuldu, %96 içerik
  uyumu aldı. Teknik → ihtiyaç analizi → mühendislik akışı test edildi. Son olarak
  tarayıcıdaki formdan teknik şefliğe yönlendirme doğrulandı. Kayıt test olarak
  işaretlidir; gerçek eğitim görevlendirmesi değildir. Toplam kayıt sayısı 16'dır.
- Tarayıcıda kullanıcı adı/parola girişi, ihtiyaç analizi ekranı, anlık durum
  filtresi, boş sonuç, yönlendirme formu ve işlem geçmişi doğrulandı. Diğer üç
  hesabın giriş/rol akışı HTTP üzerinden sınandı; tüm rol ekranları için tam
  tarayıcı otomasyonu yapıldığı iddia edilmez.

Tekrar kontrol:

```text
.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test tests/frontend.test.cjs
.venv\Scripts\python.exe scripts\verify_portal_live.py
.venv\Scripts\python.exe scripts\verify_portal_preservation.py --backup backups/20260904-account-roles-140111.db
```

`verify_portal_live.py --exercise` ek olarak **yeni bir sentetik talep oluşturur**
ve yönlendirme akışını işletir; salt kontrol için bu seçenek verilmemelidir.

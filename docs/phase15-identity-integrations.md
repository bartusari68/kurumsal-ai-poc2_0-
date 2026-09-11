# Faz 15 — Enterprise Identity, Organization Sync ve İletişim Sınırları

Faz 15, mevcut named-account akışını koruyarak sağlayıcı-bağımsız kurumsal
entegrasyon sınırları ekler. Gerçek kurum credential'ı, tenant, LDAP adresi,
SMTP veya Teams webhook'u kaynak koda ya da veritabanına yazılmaz.

## Kimlik alanı

`PortalUser` uygulamadaki kişidir; `Identity` kimlik kaynağını (`LOCAL`,
`DIRECTORY`, `SSO`) temsil eder. `ExternalIdentityLink`, sağlayıcı ve dış
subject tekilliğiyle bir dış kimliği tek kullanıcıya bağlar. Dış kullanıcılar
yerel test parolasıyla otomatik olarak yerel hesaba dönüştürülmez; mevcut dört
yerel hesap çalışmaya devam eder.

OIDC sınırı state/nonce, geri dönüş adresi, issuer/audience ve token süresi
doğrulamasına hazırdır. Yapılandırma tamamlanmadan `/api/auth/oidc/start`
404 döner ve giriş ekranında SSO aksiyonu görünmez. Token değişimi gerçek
sağlayıcı adaptörüne bırakılmıştır.

## Organizasyon ve senkronizasyon

`OrganizationUnit` generic parent-child ağaçtır; seviye isimleri sabitlenmez ve
backend döngüleri reddeder. `OrganizationMembership` ve `UserManagerRelation`
geçerli/geçmiş kayıtları ayırır. Eski `UserOrganization` alanları korunur ve
directory kaynağı ayrıca işaretlenir.

`SyncRun` uygulanmış eşitlemelerin özetini; `IdentityConflict` deterministik,
incelenebilir alan çatışmalarını; `IntegrationAuditEvent` yalnızca anlamlı
değişiklikleri tutar. Dry-run kullanıcı, üyelik veya yetki kaydı yazmaz. Apply
explicit olarak istenir; dizinde görünmeyen kullanıcı silinmez, pasifleştirilir
ve oturumları kapatılır. Geçmiş talep/karar/evidence kayıtları silinmez.

Pozisyon anahtarı yalnızca `ExternalPositionMapping` ile mevcut bir
`PositionProfile`'a bağlanır; bilinmeyen anahtar profil üretmez. Dış grup ancak
`ExternalRoleMapping` ile mevcut bir uygulama rolüne bağlanır; bilinmeyen grup
çalışan (`EMPLOYEE`) güvenli varsayılanında kalır.

## İletişim

Mevcut in-app `operation_outbox` ve bildirimler otorite olmaya devam eder.
`CommunicationDelivery` yalnızca yapılandırılmış EMAIL/TEAMS kanalları için
event + kanal + alıcı idempotency anahtarıyla kuyruk kaydı açar. Sağlayıcılar
varsayılan olarak kapalıdır; başarısız harici teslim iş akışını geri almaz,
sınırlı ve kontrollü yeniden deneme ile `FAILED` olarak izlenir. Şablonlar
`resolve_template` üzerinden çözülür. UI/API hiçbir secret, raw token veya raw
claim döndürmez.

## Yönetim uçları

Yetkili yöneticiler için `/api/integrations` sağlayıcı durumunu, son eşitlemeyi,
çatışmaları, iletişim kuyruğunu ve dry-run/apply sınırını gösterir. Ayrıntılı
uçlar organization tree, identity detail, role/position mappings, conflicts,
sync-runs ve optional preferences yollarındadır. Çalışanlar entegrasyon
yönetim ekranını göremez.


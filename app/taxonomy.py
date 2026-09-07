"""Versioned, bounded learning taxonomy; domain and need type are separate axes."""
VERSION = "2026-09-v1"
TAXONOMY = [
    {"id": "DATA", "name": "Veri Analizi ve Raporlama", "boundary": "Çıktı tablo, rapor veya içgörüdür. Genel yazılım geliştirme bu gruba girmez.", "children": [
        ("EXCEL", "Excel ve Elektronik Tablolar", "Formüller, Pivot, Power Query, Excel raporları"),
        ("BI", "İş Zekâsı ve Görselleştirme", "Power BI, dashboard, DAX, görsel raporlama"),
        ("STATISTICS", "İstatistik ve Analitik", "İstatistik, deney tasarımı, veri yorumlama"),
        ("DATA_PIPELINES", "Veri Yönetimi ve SQL", "SQL, veri kalitesi, ETL ve veri modelleri") ]},
    {"id": "SOFTWARE", "name": "Yazılım Geliştirme ve Otomasyon", "boundary": "Çıktı çalışan kod veya yazılım hizmetidir. Hazır araç kullanımı ile ürün mühendisliği ayrıdır.", "children": [
        ("CPP", "C++ ve Sistem Programlama", "C++, bellek, performans, concurrency"),
        ("DOTNET", "C# ve .NET Uygulamaları", "C#, .NET, uygulama mimarisi"),
        ("PYTHON", "Python ve İş Otomasyonu", "Python betikleri, dosya ve iş akışı otomasyonu"),
        ("WEB", "Web, API ve Uygulama Geliştirme", "Arayüz, backend, API entegrasyonları"),
        ("DEVOPS", "Yazılım Testi ve DevOps", "Birim testi, Git, CI/CD, dağıtım") ]},
    {"id": "ENGINEERING", "name": "Ürün ve Sistem Mühendisliği", "boundary": "Fiziksel ürün veya mühendislik sistemi tasarlanır/doğrulanır. Dil öğrenimi Yazılım grubundadır.", "children": [
        ("DESIGN", "Mekanik Tasarım ve CAD", "Teknik resim, CAD, tasarım yöntemleri"),
        ("SIMULATION", "Analiz ve Simülasyon", "Yapısal, akışkan, termal analiz ve modelleme"),
        ("SYSTEMS", "Sistem Mühendisliği ve Entegrasyon", "Gereksinimler, arayüzler, doğrulama ve entegrasyon"),
        ("EMBEDDED", "Elektronik ve Gömülü Sistemler", "Elektronik, kontrol, gömülü donanım/yazılım entegrasyonu") ]},
    {"id": "OPERATIONS", "name": "Üretim, Bakım ve Operasyon", "boundary": "Mevcut ürün/ekipmanın üretilmesi veya işletilmesidir. Ürün tasarımı Mühendislik grubundadır.", "children": [
        ("MANUFACTURING", "Üretim ve Montaj", "İmalat, montaj, iş talimatı uygulaması"),
        ("MAINTENANCE", "Bakım ve Ekipman Kullanımı", "Bakım, arıza giderme, ekipman işletimi"),
        ("SUPPLY", "Tedarik, Planlama ve Lojistik", "Stok, üretim planlama, tedarik ve lojistik") ]},
    {"id": "QUALITY", "name": "Kalite ve Süreç İyileştirme", "boundary": "Kalite sistemi veya süreç performansı geliştirilir. Anlık emniyet tehlikesi Emniyet grubundadır.", "children": [
        ("QMS", "Kalite Sistemleri ve Denetim", "Kalite standardı, uygunluk ve denetim"),
        ("ROOT_CAUSE", "Kök Neden ve Problem Çözme", "8D, neden analizi, düzeltici faaliyet"),
        ("LEAN", "Süreç İyileştirme ve Yalın", "Yalın, süreç haritalama, verimlilik ölçümü") ]},
    {"id": "SAFETY", "name": "Emniyet, İş Güvenliği ve Çevre", "boundary": "İnsan, ürün veya çevre güvenliği odağıdır. Siber risk Siber Güvenlik grubundadır; risk seviyesi ayrıca belirlenir.", "children": [
        ("OHS", "İş Sağlığı ve Saha Güvenliği", "İş kazası önleme, kimyasal, acil durum"),
        ("PRODUCT", "Ürün ve Operasyon Emniyeti", "Ürün emniyeti, tehlike bildirimi, güvenli prosedür"),
        ("ENVIRONMENT", "Çevre ve Sürdürülebilirlik", "Atık, çevre etkisi, kaynak verimliliği") ]},
    {"id": "DIGITAL", "name": "Dijital Araçlar ve Yapay Zekâ", "boundary": "Hazır dijital araçların kullanımıdır. Excel analizi Veri; kod geliştirme Yazılım grubundadır.", "children": [
        ("AI_USE", "Üretken Yapay Zekâ Kullanımı", "İstem yazma, çıktı doğrulama, sorumlu kullanım"),
        ("COLLABORATION", "Ofis ve İş Birliği Araçları", "Word, sunum, Teams, belge iş birliği"),
        ("ENTERPRISE", "Kurumsal Uygulamalar", "ERP, PLM, kurum içi uygulama kullanımı") ]},
    {"id": "CYBER", "name": "Bilgi ve Siber Güvenlik", "boundary": "Bilginin gizliliği ve dijital sistem güvenliği odağıdır. Fiziksel iş güvenliği ayrıdır.", "children": [
        ("AWARENESS", "Bilgi Güvenliği Farkındalığı", "Kimlik avı, veri sınıflandırma, güvenli paylaşım"),
        ("TECHNICAL", "Teknik Siber Güvenlik", "Ağ, erişim, güvenli geliştirme, olay müdahalesi") ]},
    {"id": "MANAGEMENT", "name": "Proje ve İş Yönetimi", "boundary": "İşin kapsamı, süresi, kaynakları ve paydaşları yönetilir. İnsan liderliği ayrı gruptur.", "children": [
        ("PROJECT", "Proje Planlama ve Takip", "Takvim, kapsam, kaynak, çevik çalışma"),
        ("RISK", "Proje Riski ve Karar Verme", "Proje riski, karar yöntemleri, paydaş yönetimi"),
        ("BUSINESS", "Finans ve Ticari Yetkinlikler", "Bütçe, maliyet, satın alma ve sözleşme okuryazarlığı") ]},
    {"id": "PEOPLE", "name": "Liderlik ve Kişisel Yetkinlikler", "boundary": "İnsan davranışı, iletişim ve kişisel çalışma becerileridir. Teknik süreç optimizasyonu Kalite grubundadır.", "children": [
        ("LEADERSHIP", "Ekip Liderliği ve Koçluk", "Geri bildirim, delegasyon, ekip gelişimi"),
        ("COMMUNICATION", "İletişim ve Paydaş İlişkileri", "Sunum becerisi, müzakere, çatışma çözümü"),
        ("PRODUCTIVITY", "Kişisel İş Planlama", "Zaman yönetimi, odaklanma, kişisel önceliklendirme") ]},
    {"id": "OTHER", "name": "Kapsam Netleştirme", "boundary": "Tanımlı gruplara uymayan veya konusu belirsiz ihtiyaçlar zorlanmadan insan incelemesine ayrılır.", "children": [
        ("REVIEW", "Yeni veya Belirsiz Konu", "Ek bağlam veya yeni alt kategori değerlendirmesi gerekir") ]},
]
INDEX = {f"{group['id']}.{code}": {"category_id": group["id"], "category": group["name"],
         "subcategory_id": f"{group['id']}.{code}", "subcategory": name, "description": description}
         for group in TAXONOMY for code, name, description in group["children"]}


def normalize_category(code):
    return dict(INDEX.get(str(code).upper(), INDEX["OTHER.REVIEW"]))


def public_taxonomy():
    return {"version": VERSION, "groups": [{**group, "children": [
        {"id": f"{group['id']}.{code}", "name": name, "description": description}
        for code, name, description in group["children"]]} for group in TAXONOMY]}


def prompt_taxonomy():
    return "\n".join(group["name"] + ": " + group["boundary"] + "\n" + "; ".join(
        f"{group['id']}.{code}={name}" for code, name, _ in group["children"]) for group in TAXONOMY)

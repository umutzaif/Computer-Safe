# Computer-Safe

Bilgisayarınızın kamerasıyla önündeki hareketi algılayan, alarm çalan, olayı
**zaman damgalı video ve fotoğraf** olarak kaydeden ve size **e-posta** ile
bildiren bir Windows uygulaması. OpenCV'nin arka plan çıkarma (MOG2) algoritmasını
kullanır.

> *English summary:* Computer-Safe watches your webcam while you are away. On
> motion it sounds an alarm, records timestamped video/snapshots to a folder you
> choose, e-mails you (queued and retried when offline) and can lock or shut
> down the PC. SMTP passwords are kept in Windows Credential Manager; the admin
> password is stored only as a salted PBKDF2 hash. Ships as a single `.exe`.

## Özellikler

- **Tek dosyalık exe** – Python kurmadan çalışır (`ComputerSafe.exe`).
- **Ayarlar penceresi** – kayıt klasörü, kamera, hassasiyet, e-posta alıcıları vb.
  tamamen arayüzden ayarlanır; koda dokunmak gerekmez.
- **Zaman damgalı kayıt** – hareket başlayınca video kaydı başlar (hareketten
  önceki 2 sn dahil), hareket bitince kapanır. Dosyalar gün klasörlerine kaydedilir:
  ```
  Kayıt klasörü\2026-11-20\ComputerSafe_2026-11-20_21-15-03.mp4
  Kayıt klasörü\2026-11-20\ComputerSafe_2026-11-20_21-15-03.jpg
  ```
  Görüntünün üzerine de tarih-saat yazılır.
- **Kademeli alarm**
  1. Hareket → bip sesi, kayıt başlar
  2. Uyarı eşiği → alarm sesi + fotoğraflı e-posta
  3. Kritik eşik → ikinci alarm + e-posta + seçilen işlem (ekranı kilitle /
     bilgisayarı 60 sn sonra kapat / hiçbir şey yapma)
  4. Video tamamlanınca videolu e-posta
- **İnternet yokken çökmez** – e-postalar önce diske (kuyruğa) yazılır; bağlantı
  yoksa kuyrukta bekler ve internet gelince otomatik gönderilir. Program kapanıp
  açılsa bile bekleyen e-postalar kaybolmaz.
- **Şifre güvenliği** – bkz. [Güvenlik](#güvenlik).
- **Yönetici şifresi** – koruma, yönetici şifresi girilmeden durdurulamaz;
  3 hatalı denemede 30 sn kilitlenir.
- **Windows açılışında otomatik başlatma** (isteğe bağlı).
- **Kamera koparsa** program kapanmaz, kamerayı yeniden bağlamayı dener.

## Kullanım

1. `ComputerSafe.exe`'yi çalıştırın. (İmzasız exe olduğu için Windows SmartScreen
   uyarı verebilir: *Ek bilgi → Yine de çalıştır*.)
2. İlk açılışta bir **yönetici şifresi** belirleyin.
3. Ayarlar penceresinde:
   - **Genel:** kayıt klasörünü seçin, saldırı eşiğinde yapılacak işlemi belirleyin.
   - **E-posta:** servis seçin (Outlook, Gmail, Yandex...), gönderen adresi,
     şifreyi ve alıcıları (virgülle) girin. **Test e-postası gönder** ile deneyin.
   - **Algılama:** hassasiyeti ortamınıza göre deneyerek ayarlayın.
4. **Korumayı Başlat**'a basın. Başlangıç gecikmesi süresince (varsayılan 10 sn)
   ortamdan uzaklaşın; program bu sürede arka planı öğrenir.
5. Durdurmak için **Korumayı Durdur**'a basıp yönetici şifresini girin.

### E-posta şifresi hakkında

Gmail, Outlook ve Yandex gibi servisler normal hesap şifresiyle SMTP girişine
genellikle izin vermez. İki adımlı doğrulamayı açıp hesabınızdan bir
**uygulama şifresi** oluşturun ve onu kullanın:

- Gmail: Google Hesabı → Güvenlik → Uygulama şifreleri
- Outlook/Hotmail: Microsoft hesabı → Güvenlik → Gelişmiş güvenlik seçenekleri → Uygulama şifreleri
  (Microsoft bazı kişisel hesaplarda SMTP ile şifre girişini kapatmış olabilir; bu durumda Gmail önerilir.)

## Güvenlik

| Bilgi | Nasıl saklanır |
| --- | --- |
| Yönetici şifresi | Sadece **PBKDF2-HMAC-SHA256** özeti (600.000 iterasyon, rastgele 16 bayt tuz). Şifrenin kendisi hiçbir yerde tutulmaz; doğrulama sabit zamanlı karşılaştırma ile yapılır. |
| E-posta (SMTP) şifresi | **Windows Kimlik Bilgisi Yöneticisi**'nde (Credential Manager). Windows bunu DPAPI ile kullanıcı hesabınıza bağlı olarak şifreler. Ayar dosyasına veya diske düz metin yazılmaz. |
| Diğer ayarlar | `%APPDATA%\ComputerSafe\config.json` |

> Neden e-posta şifresi de hash'lenmiyor? Hash tek yönlüdür; SMTP sunucusuna
> giriş yaparken şifrenin kendisini göndermek gerekir. Bu yüzden geri
> çözülebilmesi gereken sırlar için doğru yöntem, işletim sisteminin şifreli
> kasasıdır. Hash, yalnızca doğrulanması gereken yönetici şifresi için kullanılır.

## Dosya konumları

| Ne | Nerede |
| --- | --- |
| Ayarlar | `%APPDATA%\ComputerSafe\config.json` |
| Log dosyası | `%APPDATA%\ComputerSafe\logs\computer_safe.log` |
| Gönderilmeyi bekleyen e-postalar | `%APPDATA%\ComputerSafe\outbox\` |
| Video / fotoğraflar | Ayarlarda seçtiğiniz klasör (varsayılan `Videolar\ComputerSafe`) |

Sorun giderme: `ComputerSafe.exe --self-test` ses dosyalarını, şifre kasasını ve
kamerayı kontrol edip sonucu log dosyasına yazar.

## Geliştirme

Gereksinim: Windows, Python 3.10+ (tkinter dahil).

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe koruma.py        # kaynak koddan çalıştır
.\.venv\Scripts\python.exe -m pytest -q     # testler
```

Exe derlemek (testleri çalıştırır, `dist\ComputerSafe.exe` üretir):

```powershell
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

### Proje yapısı

```
koruma.py                  Başlatıcı
computer_safe/
  app.py                   Giriş noktası, log, tek kopya kontrolü
  config.py                Ayarlar (JSON)
  security.py              PBKDF2 şifre özeti + Windows Kimlik Bilgisi Yöneticisi
  monitor.py               Kamera döngüsü ve alarm seviyeleri
  detector.py              MOG2 hareket algılama
  recorder.py              Zaman damgalı video / fotoğraf kaydı
  mailer.py                Çevrimdışı kuyruklu e-posta gönderimi
  alarm.py                 Sesler, ekran kilitleme, kapatma
  overlay.py               Görüntü üzerindeki yazılar
  autostart.py             Windows açılışında başlatma
  gui/                     Tkinter pencereleri
assets/                    Alarm sesleri
tests/                     Birim testleri
```

# 💻 Güvenlik Kamerası ve İzinsiz Giriş Tespit Sistemi (OpenCV Tabanlı)

Bu proje, bir bilgisayarın gözetimsiz bırakıldığı durumlarda **izinsiz girişleri tespit etmek** ve potansiyel davetsiz misafirleri caydırmak için **OpenCV** kütüphanesinin gücünden yararlanır. Sistem, web kamerası görüntülerindeki piksel değişikliklerini izler ve belirlenen eşiğin üzerinde bir hareket algılandığında bir alarm çalarak kullanıcıyı uyarır.

> "Bilgisayarınıza kötü niyetli planlar kuranları korkudan çılgına çevirecek bir program!"

---

## ✨ Özellikler

* **Hareket Algılama:** OpenCV ile canlı kamera görüntüsündeki **değişen pikselleri** tespit eder.
* **Sesli Alarm:** Belirlenen hareket eşiği aşıldığında bir uyarı alarmı çalar (yüklediğiniz dosya yolunda).
* **Saldırgan Fotoğrafı Çekme:** İzinsiz giriş yapan kişinin fotoğrafını çekme yeteneği.
* **E-posta Bildirimi (Opsiyonel):** Çekilen fotoğrafları size e-posta ile gönderme imkanı (kodda yorum satırı olarak mevcuttur).
* **Kişiselleştirilebilir Hassasiyet:** Çevreye göre ayarlanabilir hareket algılama hassasiyeti (`pixelcounter` değişkeni).
* **Güvenli Kapatma (Opsiyonel):** Saldırı durumunda bilgisayarı kapatma komutu.
* **Geri Sayım (Intro):** Program başladığında ortamdan ayrılmanız için süre tanıyan başlangıç bloğu.

---

## 🛠️ Kurulum

Projeyi çalıştırmak için gerekli Python kütüphanelerini kurmanız gerekmektedir.

1.  Gerekli kütüphaneleri (başta **OpenCV**) kurun:

    ```bash
    pip install opencv-python
    ```
    
    > **Not:** Alarm sesini çalmak için kullandığınız kütüphaneyi de buraya eklemeyi unutmayın (örneğin, `playsound` veya `simpleaudio`).

2.  Kodu yerel bilgisayarınıza indirin veya klonlayın.
3.  Kamera ve internet bağlantınızın çalıştığından emin olun.

---

## ⚙️ Ayarlar ve Kişiselleştirme

Program, farklı senaryolara ve kişisel tercihlere göre kolayca özelleştirilebilecek değişkenler içerir. Lütfen kodu inceleyerek aşağıdaki ayarları **Türkçe yorum satırları** doğrultusunda değiştirin:

### 1. Hareket Algılama Hassasiyeti

* **Değişken:** `pixelcounter`
* **Açıklama:** Bu değişken, hareketin algılanması için değişmesi gereken minimum piksel sayısını belirler. Çevrenizdeki ışık, kamera kalitesi ve ortamdaki titreşimlere göre en doğru değeri bulmak için denemeler yapın.

### 2. Alarm Sesi Ayarları

* **Değişkenler:** `f` ve `d`
* **Açıklama:**
    * `f` değişkeni: Alarm sesinin **frekansını (tone)** belirler.
    * `d` değişkeni: Alarm sesinin çalınma **sıklığını (frequency)** ayarlar.

### 3. Başlangıç (Intro) Süresi

Bu blok, program açıldığında ortamdan ayrılmanız için size süre tanır.

* **Geri Sayım Tekrarı:** `a` değişkeni, intro bloğunun kaç kez sayım yapacağını belirler.
* **Gecikme Süresi:** `cv2.waitkey()` fonksiyonunun içindeki parametreyi değiştirin. Buradaki değer milisaniye cinsindendir. Örneğin, 5 saniye bekleme için `5000` değerini kullanın.

### 4. Gelişmiş Özellikler (E-posta & Kapatma)

Bu özellikler, varsayılan olarak **yorum satırı** (`#`) içindedir ve kullanmak için yorum işaretleri kaldırılmalıdır.

| Özellik | Açıklama | Dikkat Edilmesi Gerekenler |
| :--- | :--- | :--- |
| **E-posta Gönderme** | Saldırganın fotoğrafını size e-posta ile gönderir. | **Kodu yorum satırından kaldırırsanız, cihazınız internete bağlıyken e-posta gönderme komutları hata verecektir.** Bu komutları yalnızca internet bağlantısı kesikken ve uygun e-posta kütüphanesi yapılandırması yapılmışken kullanmalısınız. |
| **Bilgisayarı Kapatma** | İzinsiz giriş durumunda bilgisayarı kapatır (`os.system("poweroff")`). | Mevcut komut (`os.system("poweroff")`) **Linux terminalleri** için uygundur. Windows veya Mac kullanıcıları, işletim sistemlerine uygun kapatma komutunu (örneğin Windows için `shutdown /s /t 1`) bu parametre ile değiştirmelidir. |

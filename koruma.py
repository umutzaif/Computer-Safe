
import cv2
import numpy as np
import os
import time

time.sleep(5)
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.utils import COMMASPACE
from email import encoders
"""
import sounddevice as sd

def beep():
    frequency = 1000  # Hz
    duration = 100  # milliseconds
    sd.play(0.5 * np.sin(2 * np.pi * frequency * np.arange(44100 * duration // 1000) / 44100), 44100)
    sd.wait()

"""""
#mail gönderme için smtp ayarı 
smtp_server = "smtp.office365.com"
smtp_port = 587
server = smtplib.SMTP(smtp_server, smtp_port)
server.starttls()
#gönderen mail ayarı
from_email = 'email@example.com'
from_email_password = 'password'
server.login(from_email, from_email_password)
#alıcı mail ayarı ve içerik ayarı
to_email = 'receiver@exapmle.com'
subject = 'PC Bildirimi'
body = 'Bilgisayarınız açıldı'
message = MIMEMultipart()
message['From'] = from_email
message['To'] = to_email
message['Subject'] = subject
message.attach(MIMEText(body, 'plain'))
server.sendmail(from_email, to_email, message.as_string())
server.quit()
"""

f = 2300
d = 300

# Video Yakalama için VideoCapture kullanıyoruz ve (0) dediğimiz ise kameranın listedeki yeri
#yani eğer 2 tane kameramız varsa 2. kamerayı açmal için (1) yazmamız lazım.
capture = cv2.VideoCapture(0)


# Maskeleyeceğimiz yere 3 değer atıyoruz = History, Threshold, DetectShadows
# History:Arkaplanda kaç frame olduğunda arkaplanı modeli yenileneceğini seçiyor. Yani arkaplanı bir kere daha yeniliyor.Kaç pixel aklında ttucağını seçiyor.
# Threshold: önceki pik frame ve önceki pozisyonu ve sonraki pozisyonu aklında tutuyor. Birbirinde ne kadar farklı olduğunu belirliyor.
#eğer history değerini çok yüksek tutarsak resimdeki değişikliği aklında dah uzun süre tutabilir.
maske = cv2.createBackgroundSubtractorMOG2(500, 750, True)
# hangi frame'de olduğumuzu takip edecek
kare_sayisi = 0
"""a = 6
while a<7:
	ret, frame_yen = capture.read()
	if a==0:
		cv2.putText(frame_yen,"KORUMA", (250,215), cv2.FONT_HERSHEY_COMPLEX, 1, (0,255,255), 2, cv2.LINE_AA)
		cv2.putText(frame_yen,"BASLATILIYOR", (210,245), cv2.FONT_HERSHEY_COMPLEX, 1, (0,255,255), 2, cv2.LINE_AA)
		cv2.imshow("intro", frame_yen)
		cv2.waitKey(2000)
		#capture.release()
		cv2.destroyAllWindows()
		break
	if a!= 0: 
		cv2.putText(frame_yen,"{}".format(np.round(a-1)), (315,235), cv2.FONT_HERSHEY_COMPLEX, 1, (0,255,255), 2, cv2.LINE_AA)
		vo.Beep(4000,300)
		cv2.waitKey(700)
		cv2.imshow("intro", frame_yen)
	if a==-1:
		#capture.release()
		cv2.destroyAllWindows()
		break
	a = a-1
	
"""
saldiri_sayisi = 0

while(1):
	#Anlık frame değerinin return ediyoruz.
	ret, frame = capture.read()
	# Bir değer var mı diye kontrol ediyoruz yoksa çıkıyoruz döngüden
	if not ret:
		break
	
	kare_sayisi += 1
	#frame'i yeniden boyutlandırıyoruz
	frame_yeni = cv2.resize(frame, (0, 0), fx=1, fy=1) #frame dsize,

	# Yeni frame in boyutunda yuzey maskesi oluşturuyoruz.
	yuzey_maske = maske.apply(frame_yeni)

	# Maske'deki siyah olmayan pixeller sayılıyor.
	pixelsayaci = np.count_nonzero(yuzey_maske)
	yuzey_cnts = cv2.findContours(yuzey_maske, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[-2]
	#çıktıyı alıyoruz
	print('Görüntü: %d, Değişen pixel sayısı: %d' % (kare_sayisi, pixelsayaci))
	#Maske'nin değerleri vektör olarak x,y,w,h sabitlerine atıyoruz.
	#x,y pencere boyutu ve w,h genişlik ve uzunluğu
	x, y, w, h = cv2.boundingRect(yuzey_maske)

	war = frame
	alarm_durumu = False
	
	cv2.putText(frame_yeni, "With Dalga IT", (460, 455), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
	# Eğer değişen pixel sayısı belli sayıdan yuksekse hareket olarak algılanacak
	# ilk başta frame çok küçük olduğunda siyah ekrala karşılaşabilir ondan dolayı 1'den buyuk olup olmadığını kontrol ediyoruz.
	if (kare_sayisi > 1 and pixelsayaci > 500):
		print('Hareket Algılandı')
		if len(yuzey_cnts) > 0:
			yuzey_cnts = max(yuzey_cnts, key=cv2.contourArea)
			(x, y, w, h) = cv2.boundingRect(yuzey_cnts)
			cv2.rectangle(frame_yeni, (x, y), (x + w, y + h), (0, 0, 255), 2)
			cv2.putText(frame_yeni, "System Capture", (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
		if (not alarm_durumu):
       		# Hareket algılandığında fotoğrafı kaydet
			#cv2.imwrite("image saving path", frame_yeni)
			alarm_durumu = True
		#Hareket edilen yer bulunduğunda dörtgen içine alınıyor
		
		cv2.rectangle(frame_yeni, (10,10), (200, 50), (0, 0, 255),-1)
		cv2.rectangle(frame_yeni, (10,10),(630,470), (0, 0, 255), 5 )
		cv2.putText(frame_yeni, "ALARM", (55,40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2, cv2.LINE_AA)
		saldiri_sayisi = saldiri_sayisi + 1
		print("Saldırı Sayısı: {}".format(np.round(saldiri_sayisi)))
		cv2.putText(frame_yeni, "Saldiri Sayisi: {}".format(np.round(saldiri_sayisi)), (15,460), cv2.FONT_HERSHEY_COMPLEX_SMALL, 1, (0,0,255), 2, cv2.LINE_4)
		beep()
	else:
		cv2.rectangle(frame_yeni, (10,10), (200, 50), (0, 255, 0),-1)
		cv2.rectangle(frame_yeni, (10,10),(630,470), (0, 255, 0), 5 )
		cv2.putText(frame_yeni, "SAFETY", (55,40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255,255,255), 2, cv2.LINE_AA)
	if saldiri_sayisi == 30:
		os.system("<voice warning path>")
		cv2.waitKey(100)
	elif saldiri_sayisi == 40:
		os.system("voice file path")
	elif saldiri_sayisi == 60:
		
		""""
		msg = MIMEMultipart()
		msg['From'] = 'sender@example.com'
		msg['To'] = COMMASPACE.join(['receiver@example.com'])
		msg['Subject'] = 'PC INFO'
		body2 = 'Saldırı eşiği aşıldı. Saldırganların videosu postaya eklendi, Bilgisayarınız kapatıldı.'
		msg.attach(MIMEText(body2, 'plain'))
		filename = r'<file path>'
		attachment = open(filename, 'rb')
		part = MIMEBase('application', 'octet-stream')
		part.set_payload((attachment).read())
		encoders.encode_base64(part)
		part.add_header('Content-Disposition', 'attachment', filename=filename)
		msg.attach(part)

		# e-postayı gönderme
		server2 = smtplib.SMTP('smtp.office365.com', 587)
		server2.starttls()
		server2.login('sender@example.com', ['sender@example.com'], msg.as_string())
		server2.quit()
		"""
		#playsound(r"voice file path")
		os.system("mplayer <voice warning path>")
		cv2.waitKey(1000)
		os.system("poweroff")
		break
	cv2.imshow("frame", frame_yeni)

	k = cv2.waitKey(1) & 0xff
	if k == 27: #escape tuşuna basınca çıkar
		break
	

#döngüden çıktıktan sonra yakalamalar iptal ediliyor ve tüm pencereleri kapatıyoruz
capture.release()

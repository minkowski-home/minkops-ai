import deepspeech
import mysql.connector
from all_legacy_code.src import face_mgmt
import legacy

ds = deepspeech.Model('../resources/deepspeech/saved/deepspeech-0.9.3-models.pbmm')

chato_audio_db = mysql.connector.connect(
    host='localhost',
    user='root',
    password='0301sonaL',
    database='chato_audio',
    auth_plugin='mysql_native_password'
)
audio_cursor = chato_audio_db.cursor()

chato_customer_db = mysql.connector.connect(
    host='localhost',
    user='root',
    password='0301sonaL',
    database='chato_customer',
    auth_plugin='mysql_native_password'
)
customer_cursor = chato_customer_db.cursor()

face_id, person_name = face_mgmt.match_face(cursor=customer_cursor)


print(person_name)
if person_name:
    legacy.speak(f'Hi {person_name}, how can I help you today?')
    speech = legacy.listen()
else:
    legacy.speak(f'Hi, how can I help you today?')
    speech = legacy.listen()

# NLP working here...

stt = ds.stt(speech)
print(stt)
legacy.speak(stt)

chato_customer_db.close()
chato_audio_db.close()
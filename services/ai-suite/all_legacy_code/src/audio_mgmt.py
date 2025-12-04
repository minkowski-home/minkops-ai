from typing import Any, Union, Tuple
import sounddevice
import speech_recognition as sr
from google.cloud import texttospeech
import pygame
from io import BytesIO

mp3_fp = BytesIO()
recognizer = sr.Recognizer()
pygame.mixer.init()

from google.oauth2 import service_account
from google.cloud import texttospeech


def speech_to_text() -> str:
    with sr.Microphone() as source:
        print('Listening..')
        while True:
            # audio = recognizer.listen(source, timeout=5, phrase_time_limit=6)
            try:
                audio = recognizer.listen(source, timeout=5, phrase_time_limit=6)
                text = recognizer.recognize_google(audio)
                print(text)
                return text

            except sr.WaitTimeoutError:
                return ''
            except sr.UnknownValueError:
                return ''
            except sr.RequestError as e:
                speak('Something went wrong, please find a human employee to address the issue.')
                return ''


# def speak(text: str, tld='com.au', lang='en') -> None:
#     tts = gTTS(text, tld, lang)
#     mp3_fp.seek(0)
#     mp3_fp.truncate()
#     tts.write_to_fp(mp3_fp)
#
#     mp3_fp.seek(0)
#     pygame.mixer.music.load(BytesIO(mp3_fp.read()))
#     pygame.mixer.music.play()
#     while pygame.mixer.music.get_busy():
#         pass
#
#     pygame.mixer.music.stop()

def speak(text: str, language_code='en-CA', accent='en-AU-Wavenet-C', pitch=1.7, speaking_rate=1.0):
    credentials = service_account.Credentials.from_service_account_file('/home/crow/Iota/pluseleven/pluseleven-4df799251cd4.json')
    client = texttospeech.TextToSpeechClient(credentials=credentials)

    # Set the text input to be synthesized
    synthesis_input = texttospeech.SynthesisInput(text=text)

    # Build the voice request, select the language code and the ssml voice gender
    voice = texttospeech.VoiceSelectionParams(
        language_code=language_code,
        name=accent,
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )

    # Select the type of audio file you want returned
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        pitch=pitch,
        speaking_rate=speaking_rate
    )

    # Perform the text-to-speech request on the text input with the selected voice parameters and audio file type
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    # The response's audio_content is binary
    audio_content = BytesIO(response.audio_content)

    pygame.mixer.init()
    pygame.mixer.music.load(audio_content)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        continue

    pygame.mixer.music.stop()

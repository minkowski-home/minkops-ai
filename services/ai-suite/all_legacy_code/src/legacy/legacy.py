import threading

import keyboard
import numpy as np
import pyaudio
import pyttsx3
import webrtcvad


def listen() -> np.ndarray:
    """
     Listens to audio input from the default microphone, detects speech using VAD (Voice Activity Detection),
    and stops recording upon detecting silence for a specific duration or if 'q' is pressed. The captured
    audio is returned as a NumPy array.

    The function starts a separate thread for recording audio while monitoring the keyboard for a stop
    signal (pressing 'q') in the main thread.

    Returns:
        np.ndarray: A 1D numpy array containing the recorded audio data.
    """
    frames = []
    got_speech = False
    num_silent_chunks = 0
    stop_flag = [False]  # Using a list to make it mutable inside the threaded function

    def record_audio():
        vad = webrtcvad.Vad()
        vad.set_mode(1)

        p = pyaudio.PyAudio()
        sample_rate = 16000
        chunk_duration = 30
        chunk_size = int(sample_rate * chunk_duration / 1000)

        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=sample_rate,
            input=True,
            frames_per_buffer=chunk_size,
        )

        print("Listening...")
        nonlocal frames, got_speech, num_silent_chunks
        while True:
            chunk = stream.read(chunk_size)
            chunk_np = np.frombuffer(chunk, dtype=np.int16)

            is_speech = vad.is_speech(chunk, sample_rate)

            if got_speech and not is_speech:
                num_silent_chunks += 1
            elif is_speech:
                got_speech = True
                num_silent_chunks = 0
                frames.append(chunk_np)

            if num_silent_chunks > 50 or stop_flag[0]:
                print("Detected silence or 'q' pressed. Stopping recording...")
                stream.stop_stream()
                stream.close()
                p.terminate()
                break

    audio_thread = threading.Thread(target=record_audio)
    audio_thread.start()

    print("Press 'q' to stop the recording.")
    keyboard.wait('q')
    stop_flag[0] = True
    audio_thread.join()

    return np.concatenate(frames, axis=0)


# Initialize TTS engine
engine = pyttsx3.init()
voices = engine.getProperty('voices')
engine.setProperty('voice', voices[1].id)


def speak(response: str) -> None:
    """
    This function speaks out loud whatever string is passed in response argument.

    Args:
        response: A string to synthesize

    Returns: None
    """
    engine.say(response)
    engine.runAndWait()

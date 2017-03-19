import pyaudio
import wave
import threading

class AudioRecorder():
    
    # Audio class based on pyAudio and Wave
    def __init__(self):
        
        self.recording = False

        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = 2
        self.RATE = 44100
        self.CHUNK = 1024
        self.RECORD_SECONDS = 5
        self.WAVE_OUTPUT_FILENAME = "file.wav"        

        self.audio_frames = []

    

    # Audio starts being recorded
    def _start_recording(self):
        
        self.audio = pyaudio.PyAudio()
         
        # start Recording
        self.stream = self.audio.open(format=self.FORMAT, channels=self.CHANNELS,
                        rate=self.RATE, input=True,
                        frames_per_buffer=self.CHUNK)
        
        print "\nrecording...\n"
        while self.recording == True:
            data = self.stream.read(self.CHUNK)
            self.audio_frames.append(data)

            if self.recording == False:
                break
        
        print "\nfinished recording\n"
        self._stop_recording()
         
         
                
    # Finishes the audio recording therefore the thread too    
    def _stop_recording(self):
        """ Stops audio recording and saves recording to a .wav file
        
        filename -- must specify .wav extension
        """

        # stop Recording
        self.stream.stop_stream()
        self.stream.close()
        self.audio.terminate()
         
        waveFile = wave.open(self.WAVE_OUTPUT_FILENAME, 'wb')
        waveFile.setnchannels(self.CHANNELS)
        waveFile.setsampwidth(self.audio.get_sample_size(self.FORMAT))
        waveFile.setframerate(self.RATE)
        waveFile.writeframes(b''.join(self.audio_frames))
        waveFile.close()

        
    
    # Launches the audio recording function using a thread
    def start(self):   
        self.recording = True
        audio_thread = threading.Thread(target=self._start_recording)
        audio_thread.start()


    def stop(self, filename):
        self.WAVE_OUTPUT_FILENAME = filename
        self.recording = False

    def cancel(self):
        self.recording = False
    


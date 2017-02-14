
from PyQt5 import QtGui, QtCore, QtWidgets


import cv2
import datetime
import json
import numpy
import os
import requests
import subprocess
import sys
import threading
import time


# my modules
import audiorecorder
import avrecorder
import youtube_upload


TEMPORARY_AUDIO_DIR = 'videos/temp_audio'
TEMPORARY_VIDEO_DIR = 'videos/temp_video'
FINAL_AV_DIR = 'videos/final'

PROMPTS = [
    'What is your hometown and what is your favorite thing about it?',
    'What did you do for fun last weekend?',
    'What is a project you are working on right now?',
    'Who is your favorite author and why?'
]


class CameraDevice(QtWidgets.QWidget):

    newFrame = QtCore.pyqtSignal(numpy.ndarray)
    
    def __init__(self):
        super(QtWidgets.QWidget, self).__init__()

        self.fps = 10
        self.frameSize = (640, 480) # video formats and sizes also depend and vary according to the camera used
        
        # capture input from camera
        self.cap = cv2.VideoCapture(0)
        self.cap.set(3, 640)
        self.cap.set(4, 480)

        # don't record until user clicks start
        self.recording = False        


        # start preview
        self.initUI()



    def initUI(self):
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.nextFrameSlot)
        self.timer.start(1000./self.fps)        


    def nextFrameSlot(self):
        ret, frame = self.cap.read() 

        # fix color of what is saved
        cv2.cvtColor(frame, cv2.COLOR_BGRA2RGBA, frame)

        # emit signal to update UI
        self.newFrame.emit(frame)   

        
        # write frames to file if recording
        if self.recording:
            self.video_out.write(frame)

            # track frame counts for video processing
            self.frame_counts += 1


    def set_filenames(self, start_time):

        default_name = str(start_time)

        self.temp_audio_filename = default_name
        self.temp_audio_extension = '.wav'
        self.temp_audio_filepath = os.path.join(TEMPORARY_AUDIO_DIR, 
            self.temp_audio_filename + self.temp_audio_extension)
 
        self.temp_video_filename = default_name
        self.temp_video_extension = '.mp4'
        self.temp_video_filepath = os.path.join(TEMPORARY_VIDEO_DIR, 
            self.temp_video_filename + self.temp_video_extension)     

        self.temp_video_filepath_2 = os.path.join(TEMPORARY_VIDEO_DIR,
            self.temp_video_filename + '_2_' + self.temp_video_extension)   

        self.final_video_filepath = os.path.join(FINAL_AV_DIR,
            default_name + '.mp4')


    def start(self):
        """Start video and audio recording"""

        if self.recording:
            return
        
        # reset frame counts for video processing
        self.frame_counts = 0

        # reset start time for video processing
        self.start_time = time.time()

        # set filenames, must do before creating VideoWriter
        self.set_filenames(self.start_time)

        # create object for video recording
        self.fourcc = cv2.cv.FOURCC(*'mp4v') 
        self.video_out = cv2.VideoWriter(self.temp_video_filepath, 
            self.fourcc, self.fps, self.frameSize, True)

        # audio recording
        self.microphone = audiorecorder.AudioRecorder()


        # start recording video
        self.recording = True

        # start recording audio
        self.microphone.start()

        print 'Started video and audio recording'
        

    def stop(self):
        """Stop video and audio recording"""
        self.recording = False
        self.microphone.stop(self.temp_audio_filepath)

        print 'Stopped video and audio recording'

        # Stop audio and video recording
        processing_thread = threading.Thread(target=self.process_AV_files)
        processing_thread.start()
        



    def process_AV_files(self):

        filename = self.final_video_filepath
        
        frame_counts = self.frame_counts
        elapsed_time = time.time() - self.start_time
        recorded_fps = frame_counts / elapsed_time
        print "total frames " + str(frame_counts)
        print "elapsed time " + str(elapsed_time)
        print "recorded fps " + str(recorded_fps)
    

        # Merging audio and video signal

        if abs(recorded_fps - 6) >= 0.01:    
            # If the fps rate was higher/lower than expected, re-encode it to the expected
            print "RE-ENCODING"
            cmd = ''.join(["ffmpeg -r ", str(recorded_fps), " -i ", 
                self.temp_video_filepath, " -pix_fmt yuv420p -r 6 ", self.temp_video_filepath_2])
            print cmd
            subprocess.call(cmd, shell=True)

            print "MUXING"
            cmd = ''.join(["ffmpeg -ac 2 -channel_layout stereo -i ", self.temp_audio_filepath, 
                " -i ", self.temp_video_filepath_2, " -pix_fmt yuv420p ", self.final_video_filepath])
            print cmd
            subprocess.call(cmd, shell=True)
        else:
            print "Normal recording\nMuxing"
            cmd = ''.join(["ffmpeg -ac 2 -channel_layout stereo -i ", self.temp_audio_filepath, 
                " -i ", self.temp_video_filepath, " -pix_fmt yuv420p ", self.final_video_filepath])
            subprocess.call(cmd, shell=True)


    def get_final_filepath(self):
        return self.final_video_filepath



class CameraWidget(QtWidgets.QWidget):
    newFrame = QtCore.pyqtSignal(QtGui.QImage)

    def __init__(self, cameraDevice, parent=None):
        super(CameraWidget, self).__init__(parent)

        self._frame = None

        self._cameraDevice = cameraDevice
        self._cameraDevice.newFrame.connect(self._onNewFrame)
    

        w, h = self._cameraDevice.frameSize
        self.setMinimumSize(w, h)
        self.setMaximumSize(w, h)



    @QtCore.pyqtSlot(numpy.ndarray)
    def _onNewFrame(self, frame):
        """"Update UI preview with latest frame
        """

        img = QtGui.QImage(frame, frame.shape[1], frame.shape[0], QtGui.QImage.Format_RGB888)
        self._frame = img
        self.update()


    def changeEvent(self, e):
        if e.type() == QtCore.QEvent.EnabledChange:
            if self.isEnabled():
                self._cameraDevice.newFrame.connect(self._onNewFrame)
            else:
                self._cameraDevice.newFrame.disconnect(self._onNewFrame)


    def paintEvent(self, e):

        if self._frame is None:
            return

        painter = QtGui.QPainter(self)
        painter.drawImage(QtCore.QPoint(0, 0), self._frame)





class ControlWindow(QtWidgets.QWidget):
    def __init__(self):
        QtWidgets.QWidget.__init__(self)

        # load styles
        with open('styles.qss', 'r') as f:
            self.setStyleSheet(f.read())

        
        # create camera
        self.cameraDevice = CameraDevice()
        self.cameraWidget = CameraWidget(self.cameraDevice)


        # create layout w/ camera preview
        vertical_layout = QtWidgets.QVBoxLayout(self)
        vertical_layout.addWidget(self.cameraWidget)

        # add prompt selection
        self.promptQuestionLabel = QtWidgets.QLabel("What will you answer today?")
        self.promptQuestionLabel.setObjectName("PromptQuestionLabel")
        self.promptQuestionLabel.setFont(QtGui.QFont('SansSerif', 30))   
        self.promptQuestionLabel.setAlignment(QtCore.Qt.AlignCenter)
        vertical_layout.addWidget(self.promptQuestionLabel)


        # group radio buttons
        self.prompt_group = QtWidgets.QButtonGroup(vertical_layout) 

        # create radio button for each prompt
        for prompt in PROMPTS:
            prompt_radio_button = QtWidgets.QRadioButton(prompt)
            self.prompt_group.addButton(prompt_radio_button)
            vertical_layout.addWidget(prompt_radio_button)

        # make one default selected
        self.prompt_group.buttons()[0].setChecked(True)


        # define buttons
        self.start_button = QtWidgets.QPushButton('Start Recording')
        self.start_button.clicked.connect(self.startRecording)
        
        self.stop_button = QtWidgets.QPushButton('Stop Recording')
        self.stop_button.clicked.connect(self.stopRecording)
        self.stop_button.setDisabled(True)

        self.submit_button = QtWidgets.QPushButton('Upload Video')
        self.submit_button.clicked.connect(self.uploadVideo)
        self.submit_button.setDisabled(True)

   

        buttonhorizontalbox = QtWidgets.QHBoxLayout()
        buttonhorizontalbox.addWidget(self.start_button)
        buttonhorizontalbox.addWidget(self.stop_button)
        buttonhorizontalbox.addWidget(self.submit_button)        
        vertical_layout.addLayout(buttonhorizontalbox)

        # input kerberos
        kerberos_horizontal_layout = QtWidgets.QHBoxLayout()
        self.kerberosLabel = QtWidgets.QLabel("Kerberos")
        self.kerberosLabel.setObjectName("KerberosLabel")
        kerberos_horizontal_layout.addWidget(self.kerberosLabel)
        
        self.kerberos_inputbox = QtWidgets.QLineEdit()
        self.kerberos_inputbox.setPlaceholderText("Your kerberos")
        kerberos_horizontal_layout.addWidget(self.kerberos_inputbox)

        vertical_layout.addLayout(kerberos_horizontal_layout)


        self.uploadStatusLabel = QtWidgets.QLabel("Nothing uploaded yet")
        vertical_layout.addWidget(self.uploadStatusLabel)



        self.setLayout(vertical_layout)
        self.setWindowTitle('Video Booth')
        self.setGeometry(100, 100, 200, 200)
        self.show()

        self.kerberos = ""



    def startRecording(self):

        self.start_button.setText("Recording...")

        # self.kerberos = ""
        self.start_button.setDisabled(True) 
        self.stop_button.setDisabled(False)

        
        # start recording
        self.cameraDevice.start()


    def stopRecording(self):
        self.start_button.setText("Start Recording")
        self.stop_button.setDisabled(True)
        self.submit_button.setDisabled(False)


        # stop recording
        self.cameraDevice.stop()



    def uploadVideo(self):
        """ Uploads recorded video to youtube
        """

        # retrieve selected prompt
        for button in self.prompt_group.buttons():
            if button.isChecked():
                self.selected_prompt = button.text()

        # retrieve kerberos
        self.kerberos = self.kerberos_inputbox.text()
        
        if self.kerberos == "":
            self.kerberosLabel.setStyleSheet('QLabel#KerberosLabel {color: red;}')
            return
            
        
        else:
            processing_thread = threading.Thread(target=self._upload)
            processing_thread.start()

            self.stop_button.setDisabled(True)
            self.submit_button.setDisabled(True)
            self.start_button.setDisabled(False)

            self.uploadStatusLabel.setText("Uploaded video for user " + self.kerberos)
            self.kerberos_inputbox.setText("")
            self.kerberosLabel.setStyleSheet('QLabel#KerberosLabel {color: black;}')


    def _upload(self):
        print 'The function _upload is called'
        final_filepath = self.cameraDevice.get_final_filepath()
        
        title = str(time.time())


        # upload video to youtube
        youtubeId = youtube_upload.upload_video(final_filepath, title)


        # tell Node server that video was uploaded
        payload = {
            'youtubeId': youtubeId,
            'title': title,
            'kerberos': self.kerberos,
            'recordingDate': json.dumps(datetime.datetime.now(), default=json_serial),
            'upvotes': 0
        }
        
        payload = json.dumps(payload)

        url = 'http://localhost:3000/upload'
        headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
        r = requests.post(url, headers=headers, data=payload)


        
def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, datetime.datetime):
        serial = obj.isoformat()
        return serial
    raise TypeError ("Type not serializable")





if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    window = ControlWindow()
    sys.exit(app.exec_())



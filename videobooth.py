
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
    
    def cancel(self):
        self.recording = False
        self.microphone.cancel()


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


        # container widget to control screens
        self.start_frame = QtWidgets.QFrame()
        self.start_frame_layout = QtWidgets.QVBoxLayout(self.start_frame)
        vertical_layout.addWidget(self.start_frame)

        # add prompt selection
        self.promptQuestionLabel = QtWidgets.QLabel("What will you share?")
        self.promptQuestionLabel.setObjectName("PromptQuestionLabel")
        self.promptQuestionLabel.setFont(QtGui.QFont('SansSerif', 30))   
        self.promptQuestionLabel.setAlignment(QtCore.Qt.AlignCenter)
        self.start_frame_layout.addWidget(self.promptQuestionLabel)

        # add question from previous user
        self.prevQuestionLabel = QtWidgets.QLabel("Question from previous user")
        self.prevQuestionLabel.setObjectName("PromptQuestionLabel")
        self.prevQuestionLabel.setFont(QtGui.QFont('SansSerif', 15))   
        self.start_frame_layout.addWidget(self.prevQuestionLabel)

        

        # group radio buttons
        self.prompt_group = QtWidgets.QButtonGroup(vertical_layout) 

        self.prev_question_button = QtWidgets.QRadioButton('How did you grow up?')
        self.prompt_group.addButton(self.prev_question_button)
        self.start_frame_layout.addWidget(self.prev_question_button)

        # add question from previous user
        self.prevQuestionLabel = QtWidgets.QLabel("Other questions")
        self.prevQuestionLabel.setObjectName("PromptQuestionLabel")
        self.prevQuestionLabel.setFont(QtGui.QFont('SansSerif', 15))   
        self.start_frame_layout.addWidget(self.prevQuestionLabel)

        
        # create radio button for each prompt
        for prompt in PROMPTS:
            prompt_radio_button = QtWidgets.QRadioButton(prompt)
            self.prompt_group.addButton(prompt_radio_button)
            self.start_frame_layout.addWidget(prompt_radio_button)
        
        # make one default selected
        self.prompt_group.buttons()[0].setChecked(True)



        # define buttons
        self.start_button = QtWidgets.QPushButton('Start Recording')
        self.start_button.clicked.connect(self.startRecording)

        self.start_frame_layout.addWidget(self.start_button)


        # container widget to control screens
        self.recording_frame = QtWidgets.QFrame()
        self.recording_frame_layout = QtWidgets.QVBoxLayout(self.recording_frame)
        vertical_layout.addWidget(self.recording_frame)


    
        # progress bar
        # self.progress_bar = QtWidgets.QProgressBar(self)   
        # self.progress_bar.setMinimum(1)
        # self.progress_bar.setMaximum(30)     
        # self.progress_bar.setGeometry(30, 40, 200, 25)
        # self.recording_frame_layout.addWidget(self.progress_bar)
        # self._active = False


        # self.instructionLabel = QtWidgets.QLabel("Talk for ~30 seconds")
        # self.recording_frame_layout.addWidget(self.instructionLabel)


        self.stop_button = QtWidgets.QPushButton('Stop Recording')
        self.stop_button.clicked.connect(self.stopRecording)
        # self.stop_button.setDisabled(True)
        self.recording_frame_layout.addWidget(self.stop_button)

        self.recording_frame.hide()



        # container widget to control screens
        self.submit_frame = QtWidgets.QFrame()
        self.submit_frame.hide()
        self.submit_frame_layout = QtWidgets.QVBoxLayout(self.submit_frame)
        vertical_layout.addWidget(self.submit_frame)
        

        # input kerberos
        kerberos_horizontal_layout = QtWidgets.QHBoxLayout()
        self.kerberosLabel = QtWidgets.QLabel("Kerberos")
        self.kerberosLabel.setObjectName("KerberosLabel")
        kerberos_horizontal_layout.addWidget(self.kerberosLabel)
        
        self.kerberos_inputbox = QtWidgets.QLineEdit()
        self.kerberos_inputbox.setPlaceholderText("Your kerberos")
        kerberos_horizontal_layout.addWidget(self.kerberos_inputbox)
        self.submit_frame_layout.addLayout(kerberos_horizontal_layout)

        # ask the next question
        nextquestion_horizontal_layout = QtWidgets.QHBoxLayout()
        self.nextquestionLabel = QtWidgets.QLabel("Next question")
        self.nextquestionLabel.setObjectName("nextquestionLabel")
        nextquestion_horizontal_layout.addWidget(self.nextquestionLabel)
        
        self.nextquestion_inputbox = QtWidgets.QLineEdit()
        self.nextquestion_inputbox.setPlaceholderText("(Who is the spiciest memelord?)")
        nextquestion_horizontal_layout.addWidget(self.nextquestion_inputbox)
        self.submit_frame_layout.addLayout(nextquestion_horizontal_layout)


        # add cancel or submit buttons
        cancel_submit_button_layout = QtWidgets.QHBoxLayout()
        
        # cancel button
        self.cancel_button = QtWidgets.QPushButton('Redo video')
        self.cancel_button.clicked.connect(self.cancel)
        cancel_submit_button_layout.addWidget(self.cancel_button)
        
        # submit button
        self.submit_button = QtWidgets.QPushButton('Upload video')
        self.submit_button.clicked.connect(self.uploadVideo)
        cancel_submit_button_layout.addWidget(self.submit_button)
        # self.submit_button.setDisabled(True)

        self.submit_frame_layout.addLayout(cancel_submit_button_layout)

        # # input MIT affiliation
        # mitAffiliation_horizontal_layout = QtWidgets.QHBoxLayout()
        # self.mitAffiliationLabel = QtWidgets.QLabel("MIT affiliation")
        # self.mitAffiliationLabel.setObjectName("mitAffiliationLabel")
        # mitAffiliation_horizontal_layout.addWidget(self.mitAffiliationLabel)
        
        # self.mitAffiliation_inputbox = QtWidgets.QLineEdit()
        # self.mitAffiliation_inputbox.setPlaceholderText("(grad / undergrad / staff)")
        # mitAffiliation_horizontal_layout.addWidget(self.mitAffiliation_inputbox)
        # vertical_layout.addLayout(mitAffiliation_horizontal_layout)


        # # input MIT course
        # mitCourse_horizontal_layout = QtWidgets.QHBoxLayout()
        # self.mitCourseLabel = QtWidgets.QLabel("MIT Course")
        # self.mitCourseLabel.setObjectName("mitCourseLabel")
        # mitCourse_horizontal_layout.addWidget(self.mitCourseLabel)
        
        # self.mitCourse_inputbox = QtWidgets.QLineEdit()
        # self.mitCourse_inputbox.setPlaceholderText("e.g. 3, 20, CMS, etc.")
        # mitCourse_horizontal_layout.addWidget(self.mitCourse_inputbox)
        # vertical_layout.addLayout(mitCourse_horizontal_layout)


        self.uploadStatusLabel = QtWidgets.QLabel("Nothing uploaded yet")
        vertical_layout.addWidget(self.uploadStatusLabel)


        self.setLayout(vertical_layout)
        self.setWindowTitle('Video Booth')
        self.setGeometry(100, 100, 200, 200)
        self.show()

        self.kerberos = ""



    def startRecording(self):

        # if not self._active:
        #     self._active = True
        #     # self.button.setText('Stop')
        #     if self.progress_bar.value() == self.progress_bar.maximum():
        #         self.progress_bar.reset()
        #     QtCore.QTimer.singleShot(0, self.startLoop)
        # else:
        #     self._active = False
        
        # self.start_button.setText("Recording...")
        self.start_frame.hide()
        self.recording_frame.show()

        # self.kerberos = ""
        # self.start_button.setDisabled(True) 
        # self.stop_button.setDisabled(False)

        
        # start recording
        self.cameraDevice.start()

    def startLoop(self):
        ## make this loop for 30 seconds
        while True:
            time.sleep(0.05)
            value = self.progress_bar.value() + 1
            self.progress_bar.setValue(value)
            QtWidgets.QApplication.processEvents()
            if (not self._active or
                value >= self.progress_bar.maximum()):
                break

        self._active = False

    def cancel(self):
        self.start_frame.show()
        self.recording_frame.hide()
        self.submit_frame.hide()  

        self.cameraDevice.cancel()  


    def stopRecording(self):

        self.recording_frame.hide()
        self.submit_frame.show()

        # stop recording
        self.cameraDevice.stop()



    def uploadVideo(self):
        """ Uploads recorded video to youtube
        """

        # retrieve selected prompt
        for button in self.prompt_group.buttons():
            if button.isChecked():
                self.selected_prompt = button.text()


        # retrieve MIT affiliation
        # self.mitAffiliation = self.mitAffiliation_inputbox.text()

        # retrieve MIT course number
        # self.mitCourse = self.mitCourse_inputbox.text()

        # retrieve kerberos
        self.kerberos = self.kerberos_inputbox.text()

        # retrieve new question
        self.prev_question = self.nextquestion_inputbox.text()
        self.prev_question_button.setText(self.prev_question)



        
        if self.kerberos == "":
            self.kerberosLabel.setStyleSheet('QLabel#KerberosLabel {color: red;}')
            return
        
        
        else:
            processing_thread = threading.Thread(target=self._upload)
            processing_thread.start()

            self.start_frame.show()
            self.recording_frame.hide()
            self.submit_frame.hide()

            self.uploadStatusLabel.setText("Uploaded video for user " + self.kerberos)
            self.kerberos_inputbox.setText("")
            self.kerberosLabel.setStyleSheet('QLabel#KerberosLabel {color: black;}')

            self.nextquestion_inputbox.setText("")

            # self.mitAffiliation_inputbox.setText("")
            # self.mitCourse_inputbox.setText("")


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
            'recordingDate': datetime.datetime.now().strftime('%Y/%m/%d %H:%M'),
            'upvotes': 0,
            'newQuestion': self.prev_question,
            'promptString': self.selected_prompt
            # 'mitAffiliation': self.mitAffiliation,
            # 'mitCourse': self.mitCourse
        }
        
        payload = json.dumps(payload)
        
        url = 'https://mitpeople.herokuapp.com/upload'
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




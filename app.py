from flask import Flask, render_template, request, send_file, session
import cv2
import numpy as np
import os
import threading
import time
import secrets
from mss import mss  # Using mss instead of pyautogui for screen capture

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)  # Secure secret key for sessions

# Create a directory for storing recordings if it doesn't exist
UPLOAD_FOLDER = 'static/recordings'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Global variables
is_recording = False
output_filename = ""
recording_error = None

@app.route('/')
def index():
    # Generate a unique session ID if not exists
    if 'user_id' not in session:
        session['user_id'] = secrets.token_hex(8)
    return render_template('index.html')

@app.route('/start_recording', methods=['POST'])
def start_recording():
    global is_recording, output_filename, recording_error

    if not is_recording:
        # Generate new filename without deleting old recordings
        output_filename = os.path.join(UPLOAD_FOLDER, 
                                     f"recording_{session['user_id']}_{int(time.time())}.mp4")
        is_recording = True
        recording_error = None
        threading.Thread(target=record_screen).start()
        return {"status": "success", "message": "Recording started"}
    else:
        return {"status": "error", "message": "Recording is already in progress"}

@app.route('/stop_recording', methods=['POST'])
def stop_recording():
    global is_recording, recording_error, output_filename

    if is_recording:
        is_recording = False
        time.sleep(1)  # Give time for recording thread to finish
        
        # Wait for the file to be completely written
        max_wait = 10  # Maximum seconds to wait
        while max_wait > 0 and not os.path.exists(output_filename):
            time.sleep(0.5)
            max_wait -= 0.5
            
        if recording_error:
            return {"status": "error", "message": recording_error}
        elif not os.path.exists(output_filename):
            return {"status": "error", "message": "Recording failed to save"}
            
        return {"status": "success", "message": "Recording stopped"}
    else:
        return {"status": "error", "message": "No recording in progress"}

@app.route('/download_recording', methods=['GET'])
def download_recording():
    global output_filename
    
    if os.path.exists(output_filename):
        try:
            # Get the filename without the session ID
            display_filename = "recording.mp4"
            return send_file(output_filename, 
                           as_attachment=True, 
                           download_name=display_filename)
        except Exception as e:
            return {"status": "error", "message": "Error downloading file"}
    else:
        return {"status": "error", "message": "No recording available"}

@app.route('/get_video_path')
def get_video_path():
    global output_filename
    if os.path.exists(output_filename):
        # Return the relative path for the video preview
        relative_path = output_filename.replace('static/', '')
        return {"status": "success", "path": relative_path}
    return {"status": "error", "message": "No recording available"}

@app.route('/get_recordings')
def get_recordings():
    if 'user_id' not in session:
        return {"status": "error", "message": "No session found"}
    
    # Get all recordings from the upload folder
    user_recordings = [f for f in os.listdir(UPLOAD_FOLDER) 
                      if f.startswith(f"recording_{session['user_id']}_")]
    recordings = []
    for file in user_recordings:
        timestamp = file.split('_')[-1].replace('.mp4', '')
        file_path = os.path.join(UPLOAD_FOLDER, file)
        if os.path.exists(file_path):
            recordings.append({
                'filename': file,
                'path': f'recordings/{file}',  # Relative path for frontend
                'date': time.strftime('%Y-%m-%d %H:%M:%S', 
                                    time.localtime(int(timestamp)))
            })
    return {"status": "success", "recordings": recordings}

def record_screen():
    global is_recording, output_filename, recording_error

    try:
        with mss() as sct:
            # Get the screen size from the primary monitor
            monitor = sct.monitors[1]  # Primary monitor
            width = monitor["width"]
            height = monitor["height"]

            # Change codec to 'avc1' for better browser compatibility
            fourcc = cv2.VideoWriter_fourcc(*'avc1')  # Changed from 'mp4v' to 'avc1'
            out = None
            
            try:
                out = cv2.VideoWriter(output_filename, fourcc, 20.0, (width, height))
                
                while is_recording:
                    try:
                        # Capture the screen
                        screen = sct.grab(monitor)
                        # Convert to numpy array
                        frame = np.array(screen)
                        # Convert from BGRA to BGR
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                        # Write the frame
                        out.write(frame)
                        time.sleep(0.05)  # Add small delay to reduce CPU usage
                    except Exception as e:
                        recording_error = f"Error during recording: {str(e)}"
                        break
                
            finally:
                # Ensure proper cleanup
                if out is not None:
                    out.release()
                    # Ensure the file is properly closed
                    cv2.waitKey(1)
                    time.sleep(0.5)  # Give time for the file to be written
                
    except Exception as e:
        recording_error = f"Error setting up recording: {str(e)}"
        is_recording = False

if __name__ == '__main__':
    app.run(debug=True)
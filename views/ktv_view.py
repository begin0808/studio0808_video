import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import sys
import time
import subprocess
import traceback
import numpy as np
from PIL import Image, ImageTk

# Lazy imports for optional modules
try:
    import sounddevice as sd
    import soundfile as sf
    import cv2
except ImportError:
    pass

# Try to import Demucs if available for Denoise
try:
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    import torch
except ImportError:
    pass


def get_readable_temp_name(original_path, suffix):
    base = os.path.splitext(os.path.basename(original_path))[0]
    return f"temp_{base}_{suffix}.wav"

class KTVView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        # Determine FFmpeg path
        if getattr(sys, 'frozen', False):
            # If run as exe
            self.tools_dir = os.path.join(os.path.dirname(sys.executable), "tools")
        else:
            # If run as script
            self.tools_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
            
        self.ffmpeg_exe = os.path.join(self.tools_dir, "ffmpeg.exe")
        if not os.path.exists(self.ffmpeg_exe):
             self.ffmpeg_exe = "ffmpeg"
             
        self.video_path = None
        self.is_recording = False
        self.is_paused = False
        self.stop_event = threading.Event()
        
        self.fs = 44100 
        self.audio_data = None
        self.recording_buffer = None
        self.rw_index = 0
        self.stream = None 
        self.stream_in = None
        self.stream_out = None        
        
        # Audio Devices
        self.input_devices = self.get_input_devices()
        
        # Output Dir
        self.output_dir = os.path.join(os.path.dirname(self.tools_dir), "Outputs", "KTV_Covers")
        if not os.path.exists(self.output_dir): os.makedirs(self.output_dir)
        
        # UI Setup
        self.create_widgets()
        
    def check_gpu(self):
        try:
            from utils.gpu_utils import safe_check_cuda
            cuda_ok, info = safe_check_cuda()
            if cuda_ok:
                self.gpu_label.configure(text=f"GPU: {info} (CUDA)", text_color=("#2E7D32", "#00E676"))
            else:
                self.gpu_label.configure(text=f"GPU: {info} (使用 CPU mode)", text_color="#FF5252")
        except Exception:
            self.gpu_label.configure(text="GPU: 偵測失敗 (使用 CPU mode)", text_color="gray")

    def get_input_devices(self):
        import re
        import sounddevice as sd
        devices = []
        try:
            dev_list = sd.query_devices()
            hostapis = sd.query_hostapis()
            
            # 優先使用 MME (相容性最佳，可搭配任何輸出裝置避免 -9993 錯誤)
            api_priority = {}
            for i, api in enumerate(hostapis):
                name = api['name'].upper()
                if "MME" in name:
                    api_priority[i] = 4  # 最高：相容性最佳
                elif "DIRECTSOUND" in name:
                    api_priority[i] = 3
                elif "WASAPI" in name:
                    api_priority[i] = 2  # WASAPI exclusive 易造成跨裝置衝突
                elif "WDM" in name or "KS" in name:
                    api_priority[i] = 1
                else:
                    api_priority[i] = 0
                    
            best_in = {}
            
            for i, d in enumerate(dev_list):
                if d.get('max_input_channels', 0) > 0:
                    api_idx = d.get('hostapi', -1)
                    priority = api_priority.get(api_idx, -1)
                    if priority < 0: continue
                    
                    raw_name = d['name']
                    base_name = re.sub(r"\s*\(.*\)", "", raw_name).strip()
                    if not base_name: base_name = raw_name
                    
                    if base_name not in best_in or priority > best_in[base_name]['priority']:
                        best_in[base_name] = {'index': i, 'raw_name': raw_name, 'priority': priority}
                        
            # Format: [{i}] {name}
            devices = [f"[{info['index']}] {info['raw_name']}" for info in sorted(best_in.values(), key=lambda x: x['index'])]
                
        except Exception as e:
            print(f"Device query error: {e}")
            devices = ["Default Input"]
            
        if not devices: devices = ["No Input Found"]
        return devices

    def get_default_input_device(self):
        """優先選取名稱含「音效對應表」的裝置，其次才是「麥克風」"""
        mapper_keywords = ["音效對應表", "sound mapper"]
        mic_keywords = ["麥克風", "microphone", "mic"]
        
        for dev in self.input_devices:
            dev_lower = dev.lower()
            for kw in mapper_keywords:
                if kw in dev_lower:
                    return dev
                    
        for dev in self.input_devices:
            dev_lower = dev.lower()
            # 排除 FrontMic / Front Mic
            if "front" in dev_lower:
                continue
            for kw in mic_keywords:
                if kw in dev_lower:
                    return dev
                    
        # 找不到關鍵字，回退第一個
        return self.input_devices[0] if self.input_devices else ""

    def run_denoise(self, audio_data):
        """ Run Demucs to separate vocals from noise (Music Separation as Denoise) """
        try:
            self.status_label.set("🤖 AI 降噪運算中 (Demucs)...")
            self.update_idletasks() # Force UI update
            
            # 1. Prepare Data
            # audio_data is (Samples, Channels), float32
            # Demucs expects (1, Channels, Samples) torch tensor
            
            # Transpose to (Channels, Samples)
            wav_np = audio_data.T
            wav_tensor = torch.tensor(wav_np)
            wav_tensor = wav_tensor.unsqueeze(0) # Add batch dim: (1, C, S)
            
            # 2. Load Model
            # Use basic htdemucs for speed
            model_name = "htdemucs"
            from utils.gpu_utils import safe_check_cuda
            cuda_ok, _ = safe_check_cuda()
            device = "cuda" if cuda_ok else "cpu"
            
            model = get_model(model_name)
            try:
                model.to(device)
            except (RuntimeError, Exception) as e:
                if device == "cuda":
                    print(f"[KTV Denoise] GPU 載入失敗 ({e})，切換至 CPU...")
                    device = "cpu"
                    from utils.gpu_utils import safe_cuda_empty_cache
                    safe_cuda_empty_cache()
                    model = get_model(model_name)
                    model.to("cpu")
                else:
                    raise e
            
            # 3. Apply
            # shifts=0 for speed
            wav_tensor = wav_tensor.to(device)
            ref = wav_tensor.mean(0)
            wav_tensor = (wav_tensor - ref.mean()) / ref.std()
            
            # Actually, standard apply_model handles normalization
            # Let's simple call
            sources = apply_model(model, wav_tensor, device=device, shifts=0, split=True, overlap=0.25)
            
            # sources shape: (Batch, Sources, Channels, Time)
            # Demucs sources: ["drums", "bass", "other", "vocals"]
            # We want "vocals" (index 3 in htdemucs)
            
            vocals_idx = model.sources.index("vocals")
            vocals_out = sources[0, vocals_idx].cpu().numpy() # (Channels, Time)
            
            # Transpose back to (Time, Channels)
            return vocals_out.T
            
        except Exception as e:
            print(f"Denoise Error: {e}")
            messagebox.showerror("AI Denoise Error", str(e))
            return audio_data # Fallback to original

    def save_result(self):
        # 1. Mix Audio
        if self.audio_data is None or self.recording_buffer is None:
            return messagebox.showwarning("提示", "無錄音數據")

        vocal_final = self.recording_buffer.copy()

        # --- AI Denoise Step ---
        if self.denoise_var.get():
            vocal_final = self.run_denoise(vocal_final)
            self.status_label.set("混音中...")

        # Apply Reverb (Simple KTV Echo)
        reverb_val = self.scale_echo.get()
        
        if reverb_val > 0:
            # Delay parameters for KTV Echo
            delay_ms = 180 # 180ms delay
            delay_samples = int(self.fs * (delay_ms / 1000.0))
            decay = reverb_val # Use slider as decay factor
            
            echo_signal = np.zeros_like(vocal_final)
            
            # Tap 1
            if len(echo_signal) > delay_samples:
                echo_signal[delay_samples:] += vocal_final[:-delay_samples] * decay
                
            # Tap 2 (Feedback)
            delay2 = delay_samples * 2
            if len(echo_signal) > delay2:
                echo_signal[delay2:] += vocal_final[:-delay2] * (decay * 0.5)
                
            vocal_final += echo_signal

        mixed = (self.audio_data * self.scale_bg.get()) + (vocal_final * self.scale_mic.get())
        mixed = np.clip(mixed, -1.0, 1.0)
    def create_widgets(self):
        # Font definitions
        font_title = ("Microsoft JhengHei UI", 20, "bold")
        font_label = ("Microsoft JhengHei UI", 15)
        font_small = ("Microsoft JhengHei UI", 12)
        font_btn = ("Microsoft JhengHei UI", 14, "bold")
        
        # Header
        header = ctk.CTkFrame(self, height=50)
        header.pack(fill="x", padx=10, pady=(20, 5)) # Increased top padding
        # Title removed based on feedback
        ctk.CTkLabel(header, text="請務必戴上耳機", text_color="#FF5252", font=("Microsoft JhengHei UI", 16, "bold")).place(relx=0.5, rely=0.5, anchor="center")
        
        # GPU Status
        self.gpu_label = ctk.CTkLabel(header, text="檢查 GPU...", text_color="gray", font=font_label)
        self.gpu_label.pack(side="left", padx=10)
        self.after(100, self.check_gpu)

        # Main Scrollable Area -> Now just a Frame
        self.scroll_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Settings Banner
        settings_frame = ctk.CTkFrame(self.scroll_frame)
        settings_frame.pack(fill="x", pady=5)
        
        ctk.CTkLabel(settings_frame, text="輸入裝置:", font=font_label).pack(side="left", padx=10)
        self.device_var = ctk.StringVar(value=self.get_default_input_device())
        self.combo_mic = ctk.CTkOptionMenu(settings_frame, variable=self.device_var, values=self.input_devices, width=320, font=font_label, dropdown_font=font_label)
        self.combo_mic.pack(side="left", padx=5)
        
        ctk.CTkLabel(settings_frame, text="混響:", font=font_label).pack(side="left", padx=(20, 5))
        self.scale_echo = ctk.CTkSlider(settings_frame, from_=0, to=1, number_of_steps=100, width=225, 
                                        command=lambda v: self.lbl_echo.configure(text=f"{int(float(v)*100)}%"))
        self.scale_echo.set(0.3)
        self.scale_echo.pack(side="left", padx=5)
        self.lbl_echo = ctk.CTkLabel(settings_frame, text="30%", width=40, font=font_label)
        self.lbl_echo.pack(side="left")
        
        # Smart Default: Enable Denoise if GPU is available
        default_denoise = False
        try:
             from utils.gpu_utils import safe_check_cuda
             cuda_ok, _ = safe_check_cuda()
             if cuda_ok:
                 default_denoise = True
        except Exception:
             pass

        self.denoise_var = ctk.BooleanVar(value=default_denoise)
        ctk.CTkCheckBox(settings_frame, text="AI 降噪", variable=self.denoise_var, font=font_label).pack(side="left", padx=20)

        # Controls
        ctrl_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        ctrl_frame.pack(pady=10)
        
        self.btn_load = ctk.CTkButton(ctrl_frame, text="選歌", command=self.load_new_song, fg_color="#0D47A1", width=120, height=40, font=font_btn)
        self.btn_load.pack(side="left", padx=10)
        
        self.btn_record = ctk.CTkButton(ctrl_frame, text="開始錄音", command=self.start_recording, fg_color="#E91E63", hover_color="#C2185B", width=150, height=40, font=font_btn)
        self.btn_record.pack(side="left", padx=10)
        
        self.btn_pause = ctk.CTkButton(ctrl_frame, text="暫停", command=self.toggle_pause, state="disabled", fg_color="#2E7D32", hover_color="#1B5E20", width=120, height=40, font=font_btn)
        self.btn_pause.pack(side="left", padx=10)
        
        # Stop Button (Moved here, between Pause and Stop & Synthesize)
        self.btn_cancel_synth = ctk.CTkButton(
            ctrl_frame, 
            text="中斷", 
            command=self.stop_synthesis_action,
            width=120, 
            height=40, 
            fg_color="#D32F2F", 
            hover_color="#B71C1C", 
            state="disabled",
            font=font_btn
        )
        self.btn_cancel_synth.pack(side="left", padx=10)
        
        self.btn_stop = ctk.CTkButton(ctrl_frame, text="停止並合成", command=self.stop_recording, state="disabled", fg_color="#EF6C00", hover_color="#E65100", width=150, height=40, font=font_btn)
        self.btn_stop.pack(side="left", padx=10)

        # Video Canvas
        # Size Increased: 960x540 (qHD 16:9)
        self.canvas_container = ctk.CTkFrame(self.scroll_frame, fg_color="black")
        self.canvas_container.pack(pady=10)
        self.canvas = tk.Canvas(self.canvas_container, width=960, height=540, bg="black", highlightthickness=0)
        self.canvas.pack(padx=2, pady=2)
        
        # Volume & Pitch Mixers (Single row to save space)
        mix_frame = ctk.CTkFrame(self.scroll_frame)
        mix_frame.pack(fill="x", pady=5)
        
        # Set Slider Width
        sw_vol = 140
        sw_pitch = 100
        
        # Companion (BG)
        ctk.CTkLabel(mix_frame, text="伴奏音量:", font=font_label).grid(row=0, column=0, padx=(10, 2), pady=5)
        self.scale_bg = ctk.CTkSlider(mix_frame, from_=0, to=2, width=sw_vol, command=lambda v: self.lbl_bg.configure(text=f"{v:.1f}"))
        self.scale_bg.set(0.5)
        self.scale_bg.grid(row=0, column=1, padx=2)
        self.lbl_bg = ctk.CTkLabel(mix_frame, text="0.5", width=30, font=font_label)
        self.lbl_bg.grid(row=0, column=2, padx=2)
        
        ctk.CTkLabel(mix_frame, text="伴奏音調:", font=font_label).grid(row=0, column=3, padx=(10, 2), pady=5)
        self.scale_pitch_bg = ctk.CTkSlider(mix_frame, from_=-6, to=6, number_of_steps=12, width=sw_pitch, command=lambda v: self.lbl_pitch_bg.configure(text=f"{int(v)}"))
        self.scale_pitch_bg.set(0)
        self.scale_pitch_bg.grid(row=0, column=4, padx=2)
        self.lbl_pitch_bg = ctk.CTkLabel(mix_frame, text="0", width=25, font=font_label)
        self.lbl_pitch_bg.grid(row=0, column=5, padx=2)

        # Separator (Vertical line or space)
        ctk.CTkLabel(mix_frame, text="|", font=font_label).grid(row=0, column=6, padx=15)

        # Vocals (Mic)
        ctk.CTkLabel(mix_frame, text="人聲音量:", font=font_label).grid(row=0, column=7, padx=2, pady=5)
        self.scale_mic = ctk.CTkSlider(mix_frame, from_=0, to=3, width=sw_vol, command=lambda v: self.lbl_mic.configure(text=f"{v:.1f}"))
        self.scale_mic.set(1.5)
        self.scale_mic.grid(row=0, column=8, padx=2)
        self.lbl_mic = ctk.CTkLabel(mix_frame, text="1.5", width=30, font=font_label)
        self.lbl_mic.grid(row=0, column=9, padx=2)

        ctk.CTkLabel(mix_frame, text="人聲音調:", font=font_label).grid(row=0, column=10, padx=(10, 2), pady=5)
        self.scale_pitch_mic = ctk.CTkSlider(mix_frame, from_=-6, to=6, number_of_steps=12, width=sw_pitch, command=lambda v: self.lbl_pitch_mic.configure(text=f"{int(v)}"))
        self.scale_pitch_mic.set(0)
        self.scale_pitch_mic.grid(row=0, column=11, padx=2)
        self.lbl_pitch_mic = ctk.CTkLabel(mix_frame, text="0", width=25, font=font_label)
        self.lbl_pitch_mic.grid(row=0, column=12, padx=(2, 10))
        
        # Status
        # Status & Progress Frame
        status_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        status_frame.pack(pady=5, fill="x", padx=20)

        # Progress Bar on Top
        self.synth_progress = ctk.CTkProgressBar(status_frame, height=10, progress_color="#ffa000")
        self.synth_progress.set(0)
        self.synth_progress.pack(fill="x", padx=10, pady=(10, 5))
        
        # Labels Below
        # Status Label (Left)
        # Re-using self.status_label (StringVar)
        if not hasattr(self, 'status_label') or isinstance(self.status_label, ctk.CTkLabel):
             self.status_label = ctk.StringVar(value="請載入歌曲...")
             
        # Change color to adapt to light/dark mode
        lbl_status = ctk.CTkLabel(status_frame, textvariable=self.status_label, text_color=("gray10", "white"), font=font_label, anchor="w")
        lbl_status.pack(side="left", padx=10, pady=(0, 5), anchor="n")
        
        # Right Side Container (Vertical: Progress Top, Button Bottom)
        right_status_frame = ctk.CTkFrame(status_frame, fg_color="transparent")
        right_status_frame.pack(side="right", padx=10, pady=0)
        
        # Percentage Label
        self.lbl_progress = ctk.CTkLabel(right_status_frame, text="0%", font=font_label, text_color="#ffa000", anchor="e")
        self.lbl_progress.pack(anchor="e", pady=(0, 5))
        
        # Open Folder Button
        ctk.CTkButton(right_status_frame, text="開啟輸出資料夾", command=self.open_output_folder, 
                      width=150, height=28, font=("Microsoft JhengHei UI", 15), fg_color="#4CAF50", hover_color="#388E3C", text_color="white").pack(anchor="e")



    def on_leave(self):
        """ Cleanup when switching views """
        if self.is_recording:
            self.stop_recording(save=False)
        self.stop_event.set() # Ensure thread stops if stuck
        
    def prepare_audio(self):
        if not self.video_path: return
        self.status_label.set("正在解析音訊...")
        temp_audio = "ktv_temp_audio.wav"
        
        # Extract audio from video
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.run([
                self.ffmpeg_exe, "-y", "-i", self.video_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", temp_audio
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
            
            data, fs = sf.read(temp_audio, dtype='float32')
            self.audio_data = data
            self.fs = fs
            if os.path.exists(temp_audio): os.remove(temp_audio)
            
            self.status_label.set(f"✅ 已載入: {os.path.basename(self.video_path)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load audio: {e}")

    def load_new_song(self):
        # Default to Outputs/Vocals as requested
        app_root = os.path.dirname(self.tools_dir)
        vocals_dir = os.path.join(app_root, "Outputs", "Vocals")
        
        start_dir = vocals_dir if os.path.exists(vocals_dir) else app_root
        
        f = filedialog.askopenfilename(
            initialdir=start_dir,
            filetypes=[("Video", "*.mp4 *.mkv *.avi *.mov")]
        )
        if f:
            if self.is_recording: self.stop_recording(save=False)
            self.video_path = f
            self.canvas.delete("all")
            self.after(100, self.prepare_audio)

    def start_recording(self):
        if not self.video_path: return messagebox.showwarning("提示", "請先選歌")
        if self.is_recording: return
        
        self.is_recording = True
        self.is_paused = False
        self.stop_event.clear()
        self.rw_index = 0
        self.recording_buffer = np.zeros((len(self.audio_data), 2), dtype='float32')
        
        self.btn_record.configure(state="disabled")
        self.btn_pause.configure(state="normal", text="⏸️ 暫停")
        self.btn_stop.configure(state="normal")
        self.combo_mic.configure(state="disabled")
        
        if not self.start_audio_stream():
            self.stop_recording(save=False)
            return
            
        threading.Thread(target=self.video_thread, daemon=True).start()

    def start_audio_stream(self):
        self.stream = None
        self.stream_in = None
        self.stream_out = None
        
        try:
            dev_name = self.device_var.get()
            dev_id = int(dev_name.split(']')[0].strip('[')) if ']' in dev_name else None
            
            # 直接使用 Split stream (分離輸入/輸出)
            # 避免 combined stream 因跨裝置 API 不同 (如 WASAPI vs DirectSound)
            # 導致 PaErrorCode -9993 (Illegal combination of I/O devices) 錯誤
            try:
                dev_info = sd.query_devices(dev_id)
                in_ch = min(2, max(1, dev_info.get('max_input_channels', 1)))
                
                self.stream_in = sd.InputStream(
                    samplerate=self.fs,
                    device=dev_id,
                    channels=in_ch,
                    callback=self.mic_callback,
                    blocksize=2048
                )
                self.stream_out = sd.OutputStream(
                    samplerate=self.fs,
                    device=None,  # 預設輸出
                    channels=2,
                    callback=self.playback_callback,
                    blocksize=2048
                )
                self.stream_in.start()
                self.stream_out.start()
                return True
            except Exception as e:
                messagebox.showerror("Error", f"Audio Stream Error: {e}")
                return False
                
        except Exception as e:
            messagebox.showerror("Error", f"Audio Stream Error: {e}")
            return False

    def mic_callback(self, indata, frames, time, status):
        """Mic input only (for split stream mode)"""
        chunk_len = min(frames, len(self.recording_buffer) - self.rw_index) if self.recording_buffer is not None else 0
        if chunk_len > 0:
            try:
                if indata.shape[1] == 1:
                    self.recording_buffer[self.rw_index:self.rw_index+chunk_len, 0] = indata[:chunk_len, 0]
                    self.recording_buffer[self.rw_index:self.rw_index+chunk_len, 1] = indata[:chunk_len, 0]
                else:
                    self.recording_buffer[self.rw_index:self.rw_index+chunk_len] = indata[:chunk_len]
            except: pass

    def playback_callback(self, outdata, frames, time, status):
        """Audio playback only (for split stream mode)"""
        chunk_len = frames
        if self.audio_data is not None:
            remaining = len(self.audio_data) - self.rw_index
            if remaining <= 0:
                outdata[:] = 0
                return
            if chunk_len > remaining:
                chunk_len = remaining
                outdata[chunk_len:] = 0
            outdata[:chunk_len] = self.audio_data[self.rw_index : self.rw_index + chunk_len]
        else:
            outdata[:] = 0
            return
        self.rw_index += chunk_len

    def audio_callback(self, indata, outdata, frames, time, status):
        # Playback
        chunk_len = frames
        if self.rw_index + chunk_len > len(self.audio_data):
            chunk_len = len(self.audio_data) - self.rw_index
            outdata[chunk_len:] = 0
            
        if chunk_len > 0:
            outdata[:chunk_len] = self.audio_data[self.rw_index : self.rw_index + chunk_len]
            
        # Record
        try:
            # Handle mono mic input to stereo buffer
            if indata.shape[1] == 1:
                self.recording_buffer[self.rw_index : self.rw_index + chunk_len, 0] = indata[:chunk_len, 0]
                self.recording_buffer[self.rw_index : self.rw_index + chunk_len, 1] = indata[:chunk_len, 0]
            else:
                self.recording_buffer[self.rw_index : self.rw_index + chunk_len] = indata[:chunk_len]
        except:
            pass # Buffer overflow protection ignored for brevity
            
        self.rw_index += chunk_len

    def video_thread(self):
        cap = cv2.VideoCapture(self.video_path)
        target_fps = 30
        interval = 1.0 / target_fps
        last_t = 0
        
        while not self.stop_event.is_set() and cap.isOpened() and self.is_recording:
            now = time.time()
            if self.is_paused: 
                time.sleep(0.1)
                continue
                
            if now - last_t < interval:
                time.sleep(0.005)
                continue
            last_t = now
            
            # Sync Logic
            audio_t = self.rw_index / self.fs
            video_t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0
            delta = audio_t - video_t
            
            if abs(delta) > 1.0:
                cap.set(cv2.CAP_PROP_POS_MSEC, audio_t * 1000)
            elif delta > 0.1:
                for _ in range(3): cap.grab()
            elif delta < -0.1:
                time.sleep(0.01)
                continue
                
            ret, frame = cap.read()
            if not ret: 
                time.sleep(0.1)
                continue
                
            try:
                # Resize to Larger Preview: 960x540
                frame = cv2.resize(frame, (960, 540))
                img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                imgtk = ImageTk.PhotoImage(image=img)
                self.after(0, self.update_canvas, imgtk)
            except: pass
            
        cap.release()

    def update_canvas(self, img):
        self.current_img = img # Keep ref
        try:
            self.canvas.create_image(0, 0, anchor="nw", image=img)
        except: pass

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        self.btn_pause.configure(text="▶️ 繼續" if self.is_paused else "⏸️ 暫停")
        for s in [self.stream, self.stream_in, self.stream_out]:
            if s:
                s.stop() if self.is_paused else s.start()

    def stop_recording(self, save=True):
        if not self.is_recording: return
        self.is_recording = False
        self.stop_event.set()
        
        # Stop combined or split stream
        for attr in ['stream', 'stream_in', 'stream_out']:
            s = getattr(self, attr, None)
            if s:
                try: s.stop()
                except: pass
                try: s.close()
                except: pass
                setattr(self, attr, None)
            
        self.btn_record.configure(state="normal")
        self.btn_pause.configure(state="disabled", text="⏸️ 暫停")
        self.btn_stop.configure(state="disabled")
        self.combo_mic.configure(state="normal")
        
        if save and self.recording_buffer is not None:
             self.save_result()

    def update_progress_ui(self, val):
        self.synth_progress.set(val)
        self.lbl_progress.configure(text=f"{int(val*100)}%")

    def stop_synthesis_action(self):
        self.stop_synthesis_flag = True
        self.status_label.set("🛑 正在中斷合成...")
        if hasattr(self, 'current_process') and self.current_process:
            try:
                self.current_process.terminate()
            except:
                pass

    def open_output_folder(self):
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        try:
            os.startfile(self.output_dir)
        except Exception as e:
            messagebox.showerror("Error", f"無法開啟資料夾: {e}")

    def get_unique_path(self, path):
        """If file exists, append _1, _2, etc. to filename."""
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        counter = 1
        while True:
            new_path = f"{base}_{counter}{ext}"
            if not os.path.exists(new_path):
                return new_path
            counter += 1

    def save_result(self):
        # 1. Check Data
        if self.audio_data is None or self.recording_buffer is None:
            return messagebox.showwarning("提示", "無錄音數據")

        # 2. Prepare Vocal with Echo (Keep in Python for simplicity)
        reverb_val = self.scale_echo.get()
        vocal_processed = self.recording_buffer.copy()
        
        if reverb_val > 0:
            delay_samples = int(self.fs * (180 / 1000.0))
            decay = reverb_val
            echo_signal = np.zeros_like(vocal_processed)
            if len(echo_signal) > delay_samples:
                echo_signal[delay_samples:] += vocal_processed[:-delay_samples] * decay
            if len(echo_signal) > delay_samples * 2:
                echo_signal[delay_samples*2:] += vocal_processed[:-delay_samples*2] * (decay * 0.5)
            vocal_processed += echo_signal
            vocal_processed = np.clip(vocal_processed, -1.0, 1.0)

        # 3. Generate Default Filename
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        song_base = os.path.splitext(os.path.basename(self.video_path))[0]
        default_path = os.path.join(self.output_dir, f"Cover_{song_base}_{timestamp}.mp4")
        default_path = self.get_unique_path(default_path)
        
        save_path = filedialog.asksaveasfilename(
            initialfile=os.path.basename(default_path),
            defaultextension=".mp4", 
            filetypes=[("MP4 Video", "*.mp4"), ("WMV Video", "*.wmv"), ("MOV Video", "*.mov"), ("MP3 Audio", "*.mp3"), ("WAV Audio", "*.wav")]
        )
        
        if not save_path: return

        # 4. Prepare Synthesis parameters
        bg_vol = self.scale_bg.get()
        mic_vol = self.scale_mic.get()
        bg_pitch = int(self.scale_pitch_bg.get())
        mic_pitch = int(self.scale_pitch_mic.get())

        self.status_label.set("正在準備合成數據...")
        self.synth_progress.set(0)
        self.btn_cancel_synth.configure(state="normal")
        self.stop_synthesis_flag = False

        # Start Thread
        threading.Thread(target=self.run_synthesis_advanced, args=(self.audio_data, vocal_processed, save_path, bg_vol, mic_vol, bg_pitch, mic_pitch)).start()

    def run_synthesis_advanced(self, bg_data, vocal_data, output_path, bg_vol, mic_vol, bg_pitch, mic_pitch):
        import re
        temp_bg = f"temp_bg_{int(time.time())}.wav"
        temp_vocal = f"temp_vocal_{int(time.time())}.wav"
        
        # Save temp files for FFmpeg to process
        sf.write(temp_bg, bg_data, self.fs)
        sf.write(temp_vocal, vocal_data, self.fs)
        
        try:
            ext = os.path.splitext(output_path)[1].lower()
            is_audio_only = ext in [".mp3", ".wav"]
            
            # Pitch factors: K = 2^(n/12)
            k_bg = 2**(bg_pitch/12.0)
            k_mic = 2**(mic_pitch/12.0)
            
            # Build Filter String
            # [0:a] is BG, [1:a] is Vocal
            # asetrate=44100*K, atempo=1/K
            filter_parts = []
            
            # BG Chain
            if bg_pitch != 0:
                filter_parts.append(f"[0:a]asetrate={self.fs}*{k_bg:.6f},atempo={1/k_bg:.6f},volume={bg_vol:.4f}[bg]")
            else:
                filter_parts.append(f"[0:a]volume={bg_vol:.4f}[bg]")
                
            # Vocal Chain
            if mic_pitch != 0:
                filter_parts.append(f"[1:a]asetrate={self.fs}*{k_mic:.6f},atempo={1/k_mic:.6f},volume={mic_vol:.4f}[vocal]")
            else:
                filter_parts.append(f"[1:a]volume={mic_vol:.4f}[vocal]")
                
            # Mix Chain
            filter_parts.append("[bg][vocal]amix=inputs=2:duration=longest:dropout_transition=0[out]")
            filter_str = ";".join(filter_parts)
            
            cmd = [self.ffmpeg_exe, "-y", "-i", temp_bg, "-i", temp_vocal]
            
            if not is_audio_only:
                # Add video input for muxing
                cmd.extend(["-i", self.video_path])
                # Map inputs: temp_bg is [0:a], temp_vocal is [1:a], video is [2:v]
                cmd.extend(["-filter_complex", filter_str, "-map", "2:v:0", "-map", "[out]"])
            else:
                cmd.extend(["-filter_complex", filter_str, "-map", "[out]"])

            # Setup Encoding
            if ext == ".mp3": cmd.extend(["-c:a", "libmp3lame", "-q:a", "2"])
            elif ext == ".wav": cmd.extend(["-c:a", "pcm_s16le"])
            elif ext == ".mp4": cmd.extend(["-c:v", "libx264", "-c:a", "aac", "-shortest"])
            elif ext == ".mov": cmd.extend(["-c:v", "libx264", "-c:a", "aac", "-f", "mov", "-shortest"])
            elif ext == ".wmv": cmd.extend(["-c:v", "wmav2", "-c:a", "wmav2", "-shortest"])
            
            cmd.append(output_path)
            
            # Debug Print Command
            print(f"\n[KTV Synthesis] FFmpeg Command:\n{' '.join(cmd)}\n")
            
            # Run Process
            duration = len(bg_data) / self.fs
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            self.status_label.set("🛠️ 正在進行音訊升降調與合成...")
            self.current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, encoding='utf-8', startupinfo=startupinfo)
            
            for line in self.current_process.stdout:
                # Print output to console for debugging
                if "Error" in line or "error" in line: print(f"[FFmpeg ERROR] {line.strip()}")
                
                if self.stop_synthesis_flag: break
                if "time=" in line:
                    match = re.search(r"time=(\d{2}:\d{2}:\d{2}\.\d+)", line)
                    if match and duration > 0:
                        h, m, s = map(float, match.group(1).split(':'))
                        curr_sec = h*3600 + m*60 + s
                        self.after(0, lambda p=min(1.0, curr_sec/duration): self.update_progress_ui(p))
            
            self.current_process.wait()

            if self.stop_synthesis_flag:
                self.after(0, lambda: self.status_label.set("🛑 合成已取消"))
                if os.path.exists(output_path): 
                    try: os.remove(output_path)
                    except: pass
            elif self.current_process.returncode == 0:
                self.after(0, lambda: self.status_label.set("✅ 合成完成"))
                self.after(0, lambda: self.update_progress_ui(1.0))
                messagebox.showinfo("成功", f"檔案已儲存至:\n{output_path}")
                try: os.startfile(os.path.dirname(output_path))
                except: pass
            else:
                self.after(0, lambda: self.status_label.set("❌ 合成失敗"))
                messagebox.showerror("失敗", "FFmpeg 合成錯誤，請檢查檔案格式")

        except Exception as e:
            traceback.print_exc()
            self.after(0, lambda: self.status_label.set("❌ 錯誤發生"))
            messagebox.showerror("Error", str(e))
        finally:
            self.current_process = None
            self.after(0, lambda: self.btn_cancel_synth.configure(state="disabled"))
            for f in [temp_bg, temp_vocal]:
                if os.path.exists(f): 
                    try: os.remove(f)
                    except: pass

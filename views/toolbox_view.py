import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import sys
import subprocess
import time
import cv2
import json
from PIL import Image, ImageTk
import sounddevice as sd
import soundfile as sf
import numpy as np

class ToolboxView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        # Video Capture Object
        self.cap = None
        self.total_frames = 0
        self.fps = 30
        self.current_frame_idx = 0
        self.is_playing = False
        self.play_job = None
        self.current_video_path = None # Track current file
        
        # FFmpeg Process Tracking
        self.current_process = None
        self.current_output_path = None
        
        # Audio Objects
        self.audio_data = None
        self.samplerate = 44100
        self.audio_ready = False
        self.play_start_time = 0
        self.video_start_sec = 0
        
        # Paths
        self.script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.output_dir = os.path.join(self.script_dir, "Outputs", "Tools")
        self.tools_dir = os.path.join(self.script_dir, "tools")
        self.temp_dir = os.path.join(self.script_dir, "temp")
        
        if not os.path.exists(self.output_dir): os.makedirs(self.output_dir)
        if not os.path.exists(self.temp_dir): os.makedirs(self.temp_dir)
            
        self.ffmpeg_exe = os.path.join(self.tools_dir, "ffmpeg.exe")
        if not os.path.exists(self.ffmpeg_exe): self.ffmpeg_exe = "ffmpeg"
        
        self.ffprobe_exe = os.path.join(self.tools_dir, "ffprobe.exe")
        if not os.path.exists(self.ffprobe_exe): self.ffprobe_exe = "ffprobe"
        
        # Clear temp on startup
        self.cleanup_temp_files()

        # Fonts
        self.font_header = ("Microsoft JhengHei UI", 24, "bold")
        self.font_tab = ("Microsoft JhengHei UI", 16, "bold")
        self.font_ui = ("Microsoft JhengHei UI", 15)
        self.font_small = ("Microsoft JhengHei UI", 12)

        # UI Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1) # Main content expands
        
        self.create_tabs()
        
        # Spacer at the bottom to push everything up
        self.spacer = ctk.CTkFrame(self, fg_color="transparent")
        self.spacer.grid(row=10, column=0, sticky="nsew")
        self.grid_rowconfigure(10, weight=1)
        self.grid_rowconfigure(1, weight=0) # Make main content NOT push components to the bottom
        
        # Status Card (Container for Status and Progress)
        self.status_card = ctk.CTkFrame(self, fg_color="#181A1F", corner_radius=8)
        self.status_card.grid(row=2, column=0, sticky="ew", padx=20, pady=(5, 5))
        self.status_card.grid_columnconfigure(0, weight=1)
        
        self.status_labels = {}
        self.percent_labels = {}
        self.progress_bars = {}
        
        for k in ["convert", "audio", "trim", "merge", "compress", "cut_silence"]:
            sl = ctk.CTkLabel(self.status_card, text="系統狀態： 就緒", anchor="w", text_color="#00E676", font=("Microsoft JhengHei UI", 15, "bold"))
            pl = ctk.CTkLabel(self.status_card, text="0%", font=("Microsoft JhengHei UI", 14, "bold"), text_color="#F57C00")
            pb = ctk.CTkProgressBar(self.status_card, height=12, progress_color="#F57C00")
            pb.set(0)
            
            self.status_labels[k] = sl
            self.percent_labels[k] = pl
            self.progress_bars[k] = pb
        
        # Initial Tab
        self.switch_tab("record")

    def create_tabs(self):
        # Custom Tab Bar
        self.tab_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.tab_bar.grid(row=0, column=0, sticky="w", padx=20, pady=(20, 10))
        
        # Define Tabs
        self.tabs = {
            "record":  {"text": "錄音助手", "color": "#43A047", "frame": None}, # Green
            "convert": {"text": "格式轉換", "color": "#1E88E5", "frame": None},
            "audio":   {"text": "音訊提取", "color": "#F57C00", "frame": None},
            "trim":    {"text": "簡易剪輯", "color": "#D32F2F", "frame": None},
            "merge":   {"text": "影音合併", "color": "#7B1FA2", "frame": None},
            "compress": {"text": "影片壓縮", "color": "#009688", "frame": None},
            "cut_silence": {"text": "裁剪靜音", "color": "#E64A19", "frame": None}
        }
        
        self.tab_buttons = {}
        
        for key, data in self.tabs.items():
            btn = ctk.CTkButton(self.tab_bar, text=data["text"], font=self.font_tab,
                                fg_color="transparent", border_width=2, border_color=data["color"], text_color=data["color"],
                                hover_color=data["color"],
                                width=120, height=40,
                                command=lambda k=key: self.switch_tab(k))
            btn.pack(side="left", padx=(0, 15)) # Spacing
            self.tab_buttons[key] = btn
            
        # Content Area
        self.content_area = ctk.CTkFrame(self, fg_color="transparent")
        self.content_area.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        # Content area row/col weights for resizing
        self.content_area.grid_columnconfigure(0, weight=1)
        self.content_area.grid_rowconfigure(0, weight=1)

    def switch_tab(self, key):
        # Release Video Capture if leaving Trim tab
        if hasattr(self, "current_tab_key") and self.current_tab_key == "trim" and key != "trim":
            self.release_video()
        
        self.current_tab_key = key
        
        # 1. Update Buttons
        for k, btn in self.tab_buttons.items():
            if k == key:
                btn.configure(fg_color=self.tabs[k]["color"], text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color=self.tabs[k]["color"])
                
        # 2. Show Content
        for k, data in self.tabs.items():
            if data["frame"]: data["frame"].pack_forget()
            
        if not self.tabs[key]["frame"]:
            self.create_tab_content(key)
            
        self.tabs[key]["frame"].pack(fill="both", expand=True)

        # 3. Handle Global Progress Bar Visibility
        if hasattr(self, 'status_card'):
            if key == "record":
                self.status_card.grid_remove()
            else:
                self.status_card.grid()
                for k in self.status_labels:
                    self.status_labels[k].grid_remove()
                    self.percent_labels[k].grid_remove()
                    self.progress_bars[k].grid_remove()
                
                self.status_labels[key].grid(row=0, column=0, sticky="w", padx=15, pady=(5, 5))
                
                if key in ["audio", "trim", "merge"]:
                    # Fast operations: Hide progress bar, only show status label
                    pass 
                else:
                    self.percent_labels[key].grid(row=0, column=1, sticky="e", padx=15, pady=(8, 8))
                    self.progress_bars[key].grid(row=1, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 15))

    def create_tab_content(self, key):
        frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.tabs[key]["frame"] = frame
        
        if key == "record":
            self.setup_record_tab(frame)
        elif key == "convert":
            self.setup_convert_tab(frame)
        elif key == "audio":
            self.setup_audio_tab(frame)
        elif key == "trim":
            self.setup_trim_tab(frame)
        elif key == "merge":
            self.setup_merge_tab(frame)
        elif key == "compress":
            self.setup_compress_tab(frame)
        elif key == "cut_silence":
            self.setup_cut_silence_tab(frame)

    def cleanup_temp_files(self):
        try:
            for f in os.listdir(self.temp_dir):
                path = os.path.join(self.temp_dir, f)
                try:
                    if os.path.isfile(path):
                        os.remove(path)
                except Exception as e:
                    print(f"Cleanup Error: {e}")
        except Exception as e:
            print(f"Cleanup Error: {e}")
            
    def release_video(self):
        self.stop_play()
        # cleanup_temp_files NOT called here to allow persistence for fast reload
        # Clean up audio
        self.audio_data = None
        self.audio_ready = False
        
        if self.cap:
            self.cap.release()
            self.cap = None

    def clear_preview(self):
        """Releases media resources and resets the preview label to black."""
        self.release_video()
        if hasattr(self, 'preview_label'):
            self.preview_label.configure(image="", text="處理完成\n\n請重新加入檔案", font=("Microsoft JhengHei UI", 24))
            self.preview_label.image = None
        if hasattr(self, 'time_label'):
            self.time_label.configure(text="00:00:00.00 / 00:00:00.00")
        if hasattr(self, 'timeline_slider'):
            self.timeline_slider.set(0)
            self.timeline_slider.configure(state="disabled")
        self.current_video_path = None # Reset path to force reload if selected again
        self.set_controls_state("disabled")

    def show_success_and_cleanup(self, title, msg):
        """Shows info box and then clears the preview if in trim mode."""
        messagebox.showinfo(title, msg)
        if getattr(self, "current_tab_key", "") == "trim":
            self.clear_preview()

    def log(self, msg, tab_key=None):
        k = tab_key if tab_key else getattr(self, "current_tab_key", None)
        if k in getattr(self, "status_labels", {}):
            self.status_labels[k].configure(text=f"系統狀態： {msg}")
            self.update_idletasks()
        
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

    def update_progress(self, val, text, tab_key=None):
        k = tab_key if tab_key else getattr(self, "current_tab_key", None)
        if k in getattr(self, "progress_bars", {}):
            self.progress_bars[k].set(val)
            self.percent_labels[k].configure(text=text)

    def clear_inputs(self, tab_key):
        if tab_key == "convert" and hasattr(self, 'conv_file_box'):
            self.conv_file_var.set("")
            self.conv_file_box.configure(state="normal")
            self.conv_file_box.delete("1.0", "end")
            self.conv_file_box.insert("1.0", "請點選下方「加入檔案」選擇單一或多個來源檔案 (支援按住 Ctrl/Shift 批次多選)...")
            self.conv_file_box.configure(state="disabled")
        elif tab_key == "audio" and hasattr(self, 'audio_file_box'):
            self.audio_file_var.set("")
            self.audio_file_box.configure(state="normal")
            self.audio_file_box.delete("1.0", "end")
            self.audio_file_box.insert("1.0", "請點選下方「加入影片檔案」選擇單一或多個來源影片 (支援按住 Ctrl/Shift 批次多選)...")
            self.audio_file_box.configure(state="disabled")
        elif tab_key == "compress" and hasattr(self, 'compress_file_box'):
            self.compress_file_var.set("")
            self.compress_file_box.configure(state="normal")
            self.compress_file_box.delete("1.0", "end")
            self.compress_file_box.insert("1.0", "請點選下方「加入影片檔案」選擇單一或多個影片 (支援按住 Ctrl/Shift 批次多選)...")
            self.compress_file_box.configure(state="disabled")
        elif tab_key == "trim" and hasattr(self, 'trim_file_var'):
            self.trim_file_var.set("")
        elif tab_key == "merge" and hasattr(self, 'merge_v_var'):
            self.merge_v_var.set("")
            self.merge_a_var.set("")
        elif tab_key == "cut_silence" and hasattr(self, 'sil_file_var'):
            self.sil_file_var.set("")


    def run_ffmpeg_batch(self, tasks, success_msg, callback=None):
        task_tab_key = getattr(self, "current_tab_key", None)
        self.clear_inputs(task_tab_key)
        def _thread():
            try:
                import time
                start_time = time.time()
                self.after(0, lambda: self.log(f"⏳ 批次處理開始，共 {len(tasks)} 個檔案...", tab_key=task_tab_key))
                self.after(0, lambda: self.update_progress(0, "處理中...", tab_key=task_tab_key))
                
                startupinfo = subprocess.STARTUPINFO()
                if os.name == 'nt':
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                if hasattr(self, 'btn_run_compress'): self.after(0, lambda: self.btn_run_compress.configure(state="disabled"))
                if hasattr(self, 'btn_run_silence'): self.after(0, lambda: self.btn_run_silence.configure(state="disabled"))
                if hasattr(self, 'btn_run_convert'): self.after(0, lambda: self.btn_run_convert.configure(state="disabled"))
                if hasattr(self, 'btn_stop_compress'): self.after(0, lambda: self.btn_stop_compress.configure(state="normal"))
                if hasattr(self, 'btn_stop_silence'): self.after(0, lambda: self.btn_stop_silence.configure(state="normal"))
                if hasattr(self, 'btn_stop_convert'): self.after(0, lambda: self.btn_stop_convert.configure(state="normal"))

                import re
                
                for idx, task in enumerate(tasks):
                    cmd = task['cmd']
                    duration = task.get('duration', 0)
                    
                    self.after(0, lambda i=idx+1, total=len(tasks): self.log(f"▶ 正在處理第 {i}/{total} 個檔案...", tab_key=task_tab_key))
                    print(f"[DEBUG] Running Batch {idx+1}: {cmd}")
                    
                    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                               universal_newlines=True, encoding='utf-8', errors='replace', startupinfo=startupinfo)
                    self.current_process = p
                    out_path = task.get('out_path')
                    self.current_output_path = out_path
                    
                    parsed_duration = duration
                    for line in p.stdout:
                        line = line.strip()
                        if not line: continue
                        
                        if parsed_duration <= 0 and "Duration:" in line:
                             match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2})\.(\d{2})", line)
                             if match:
                                 h, m, s, ms = map(int, match.groups())
                                 parsed_duration = h * 3600 + m * 60 + s + ms / 100.0
                        
                        if "time=" in line and parsed_duration > 0:
                             match = re.search(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})", line)
                             if match:
                                 h, m, s, ms = map(int, match.groups())
                                 current_time = h * 3600 + m * 60 + s + ms / 100.0
                                 percent = min(current_time / parsed_duration, 0.99)
                                 
                                 # Calculate overall progress roughly
                                 overall_percent = (idx + percent) / len(tasks)
                                 
                                 import time
                                 elapsed = int(time.time() - start_time)
                                 m, s = divmod(elapsed, 60)
                                 timer_str = f"{m:02d}:{s:02d}"
                                 
                                 self.after(0, lambda v=overall_percent, i=idx+1, total=len(tasks), ts=timer_str: self.update_progress(v, f"處理中 ({i}/{total}) {int(v*100)}% ({ts})", tab_key=task_tab_key))

                    if self.current_process:
                        p.wait()
                    
                    # Check cancellation
                    if self.current_process is None or p.returncode != 0:
                        cancelled = (self.current_process is None)
                        if cancelled:
                            self.after(0, lambda: self.update_progress(0, "⚠️ 批次處理已中斷", tab_key=task_tab_key))
                            # Cleanup corrupted file on manual cancel
                            if out_path and os.path.exists(out_path):
                                try:
                                    import time
                                    time.sleep(0.1)
                                    os.remove(out_path)
                                    self.log(f"🧹 已清理未完成檔案: {os.path.basename(out_path)}")
                                except: pass
                        else:
                            self.after(0, lambda: self.update_progress(0, "⚠️ 批次處理出錯", tab_key=task_tab_key))
                            self.log("⚠️ 批次處理出錯", tab_key=task_tab_key)
                        
                        self.current_process = None
                        self.current_output_path = None
                        return
                    
                    self.current_output_path = None

                import time
                elapsed = int(time.time() - start_time)
                m, s = divmod(elapsed, 60)
                timer_str = f"{m:02d}:{s:02d}"
                final_msg = f"{success_msg} (總耗時 {timer_str})"
                
                self.after(0, lambda: self.update_progress(1.0, final_msg, tab_key=task_tab_key))
                self.after(0, lambda m=final_msg: self.log(m, tab_key=task_tab_key))
                self.after(0, lambda msg=final_msg: self.show_success_and_cleanup("成功", msg))
                self.after(0, lambda: os.startfile(self.output_dir))
                
                if callback:
                    self.after(0, callback)
                    
            except Exception as e:
                self.log(f"FFmpeg Error: {e}", tab_key=task_tab_key)
                self.after(0, lambda: self.update_progress(0, "錯誤", tab_key=task_tab_key))
            finally:
                self.current_process = None
                if hasattr(self, 'btn_run_compress'): self.after(0, lambda: self.btn_run_compress.configure(state="normal"))
                if hasattr(self, 'btn_run_silence'): self.after(0, lambda: self.btn_run_silence.configure(state="normal"))
                if hasattr(self, 'btn_run_convert'): self.after(0, lambda: self.btn_run_convert.configure(state="normal"))
                if hasattr(self, 'btn_stop_compress'): self.after(0, lambda: self.btn_stop_compress.configure(state="disabled"))
                if hasattr(self, 'btn_stop_silence'): self.after(0, lambda: self.btn_stop_silence.configure(state="disabled"))
                if hasattr(self, 'btn_stop_convert'): self.after(0, lambda: self.btn_stop_convert.configure(state="disabled"))

        threading.Thread(target=_thread, daemon=True).start()

    def cancel_ffmpeg(self):
        if self.current_process:
            self.log("⚠️ 正在中斷處理...")
            out_to_clean = self.current_output_path
            try:
                if os.name == 'nt':
                    self.current_process.kill()
                else:
                    self.current_process.terminate()
            except Exception as e:
                print(f"Kill error: {e}")
            self.current_process = None
            
            # Cleanup interrupted file
            if out_to_clean and os.path.exists(out_to_clean):
                try:
                    time.sleep(0.1) # Wait a bit for file handle release
                    os.remove(out_to_clean)
                    self.log(f"🧹 已清理未完成檔案: {os.path.basename(out_to_clean)}")
                except Exception as e:
                    print(f"Cleanup error: {e}")
            self.current_output_path = None

    def run_ffmpeg(self, cmd, success_msg, callback=None, duration=0, out_path=None):
        task_tab_key = getattr(self, "current_tab_key", None)
        self.clear_inputs(task_tab_key)
        def _thread():
            try:
                import time
                start_time = time.time()
                self.after(0, lambda: self.log("⏳ 處理中...", tab_key=task_tab_key))
                self.after(0, lambda: self.update_progress(0, "處理中...", tab_key=task_tab_key))
                
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                print(f"[DEBUG] Running: {cmd}")
                
                if hasattr(self, 'btn_run_compress'): self.after(0, lambda: self.btn_run_compress.configure(state="disabled"))
                if hasattr(self, 'btn_run_silence'): self.after(0, lambda: self.btn_run_silence.configure(state="disabled"))
                if hasattr(self, 'btn_run_convert'): self.after(0, lambda: self.btn_run_convert.configure(state="disabled"))
                if hasattr(self, 'btn_stop_compress'): self.after(0, lambda: self.btn_stop_compress.configure(state="normal"))
                if hasattr(self, 'btn_stop_silence'): self.after(0, lambda: self.btn_stop_silence.configure(state="normal"))
                if hasattr(self, 'btn_stop_convert'): self.after(0, lambda: self.btn_stop_convert.configure(state="normal"))

                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                           universal_newlines=True, encoding='utf-8', errors='replace', startupinfo=startupinfo)
                self.current_process = p
                self.current_output_path = out_path
                
                import re
                parsed_duration = duration
                
                for line in p.stdout:
                    line = line.strip()
                    if not line: continue
                    # print(line) # Debug
                    
                    if parsed_duration <= 0 and "Duration:" in line:
                         match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2})\.(\d{2})", line)
                         if match:
                             h, m, s, ms = map(int, match.groups())
                             parsed_duration = h * 3600 + m * 60 + s + ms / 100.0
                    
                    if "time=" in line and parsed_duration > 0:
                         match = re.search(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})", line)
                         if match:
                             h, m, s, ms = map(int, match.groups())
                             current_time = h * 3600 + m * 60 + s + ms / 100.0
                             percent = min(current_time / parsed_duration, 0.99)
                             
                             import time
                             elapsed = int(time.time() - start_time)
                             mins, secs = divmod(elapsed, 60)
                             timer_str = f"{mins:02d}:{secs:02d}"
                             self.after(0, lambda v=percent, ts=timer_str: self.update_progress(v, f"處理中 {int(v*100)}% ({ts})", tab_key=task_tab_key))

                if self.current_process:
                    p.wait()
                
                # Check cancellation
                if self.current_process is None or p.returncode != 0:
                    cancelled = (self.current_process is None)
                    if cancelled:
                        self.after(0, lambda: self.update_progress(0, "⚠️ 處理已中斷", tab_key=task_tab_key))
                        # Cleanup corrupted file on manual cancel
                        if out_path and os.path.exists(out_path):
                            try:
                                time.sleep(0.1)
                                os.remove(out_path)
                                self.log(f"🧹 已清理未完成檔案: {os.path.basename(out_path)}")
                            except: pass
                    else:
                        self.after(0, lambda: self.update_progress(0, "❌ 處理失敗", tab_key=task_tab_key))
                    self.current_process = None
                    self.current_output_path = None
                    return
                
                self.current_output_path = None

                import time
                elapsed = int(time.time() - start_time)
                mins, secs = divmod(elapsed, 60)
                timer_str = f"{mins:02d}:{secs:02d}"
                final_msg = f"{success_msg} (耗時 {timer_str})"
                
                self.after(0, lambda: self.update_progress(1.0, final_msg, tab_key=task_tab_key))
                self.after(0, lambda m=final_msg: self.log(m, tab_key=task_tab_key))
                self.after(0, lambda msg=final_msg: self.show_success_and_cleanup("成功", msg))
                self.after(0, lambda: os.startfile(self.output_dir))
                
                if callback:
                    self.after(0, callback)
                    
            except Exception as e:
                self.log(f"FFmpeg Error: {e}", tab_key=task_tab_key)
                self.after(0, lambda: self.update_progress(0, "錯誤", tab_key=task_tab_key))
            finally:
                self.current_process = None
                if hasattr(self, 'btn_run_compress'): self.after(0, lambda: self.btn_run_compress.configure(state="normal"))
                if hasattr(self, 'btn_run_silence'): self.after(0, lambda: self.btn_run_silence.configure(state="normal"))
                if hasattr(self, 'btn_run_convert'): self.after(0, lambda: self.btn_run_convert.configure(state="normal"))
                if hasattr(self, 'btn_stop_compress'): self.after(0, lambda: self.btn_stop_compress.configure(state="disabled"))
                if hasattr(self, 'btn_stop_silence'): self.after(0, lambda: self.btn_stop_silence.configure(state="disabled"))
                if hasattr(self, 'btn_stop_convert'): self.after(0, lambda: self.btn_stop_convert.configure(state="disabled"))

        threading.Thread(target=_thread, daemon=True).start()

    # --- 1. Converter ---
    def setup_convert_tab(self, parent):
        ctk.CTkLabel(parent, text="將影片轉換為不同格式 (智慧無損/轉碼)", font=("Microsoft JhengHei UI", 18, "bold"), text_color="#1E88E5").pack(anchor="w", pady=(10, 10))
        
        self.conv_file_var = ctk.StringVar()
        self.conv_file_box = ctk.CTkTextbox(parent, height=120, font=self.font_ui)
        self.conv_file_box.insert("1.0", "請點選下方「加入檔案」選擇單一或多個來源檔案 (支援按住 Ctrl/Shift 批次多選)...")
        self.conv_file_box.configure(state="disabled")
        self.conv_file_box.pack(anchor="w", fill="x", padx=(0, 20), pady=5)
        btn_box_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_box_frame.pack(anchor="w", pady=5)
        ctk.CTkButton(btn_box_frame, text="加入檔案", command=lambda: self.browse_multiple(self.conv_file_var, self.conv_file_box), font=self.font_ui, fg_color="#3949AB").pack(side="left", padx=(0, 10))
        ctk.CTkButton(btn_box_frame, text="清空列表", command=lambda: self.clear_inputs("convert"), font=self.font_ui, fg_color="#757575", hover_color="#616161", width=100).pack(side="left")
        
        ctk.CTkLabel(parent, text="目標格式:", font=self.font_ui).pack(anchor="w", pady=(20, 5))
        self.fmt_var = ctk.StringVar(value="MP4 (影片)")
        formats = ["MP4 (影片)", "MKV (影片)", "MOV (影片)", "AVI (影片)", "WMV (影片)", "WEBM (影片)", "FLV (影片)", "MPEG (影片)", "TS (影片)", "MP3 (音訊)", "WAV (音訊)", "FLAC (音訊)", "M4A (音訊)", "AAC (音訊)", "OGG (音訊)", "WMA (音訊)"]
        ctk.CTkComboBox(parent, variable=self.fmt_var, values=formats, font=self.font_ui, dropdown_font=self.font_ui, width=200).pack(anchor="w", pady=5)
        
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(anchor="w", pady=30)
        self.btn_run_convert = ctk.CTkButton(btn_frame, text="開始轉換", command=self.run_convert, fg_color="#E91E63", hover_color="#C2185B", font=self.font_tab, width=150)
        self.btn_run_convert.pack(side="left", padx=(0, 10))
        
        self.btn_stop_convert = ctk.CTkButton(btn_frame, text="中斷", command=self.cancel_ffmpeg, fg_color="#D32F2F", hover_color="#B71C1C", font=self.font_tab, width=100, state="disabled")
        self.btn_stop_convert.pack(side="left", padx=(0, 10))
        
        ctk.CTkButton(btn_frame, text="開啟輸出資料夾", command=lambda: os.startfile(self.output_dir), font=self.font_tab, width=150, fg_color="#4CAF50", hover_color="#388E3C", text_color="white").pack(side="left", padx=10)

        # Recommendation Tip
        tip_frame = ctk.CTkFrame(parent, fg_color="#263238", corner_radius=6)
        tip_frame.pack(anchor="w", fill="x", padx=(0, 20), pady=(10, 0))
        ctk.CTkLabel(tip_frame, text="💡 建議：若要在 Windows 內建播放器觀看，請優先選擇 MP4 (影片) 格式，相容性最佳。", 
                     font=self.font_small, text_color="#FFD54F", justify="left").pack(padx=10, pady=5)


    def run_convert(self):
        infiles = self.conv_file_var.get()
        if not infiles: return
        infiles = infiles.split('|')
        
        raw_fmt = self.fmt_var.get()
        fmt = raw_fmt.split(" ")[0].lower()
        
        tasks = []
        for infile in infiles:
            if not infile.strip(): continue
            outfile = os.path.join(self.output_dir, f"{os.path.splitext(os.path.basename(infile))[0]}_conv.{fmt}")
            outfile = self.get_unique_path(outfile)
            
            self.log(f"準備分析 {os.path.basename(infile)}...")
            try:
                probe_cmd = [
                    self.ffprobe_exe, "-v", "quiet", "-print_format", "json",
                    "-show_streams", infile
                ]
                result = subprocess.run(probe_cmd, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                probe_data = json.loads(result.stdout)
                
                vcodec = None
                acodec = None
                for stream in probe_data.get('streams', []):
                    if stream.get('codec_type') == 'video' and not vcodec:
                        vcodec = stream.get('codec_name')
                    elif stream.get('codec_type') == 'audio' and not acodec:
                        acodec = stream.get('codec_name')
            except Exception as e:
                vcodec = None
                acodec = None

            is_audio_only = fmt in ["mp3", "wav", "flac", "m4a", "aac", "ogg", "wma"]
            
            cmd = [self.ffmpeg_exe, "-y", "-i", infile]
            
            if is_audio_only:
                cmd.extend(["-vn"]) # No video
                if fmt == "mp3":
                    cmd.extend(["-c:a", "libmp3lame", "-q:a", "2"])
                elif fmt == "wav":
                    cmd.extend(["-c:a", "pcm_s16le"])
                elif fmt == "flac":
                    cmd.extend(["-c:a", "flac"])
                elif fmt == "m4a":
                    cmd.extend(["-c:a", "aac", "-b:a", "192k"])
                elif fmt == "aac":
                    cmd.extend(["-c:a", "aac", "-b:a", "192k"])
                elif fmt == "ogg":
                    cmd.extend(["-c:a", "libvorbis", "-q:a", "4"])
                elif fmt == "wma":
                    cmd.extend(["-c:a", "wmav2", "-b:a", "192k"])
            else:
                compatible_vcodecs = ['h264']
                compatible_acodecs = ['aac']

                needs_vtranscode = vcodec not in compatible_vcodecs
                needs_atranscode = acodec not in compatible_acodecs
                
                if fmt in ["webm", "wmv", "mpeg", "avi", "flv"]:
                    needs_vtranscode = True
                    needs_atranscode = True

                if not needs_vtranscode and not needs_atranscode:
                    cmd.extend(["-c", "copy"])
                else:
                    if fmt == "webm":
                        cmd.extend(["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0"])
                        cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
                    elif fmt == "wmv":
                        cmd.extend(["-c:v", "wmv2", "-b:v", "4M", "-c:a", "wmav2", "-b:a", "192k", "-pix_fmt", "yuv420p"])
                    elif fmt == "mpeg":
                        # Use MPEG-1 for maximum out-of-the-box compatibility on modern Windows
                        cmd.extend(["-c:v", "mpeg1video", "-q:v", "4", "-c:a", "mp2", "-b:a", "192k", "-pix_fmt", "yuv420p"])
                    elif fmt == "avi":
                        cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "mp3", "-b:a", "192k"])
                    elif fmt == "flv":
                        cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23", "-c:a", "aac", "-b:a", "192k"])
                    else:
                        if needs_vtranscode:
                            cmd.extend(["-c:v", "libx264", "-preset", "fast", "-crf", "23"])
                        else:
                            cmd.extend(["-c:v", "copy"])
                            
                        if needs_atranscode:
                            cmd.extend(["-c:a", "aac", "-b:a", "192k"])
                        else:
                            cmd.extend(["-c:a", "copy"])
                
                if fmt in ["mp4", "mov"]:
                    cmd.extend(["-movflags", "+faststart"])

            cmd.append(outfile)
            tasks.append({'cmd': cmd, 'duration': 0, 'out_path': outfile})
            
        if tasks:
            self.run_ffmpeg_batch(tasks, f"批次轉換完成！")
    def setup_audio_tab(self, parent):
        ctk.CTkLabel(parent, text="從影片中提取音訊 (MP3 / WAV)", font=("Microsoft JhengHei UI", 18, "bold"), text_color="#F57C00").pack(anchor="w", pady=(10, 10))
        
        self.audio_file_var = ctk.StringVar()
        self.audio_file_box = ctk.CTkTextbox(parent, height=120, font=self.font_ui)
        self.audio_file_box.insert("1.0", "請點選下方「加入影片檔案」選擇單一或多個來源影片 (支援按住 Ctrl/Shift 批次多選)...")
        self.audio_file_box.configure(state="disabled")
        self.audio_file_box.pack(anchor="w", fill="x", padx=(0, 20), pady=5)
        btn_box_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_box_frame.pack(anchor="w", pady=5)
        ctk.CTkButton(btn_box_frame, text="加入影片檔案", command=lambda: self.browse_multiple(self.audio_file_var, self.audio_file_box), font=self.font_ui, fg_color="#1E88E5").pack(side="left", padx=(0, 10))
        ctk.CTkButton(btn_box_frame, text="清空列表", command=lambda: self.clear_inputs("audio"), font=self.font_ui, fg_color="#757575", hover_color="#616161", width=100).pack(side="left")
        
        ctk.CTkLabel(parent, text="輸出格式:", font=self.font_ui).pack(anchor="w", pady=(20, 5))
        self.audio_fmt_var = ctk.StringVar(value="mp3")
        ctk.CTkSegmentedButton(parent, variable=self.audio_fmt_var, values=["mp3", "wav", "flac", "m4a"], font=self.font_ui, width=400).pack(anchor="w", pady=5)
        
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(anchor="w", pady=30)
        ctk.CTkButton(btn_frame, text="開始提取", command=self.run_extract, fg_color="#E91E63", hover_color="#C2185B", font=self.font_tab, width=150).pack(side="left", padx=(0, 10))
        ctk.CTkButton(btn_frame, text="開啟輸出資料夾", command=lambda: os.startfile(self.output_dir), font=self.font_tab, width=150, fg_color="#4CAF50", hover_color="#388E3C", text_color="white").pack(side="left", padx=10)


    def run_extract(self):
        infiles = self.audio_file_var.get()
        if not infiles: return
        infiles = infiles.split('|')
        
        fmt = self.audio_fmt_var.get()
        
        tasks = []
        for infile in infiles:
            if not infile.strip(): continue
            outfile = os.path.join(self.output_dir, f"{os.path.splitext(os.path.basename(infile))[0]}_audio.{fmt}")
            outfile = self.get_unique_path(outfile)
            
            cmd = [self.ffmpeg_exe, "-y", "-i", infile, "-vn"]
            if fmt == "mp3": cmd.extend(["-c:a", "libmp3lame", "-q:a", "2"])
            elif fmt == "wav": cmd.extend(["-c:a", "pcm_s16le"])
            cmd.append(outfile)
            
            tasks.append({'cmd': cmd, 'duration': 0, 'out_path': outfile})
            
        if tasks:
            self.run_ffmpeg_batch(tasks, "批次提取音訊完成！")
    def setup_trim_tab(self, parent):
        # Configure grid for parent (expand video area)
        parent.grid_columnconfigure(0, weight=1)
        # Row 0: File select, Row 1: Video Preview, Row 2: Controls, Row 3: Action
        parent.grid_rowconfigure(1, weight=1) 
        
        # 1. File Selection
        self.trim_file_var = ctk.StringVar()
        file_frame = ctk.CTkFrame(parent, fg_color="transparent")
        file_frame.grid(row=0, column=0, sticky="ew", pady=(10, 5))
        
        ctk.CTkEntry(file_frame, textvariable=self.trim_file_var, width=600, placeholder_text="選擇來源影片或音訊...", font=self.font_ui).pack(side="left", padx=(0, 10))
        ctk.CTkButton(file_frame, text="加入檔案", command=self.browse_trim_video, font=self.font_ui, fg_color="#3949AB").pack(side="left")
        
        self.use_proxy_var = tk.BooleanVar(value=False)
        self.cb_use_proxy = ctk.CTkCheckBox(file_frame, text="優化預覽畫面 (低配電腦建議)", variable=self.use_proxy_var, font=self.font_small)
        self.cb_use_proxy.pack(side="left", padx=20)
        
        ctk.CTkLabel(file_frame, text="(支援讀取影片或純音訊檔)", text_color="gray", font=self.font_small).pack(side="left", padx=10)

        # 2. Video Preview Area (Adjusted to 680x382 for maximum screen compatibility)
        self.preview_label = ctk.CTkLabel(parent, text="無預覽畫面", width=680, height=382, fg_color="black", font=self.font_ui)
        self.preview_label.grid(row=1, column=0, pady=5) # Reduced pady
        
        # 3. Timeline Slider
        slider_frame = ctk.CTkFrame(parent, fg_color="transparent")
        slider_frame.grid(row=2, column=0, sticky="ew", pady=5)
        
        self.time_label = ctk.CTkLabel(slider_frame, text="00:00:00.00 / 00:00:00.00", font=self.font_ui, width=200)
        self.time_label.pack(side="right", padx=10)
        
        # On seek/drag, stop playing
        self.timeline_slider = ctk.CTkSlider(slider_frame, from_=0, to=100, command=self.on_slider_drag, state="disabled")
        self.timeline_slider.pack(side="left", fill="x", expand=True, padx=10)
        self.timeline_slider.set(0)

        # 4. Controls
        ctrl_frame = ctk.CTkFrame(parent, fg_color="transparent")
        ctrl_frame.grid(row=3, column=0, pady=5) # Reduced pady from 10
        
        # Group 1: Start (Blue)
        ctk.CTkButton(ctrl_frame, text="設定起點", command=self.set_start_mark, width=100, font=self.font_ui, fg_color="#1E88E5").pack(side="left", padx=5)
        self.start_time = ctk.CTkEntry(ctrl_frame, width=120, placeholder_text="00:00:00.00", font=self.font_ui)
        self.start_time.pack(side="left", padx=5)
        
        # Spacer
        ctk.CTkLabel(ctrl_frame, text="   |   ", font=self.font_ui).pack(side="left")

        # Group 2: Playback Controls (Dark Grey + BOLD ICONS)
        btn_width = 40
        btn_color = "#455A64" # Blue Grey
        btn_hover = "#607D8B"
        font_icon = ("Arial", 20, "bold") # Larger/Bold Icons
        
        self.btn_seek_start = ctk.CTkButton(ctrl_frame, text="|<", width=btn_width, command=self.seek_to_start_mark, fg_color=btn_color, hover_color=btn_hover, font=font_icon, state="disabled")
        self.btn_seek_start.pack(side="left", padx=2)
        
        self.btn_seek_back = ctk.CTkButton(ctrl_frame, text="<<", width=btn_width, command=lambda: self.seek_relative(-5), fg_color=btn_color, hover_color=btn_hover, font=font_icon, state="disabled")
        self.btn_seek_back.pack(side="left", padx=2)
        
        self.btn_play = ctk.CTkButton(ctrl_frame, text="▶", width=50, command=self.toggle_play, fg_color="#2E7D32", font=font_icon, state="disabled") # Green
        self.btn_play.pack(side="left", padx=5)
        
        self.btn_seek_fwd = ctk.CTkButton(ctrl_frame, text=">>", width=btn_width, command=lambda: self.seek_relative(5), fg_color=btn_color, hover_color=btn_hover, font=font_icon, state="disabled")
        self.btn_seek_fwd.pack(side="left", padx=2)
        
        self.btn_seek_end = ctk.CTkButton(ctrl_frame, text=">|", width=btn_width, command=self.seek_to_end_mark, fg_color=btn_color, hover_color=btn_hover, font=font_icon, state="disabled")
        self.btn_seek_end.pack(side="left", padx=2)
        
        # Spacer
        ctk.CTkLabel(ctrl_frame, text="   |   ", font=self.font_ui).pack(side="left")

        # Group 3: End (Blue)
        self.end_time = ctk.CTkEntry(ctrl_frame, width=120, placeholder_text="00:00:00.00", font=self.font_ui)
        self.end_time.pack(side="left", padx=5)
        ctk.CTkButton(ctrl_frame, text="設定終點", command=self.set_end_mark, width=100, font=self.font_ui, fg_color="#1E88E5").pack(side="left", padx=5)

        # Mode Selection
        mode_frame = ctk.CTkFrame(parent, fg_color="transparent")
        mode_frame.grid(row=4, column=0, pady=5)
        ctk.CTkLabel(mode_frame, text="剪輯模式:", font=self.font_ui).pack(side="left", padx=10)
        self.trim_mode_var = ctk.StringVar(value="保留此區段")
        ctk.CTkSegmentedButton(mode_frame, variable=self.trim_mode_var, values=["保留此區段", "刪除此區段 (其餘合併)"], font=self.font_ui, selected_color="#E65100", selected_hover_color="#EF6C00").pack(side="left")

        # Action (Row 5 now)
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.grid(row=5, column=0, pady=(10, 5))
        self.btn_trim = ctk.CTkButton(btn_frame, text="開始剪輯", command=self.run_trim, fg_color="#E91E63", hover_color="#C2185B", font=self.font_tab, width=150, state="disabled")
        self.btn_trim.pack(side="left", padx=(0, 10))
        ctk.CTkButton(btn_frame, text="開啟輸出資料夾", command=lambda: os.startfile(self.output_dir), font=self.font_tab, width=150, fg_color="#4CAF50", hover_color="#388E3C", text_color="white").pack(side="left", padx=10)

    def set_controls_state(self, state):
        if hasattr(self, 'btn_play'):
            self.btn_play.configure(state=state)
            self.btn_seek_start.configure(state=state)
            self.btn_seek_back.configure(state=state)
            self.btn_seek_fwd.configure(state=state)
            self.btn_seek_end.configure(state=state)
            self.btn_trim.configure(state=state)
            self.timeline_slider.configure(state=state)

    def browse_trim_video(self):
        init_dir = os.path.join(self.script_dir, "Outputs")
        f = filedialog.askopenfilename(initialdir=init_dir, filetypes=[("Media Files", "*.mp4;*.mkv;*.avi;*.mov;*.flv;*.wmv;*.wav;*.mp3;*.m4a;*.flac;*.aac;*.ogg;*.wma")])
        if f:
            self.trim_file_var.set(f)
            self.load_video(f)

    def load_video(self, path):
        # Reuse check
        reuse_proxy = False
        current_path = getattr(self, "current_video_path", None)
        
        self.release_video()
        
        if path == current_path:
            reuse_proxy = True
        else:
            self.cleanup_temp_files()
            self.current_video_path = path
        
        self.is_audio_only = False
        duration = 0
        
        try:
            # 1. Try Video via OpenCV
            self.cap = cv2.VideoCapture(path)
            valid_video = False
            if self.cap.isOpened():
                self.fps = self.cap.get(cv2.CAP_PROP_FPS)
                frame_count = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
                if frame_count > 0 and self.fps > 0:
                    self.total_frames = int(frame_count)
                    duration = self.total_frames / self.fps
                    valid_video = True
            
            # 2. If OpenCV fails or empty, treat as Audio (use FFmpeg for duration)
            if not valid_video:
                if self.cap: self.cap.release()
                self.cap = None
                self.is_audio_only = True
                
                # Get Duration via FFmpeg
                try:
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    cmd = [self.ffmpeg_exe, "-i", path]
                    res = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, startupinfo=startupinfo, encoding='utf-8', errors='replace')
                    import re
                    match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2})\.(\d{2})", res.stderr)
                    if match:
                        h, m, s, ms = map(int, match.groups())
                        duration = h * 3600 + m * 60 + s + ms / 100.0
                except Exception as e:
                    print(f"Duration Probe Error: {e}")

                if duration > 0:
                    self.fps = 10.0 # Fake FPS for smooth slider
                    self.total_frames = int(duration * self.fps)
                else:
                    messagebox.showerror("錯誤", "無法讀取檔案 (或檔案長度為0)")
                    return

            # UI Updates
            self.set_controls_state("disabled")
            self.update_progress(0, "0%")
            
            self.timeline_slider.configure(state="normal", to=self.total_frames)
            self.timeline_slider.set(0)
            
            self.current_frame_idx = 0
            self.update_time_label(0, duration)
            self.is_proxy = False
            
            # Auto-set Start/End Time
            total_str = self.get_time_str(self.total_frames)
            self.start_time.delete(0, "end")
            self.start_time.insert(0, "00:00:00.00")
            self.end_time.delete(0, "end")
            self.end_time.insert(0, total_str)
            
            # Preview
            if not self.is_audio_only:
                self.seek_video(0)
            else:
                self.preview_label.configure(image="", text="音訊模式\n\n無影像預覽", font=("Microsoft JhengHei UI", 24))
                self.preview_label.image = None
            
            # Async Prepare
            threading.Thread(target=self.prepare_resources, args=(path, reuse_proxy), daemon=True).start()
            
        except Exception as e:
            messagebox.showerror("錯誤", f"載入失敗: {e}")

    def prepare_resources(self, path, reuse_proxy=False):
        # 1. Extract Audio
        try:
            temp_wav = os.path.join(self.temp_dir, "preview.wav")
            # If reuse and exists, skip extraction
            if reuse_proxy and os.path.exists(temp_wav):
                 # Load existing
                 self.log("🔊 載入快取音訊...")
            else:
                self.log("⏳ 正在準備預覽資源...")
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
                # Audio
                subprocess.run([
                    self.ffmpeg_exe, "-y", "-i", path, 
                    "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                    temp_wav
                ], startupinfo=startupinfo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            if os.path.exists(temp_wav):
                data, samplerate = sf.read(temp_wav, dtype='float32')
                self.audio_data = data
                self.samplerate = samplerate
                self.audio_ready = True
                self.log("🔊 音訊就緒")
            else:
                self.log("⚠️ 無法載入音訊")
                
        except Exception as e:
            print(f"Audio Load Error: {e}")
            self.log("⚠️ 音訊載入失敗")

        # 2. Generate Proxy if enabled (Height > 720)
        if not self.use_proxy_var.get():
             self.log("🚀 使用原始畫面預覽 (高效能)")
             self.after(0, lambda: self.set_controls_state("normal"))
             return

        try:
            if not self.cap:
                # Audio Mode: No proxy needed
                self.log("✅ 音訊就緒")
                self.after(0, lambda: self.set_controls_state("normal"))
                return

            h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            if h is not None and h > 720:
                proxy_path = os.path.join(self.temp_dir, "proxy_preview.mp4")
                
                if reuse_proxy and os.path.exists(proxy_path):
                     # Fast Skip
                     self.log("🚀 快取優化就緒")
                     self.after(0, lambda: self.swap_to_proxy(proxy_path))
                     return

                self.log("⚙️ 正在生成優化畫面，請稍等....")
                
                cmd = [
                    self.ffmpeg_exe, "-y", "-i", path,
                    "-vf", "scale=-2:720", # Scale to 720p height, keep aspect ratio
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                    "-an", # No audio needed for proxy video
                    proxy_path
                ]
                
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                # Use Popen to capture progress
                process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                           universal_newlines=True, encoding='utf-8', errors='replace', startupinfo=startupinfo)
                
                duration = 0
                if self.fps > 0 and self.total_frames > 0:
                    duration = self.total_frames / self.fps
                
                import re
                
                for line in process.stdout:
                    line = line.strip()
                    if not line: continue

                    # Parse Time for Progress
                    if "time=" in line and duration > 0:
                         match = re.search(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})", line)
                         if match:
                             h, m, s, ms = map(int, match.groups())
                             current_time = h * 3600 + m * 60 + s + ms / 100.0
                             percent = min(current_time / duration, 0.99)
                             self.after(0, lambda v=percent: self.update_progress(v, f"優化中 {int(v*100)}%"))
                
                process.wait()
                
                # Clear progress bar
                self.after(0, lambda: self.update_progress(0, "0%"))

                if process.returncode == 0 and os.path.exists(proxy_path):
                    self.after(0, lambda: self.swap_to_proxy(proxy_path))
                else:
                    self.log("⚠️ 優化畫面生成失敗")
                    self.after(0, lambda: self.set_controls_state("normal"))
            else:
                self.log("✅ 預覽資源準備完成")
                self.after(0, lambda: self.set_controls_state("normal"))
                
        except Exception as e:
            print(f"Proxy Error: {e}")
            self.log("⚠️ 優化畫面生成失敗")

    def swap_to_proxy(self, proxy_path):
        if not self.cap: return
        self.log("🔄 切換至流暢模式")
        
        # Keep position
        current_pos = self.current_frame_idx
        was_playing = self.is_playing
        self.stop_play()
        
        self.cap.release()
        try:
            self.cap = cv2.VideoCapture(proxy_path)
            self.is_proxy = True
            
            # Seek back
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, current_pos)
            self.seek_video(current_pos)
            
            self.log("🚀 優化預覽就緒")
            self.set_controls_state("normal")
            if was_playing: self.toggle_play()
            
        except Exception as e:
            self.log(f"⚠️ 切換失敗: {e}")

    def on_slider_drag(self, value):
        self.stop_play()
        self.seek_video(value)

    def seek_video(self, value):
        frame_idx = int(value)
        self.current_frame_idx = frame_idx
        
        if not self.cap:
            # Audio Mode
            current_sec = frame_idx / self.fps if self.fps > 0 else 0
            self.update_time_label(current_sec)
            return

        # Seek
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = self.cap.read()
        
        if ret:
            self.show_frame(frame)
            
            # Update Time Label
            current_sec = frame_idx / self.fps if self.fps > 0 else 0
            self.update_time_label(current_sec)

    def toggle_play(self):
        if self.is_playing:
            self.stop_play()
        else:
            # Check Range
            try:
                start_sec = self.time_str_to_seconds(self.start_time.get())
                end_sec = self.time_str_to_seconds(self.end_time.get())
                
                start_frame = int(start_sec * self.fps)
                end_frame = int(end_sec * self.fps)
                
                # If current position is explicitly outside range (before start or after end), jump to start
                # Also if very close to end
                if self.current_frame_idx < start_frame - 5 or self.current_frame_idx >= end_frame - 5:
                    self.current_frame_idx = start_frame
                    self.timeline_slider.set(start_frame)
                    
                    if self.cap:
                        self.cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                        ret, frame = self.cap.read()
                        if ret: self.show_frame(frame)
                    else:
                        # Audio Mode Visual Update
                        pass
                    
                    # Update label
                    self.update_time_label(start_frame / self.fps)

            except: pass

            self.is_playing = True
            self.btn_play.configure(text="⏸", fg_color="#D32F2F") # Pause icon
            
            # Start Audio
            current_sec = self.current_frame_idx / self.fps if self.fps > 0 else 0
            
            if self.audio_ready and self.audio_data is not None:
                start_sample = int(current_sec * self.samplerate)
                end_sample = int(self.time_str_to_seconds(self.end_time.get()) * self.samplerate) # Limit audio play
                
                if start_sample < len(self.audio_data):
                    try:
                        # Play only until end? sd.play doesn't easily support 'until', it plays array.
                        # So slice the array: [start:end]
                        # Ensure end_sample is valid
                        if end_sample > len(self.audio_data): end_sample = len(self.audio_data)
                        if end_sample > start_sample:
                             sd.play(self.audio_data[start_sample:end_sample], self.samplerate)
                    except Exception as e:
                        print(f"Audio Play Error: {e}")
            
            self.play_start_time = time.time()
            self.video_start_sec = current_sec
            self.play_video_loop()
    
    def stop_play(self):
        self.is_playing = False
        if hasattr(self, 'btn_play'):
            self.btn_play.configure(text="▶", fg_color="#2E7D32") # Play icon
        
        sd.stop() # Stop audio
        
        if self.play_job:
            self.after_cancel(self.play_job)
            self.play_job = None

    def play_video_loop(self):
        if not self.is_playing:
            return

        # Time-based sync
        elapsed = time.time() - self.play_start_time
        target_sec = self.video_start_sec + elapsed
        target_frame = int(target_sec * self.fps)
        
        if target_frame >= self.total_frames:
            self.stop_play()
            return

        # Check Cut End
        end_sec = self.time_str_to_seconds(self.end_time.get())
        if end_sec > 0:
            end_frame = int(end_sec * self.fps)
            if target_frame >= end_frame:
                self.stop_play()
                # Determine stick to end?
                self.current_frame_idx = end_frame
                self.timeline_slider.set(end_frame)
                return

        # Update UI (Slider)
        self.current_frame_idx = target_frame
        self.timeline_slider.set(target_frame)
        self.update_time_label(target_sec)

        # Video Sync & Render (Only if video mode)
        if self.cap:
            diff = target_frame - int(self.cap.get(cv2.CAP_PROP_POS_FRAMES))
            
            # If drift is large, seek
            if diff < 0 or diff > 10:
                 self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            # If slight lag, skip
            elif diff > 0:
                for _ in range(diff):
                    self.cap.read()
            
            ret, frame = self.cap.read()
            if ret:
                self.show_frame(frame)
        
        self.play_job = self.after(30, self.play_video_loop)

    def seek_relative(self, sec):
        self.stop_play()
        
        target_frame = self.current_frame_idx + int(sec * self.fps)
        target_frame = max(0, min(target_frame, self.total_frames - 1))
        
        self.timeline_slider.set(target_frame)
        self.seek_video(target_frame)
        
    def time_str_to_seconds(self, t_str):
        try:
            h, m, s = t_str.split(':')
            return int(h) * 3600 + int(m) * 60 + float(s)
        except:
            return 0

    def seek_to_start_mark(self):
        # Go to start time (if valid)
        t_str = self.start_time.get()
        if t_str:
            sec = self.time_str_to_seconds(t_str)
            target_frame = int(sec * self.fps)
            self.timeline_slider.set(target_frame)
            self.on_slider_drag(target_frame)

    def seek_to_end_mark(self):
        # Go to end time (if valid)
        t_str = self.end_time.get()
        if t_str:
            sec = self.time_str_to_seconds(t_str)
            target_frame = int(sec * self.fps)
            self.timeline_slider.set(target_frame)
            self.on_slider_drag(target_frame)

    def show_frame(self, frame):
        # Resize to fit preview label (keep aspect ratio)
        h, w, _ = frame.shape
        display_w, display_h = 680, 382 # Compact size for maximum compatibility
        
        scale = min(display_w/w, display_h/h)
        new_w, new_h = int(w*scale), int(h*scale)
        
        # Use INTER_AREA for high-quality downscaling (sharper text)
        interp = cv2.INTER_AREA if not self.is_proxy else cv2.INTER_LINEAR
        frame = cv2.resize(frame, (new_w, new_h), interpolation=interp)
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        img = Image.fromarray(frame)
        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(new_w, new_h))
        
        self.preview_label.configure(text="", image=ctk_img)
        self.preview_label.image = ctk_img # Keep reference

    def update_time_label(self, current_sec, total_sec=None):
        def fmt(sec):
            ms = int((sec % 1) * 100)
            h = int(sec // 3600)
            m = int((sec % 3600) // 60)
            s = int(sec % 60)
            return f"{h:02d}:{m:02d}:{s:02d}.{ms:02d}"
        
        curr_str = fmt(current_sec)
        if total_sec is None and self.fps > 0:
            total_sec = self.total_frames / self.fps
        
        total_str = fmt(total_sec) if total_sec else "00:00:00.00"
        self.time_label.configure(text=f"{curr_str} / {total_str}")

    def get_time_str(self, frame_idx):
        if self.fps <= 0: return "00:00:00"
        sec = frame_idx / self.fps
        ms = int((sec % 1) * 100)
        h = int(sec // 3600)
        m = int((sec % 3600) // 60)
        s = int(sec % 60)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:02d}"

    def time_str_to_seconds(self, t_str):
        try:
            parts = t_str.strip().split(':')
            if len(parts) == 3:
                h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
                return h * 3600 + m * 60 + s
            elif len(parts) == 2:
                m, s = float(parts[0]), float(parts[1])
                return m * 60 + s
            else:
                return float(t_str)
        except:
            return 0.0

    def set_start_mark(self):
        t_str = self.get_time_str(self.current_frame_idx)
        self.start_time.delete(0, "end")
        self.start_time.insert(0, t_str)

    def set_end_mark(self):
        t_str = self.get_time_str(self.current_frame_idx)
        self.end_time.delete(0, "end")
        self.end_time.insert(0, t_str)

    def run_trim(self):
        infile = self.trim_file_var.get()
        start = self.start_time.get()
        end = self.end_time.get()
        
        if not infile:
            messagebox.showwarning("提示", "請先選擇影片檔案")
            return
        if not start:
            messagebox.showwarning("提示", "請設定開始時間")
            return
        if not end:
            messagebox.showwarning("提示", "請設定結束時間")
            return
            
        mode = getattr(self, "trim_mode_var", ctk.StringVar(value="保留此區段")).get()
        
        # Release video before processing to avoid file lock
        self.release_video()
        
        ext = os.path.splitext(infile)[1]
        base_name = os.path.splitext(os.path.basename(infile))[0]
        
        if mode == "保留此區段":
            outfile = os.path.join(self.output_dir, f"{base_name}_trim{ext}")
            outfile = self.get_unique_path(outfile)
            
            # Use input seeking (-ss before -i) for better keyframe handling and to avoid blank starts
            start_sec = self.time_str_to_seconds(start)
            end_sec = self.time_str_to_seconds(end)
            duration = max(0, end_sec - start_sec)
            
            cmd = [
                self.ffmpeg_exe, "-y", 
                "-ss", start,
                "-i", infile,
                "-t", str(duration),
                "-c", "copy",
                outfile
            ]
            self.run_ffmpeg(cmd, "剪輯完成", out_path=outfile)
        else:
            # Delete segment = concat start..start_time and end_time..end
            outfile = os.path.join(self.output_dir, f"{base_name}_cut{ext}")
            outfile = self.get_unique_path(outfile)
            
            part1 = os.path.join(self.temp_dir, f"part1{ext}")
            part2 = os.path.join(self.temp_dir, f"part2{ext}")
            concat_txt = os.path.join(self.temp_dir, "concat.txt")
            
            def _complex_thread():
                try:
                    self.after(0, lambda: self.log("⏳ 反向剪輯處理中... (提取片段1)"))
                    self.after(0, lambda: self.update_progress(0, "提取前段..."))
                    self.after(0, lambda: self.clear_inputs("trim"))
                    self.after(0, lambda: self.btn_trim.configure(state="disabled"))
                    
                    startupinfo = subprocess.STARTUPINFO()
                    if os.name == 'nt': startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    
                    cmd1 = [self.ffmpeg_exe, "-y", "-i", infile, "-to", start, "-c", "copy", part1]
                    cmd2 = [self.ffmpeg_exe, "-y", "-ss", end, "-i", infile, "-c", "copy", part2]
                    
                    # 1. Extract part 1 conditionally
                    start_sec = self.time_str_to_seconds(start)
                    if start_sec > 0.05:
                        res1 = subprocess.run(cmd1, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if res1.returncode != 0: raise Exception("前段提取失敗")
                    
                    self.after(0, lambda: self.update_progress(0.33, "提取後段..."))
                    self.after(0, lambda: self.log("⏳ 提取片段2..."))
                    
                    # 2. Extract part 2
                    res2 = subprocess.run(cmd2, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if res2.returncode != 0: raise Exception("後段提取失敗")
                    
                    self.after(0, lambda: self.update_progress(0.66, "合併片段..."))
                    self.after(0, lambda: self.log("⏳ 正在無損合併片段..."))
                    
                    # 3. Create concat.txt
                    with open(concat_txt, "w", encoding="utf-8") as f:
                        if os.path.exists(part1) and os.path.getsize(part1) > 100:
                            safe_part1 = part1.replace('\\', '/').replace("'", r"\'")
                            f.write(f"file '{safe_part1}'\n")
                        if os.path.exists(part2) and os.path.getsize(part2) > 100:
                            safe_part2 = part2.replace('\\', '/').replace("'", r"\'")
                            f.write(f"file '{safe_part2}'\n")
                        
                    # 4. Merge
                    cmd3 = [self.ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", concat_txt, "-c", "copy", outfile]
                    res3 = subprocess.run(cmd3, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if res3.returncode != 0: raise Exception("合併步驟失敗，請確認影片格式是否支援。")
                    
                    # Clean up
                    try:
                        if os.path.exists(part1): os.remove(part1)
                        if os.path.exists(part2): os.remove(part2)
                        if os.path.exists(concat_txt): os.remove(concat_txt)
                    except: pass
                    
                    self.after(0, lambda: self.update_progress(1.0, "反向剪輯完成"))
                    self.after(0, lambda: self.log("反向剪輯完成"))
                    self.after(0, lambda msg="反向剪輯完成": self.show_success_and_cleanup("成功", msg))
                    self.after(0, lambda: os.startfile(self.output_dir))
                    
                except Exception as e:
                    self.after(0, lambda err=str(e): self.log(f"剪輯失敗: {err}"))
                    self.after(0, lambda: self.update_progress(0, "錯誤"))
                    self.after(0, lambda err=str(e): messagebox.showerror("錯誤", f"剪輯無法完成:\\n{err}"))
                finally:
                    self.after(0, lambda: self.btn_trim.configure(state="normal"))

            threading.Thread(target=_complex_thread, daemon=True).start()

    # --- 4. Merger ---
    def setup_merge_tab(self, parent):
        ctk.CTkLabel(parent, text="合併影片+音訊檔案", font=("Microsoft JhengHei UI", 18, "bold"), text_color="#7B1FA2").pack(anchor="w", pady=(10, 20))
        
        # Video Input Group
        vid_frame = ctk.CTkFrame(parent, fg_color="transparent")
        vid_frame.pack(anchor="w", pady=5)
        ctk.CTkLabel(vid_frame, text="影片: ", font=self.font_ui).pack(side="left")
        self.merge_video_var = ctk.StringVar()
        ctk.CTkEntry(vid_frame, textvariable=self.merge_video_var, width=750, placeholder_text="影片來源...", font=self.font_ui).pack(side="left", padx=5)
        ctk.CTkButton(parent, text="加入影片檔案", command=lambda: self.browse(self.merge_video_var), font=self.font_ui, fg_color="#1E88E5", hover_color="#1565C0").pack(anchor="w", pady=(0, 15))
        
        # Audio Input Group
        aud_frame = ctk.CTkFrame(parent, fg_color="transparent")
        aud_frame.pack(anchor="w", pady=5)
        ctk.CTkLabel(aud_frame, text="音訊: ", font=self.font_ui).pack(side="left")
        self.merge_audio_var = ctk.StringVar()
        ctk.CTkEntry(aud_frame, textvariable=self.merge_audio_var, width=750, placeholder_text="音訊來源...", font=self.font_ui).pack(side="left", padx=5)
        ctk.CTkButton(parent, text="加入音訊檔案", command=lambda: self.browse(self.merge_audio_var), font=self.font_ui, fg_color="#43A047", hover_color="#2E7D32").pack(anchor="w", pady=(0, 15))
        
        # Mix Audio Option
        self.mix_var = ctk.BooleanVar(value=True) # Default Mix
        ctk.CTkCheckBox(parent, text="混音模式 (保留影片原音並與新音訊合併)", variable=self.mix_var, font=self.font_ui, command=self.toggle_mix_controls).pack(anchor="w", pady=5)
        
        # Volume Controls Frame
        self.vol_frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.vol_frame.pack(anchor="w", pady=5, padx=20)
        
        # Video Volume
        ctk.CTkLabel(self.vol_frame, text="影片原音音量:", font=self.font_ui).grid(row=0, column=0, padx=5, sticky="e")
        self.vol_v_slider = ctk.CTkSlider(self.vol_frame, from_=0, to=200, number_of_steps=20, width=200, command=lambda v: self.vol_v_label.configure(text=f"{int(v)}%"))
        self.vol_v_slider.set(100)
        self.vol_v_slider.grid(row=0, column=1, padx=5)
        self.vol_v_label = ctk.CTkLabel(self.vol_frame, text="100%", font=self.font_ui, width=50)
        self.vol_v_label.grid(row=0, column=2, padx=5)

        # Audio Volume
        ctk.CTkLabel(self.vol_frame, text="外部音訊音量:", font=self.font_ui).grid(row=1, column=0, padx=5, sticky="e", pady=10)
        self.vol_a_slider = ctk.CTkSlider(self.vol_frame, from_=0, to=200, number_of_steps=20, width=200, command=lambda v: self.vol_a_label.configure(text=f"{int(v)}%"))
        self.vol_a_slider.set(100)
        self.vol_a_slider.grid(row=1, column=1, padx=5, pady=10)
        self.vol_a_label = ctk.CTkLabel(self.vol_frame, text="100%", font=self.font_ui, width=50)
        self.vol_a_label.grid(row=1, column=2, padx=5, pady=10)
        
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(anchor="w", pady=30)
        ctk.CTkButton(btn_frame, text="開始合成", command=self.run_merge, fg_color="#E91E63", hover_color="#C2185B", font=("Microsoft JhengHei UI", 18, "bold"), width=180, height=50, text_color="white").pack(side="left", padx=(0, 10))
        ctk.CTkButton(btn_frame, text="開啟輸出資料夾", command=lambda: os.startfile(self.output_dir), font=("Microsoft JhengHei UI", 16, "bold"), width=140, height=50, fg_color="#4CAF50", hover_color="#388E3C", text_color="white").pack(side="left", padx=10)

    def toggle_mix_controls(self):
        if self.mix_var.get():
            self.vol_frame.pack(anchor="w", pady=5, padx=20)
        else:
            self.vol_frame.pack_forget()

    def run_merge(self):
        v = self.merge_video_var.get()
        a = self.merge_audio_var.get()
        if not v or not a: return
        
        ext = os.path.splitext(v)[1]
        outfile = os.path.join(self.output_dir, f"{os.path.splitext(os.path.basename(v))[0]}_merged{ext}")
        outfile = self.get_unique_path(outfile)
        
        if self.mix_var.get():
            # Mix mode with volume
            vol_v = self.vol_v_slider.get() / 100.0
            vol_a = self.vol_a_slider.get() / 100.0
            
            cmd = [
                self.ffmpeg_exe, "-y",
                "-i", v, "-i", a,
                "-filter_complex", f"[0:a]volume={vol_v}[a0];[1:a]volume={vol_a}[a1];[a0][a1]amix=inputs=2:duration=longest[aout]",
                "-map", "0:v:0", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest", 
                outfile
            ]
        else:
            # Replace mode (Video audio ignored)
            cmd = [
                self.ffmpeg_exe, "-y",
                "-i", v, "-i", a,
                "-map", "0:v:0", "-map", "1:a:0",
                "-c:v", "copy", "-c:a", "aac",
                "-shortest", 
                outfile
            ]
            
        self.run_ffmpeg(cmd, "合併完成", out_path=outfile)

    # --- 5. Video Compressor ---
    def setup_compress_tab(self, parent):
        ctk.CTkLabel(parent, text="智能影片壓縮 (減少檔案體積)", font=("Microsoft JhengHei UI", 18, "bold"), text_color="#009688").pack(anchor="w", pady=(10, 20))
        
        # File Input
        self.compress_file_var = ctk.StringVar()
        self.compress_file_box = ctk.CTkTextbox(parent, height=120, font=self.font_ui)
        self.compress_file_box.insert("1.0", "請點選下方「加入影片檔案」選擇單一或多個影片 (支援按住 Ctrl/Shift 批次多選)...")
        self.compress_file_box.configure(state="disabled")
        self.compress_file_box.pack(anchor="w", fill="x", padx=(0, 20), pady=5)
        
        file_frame = ctk.CTkFrame(parent, fg_color="transparent")
        file_frame.pack(anchor="w", pady=5)
        ctk.CTkButton(file_frame, text="加入影片檔案", command=lambda: self.browse_multiple(self.compress_file_var, self.compress_file_box), font=self.font_ui, fg_color="#009688", hover_color="#00796B").pack(side="left", padx=(0, 10))
        ctk.CTkButton(file_frame, text="清空列表", command=lambda: self.clear_inputs("compress"), font=self.font_ui, fg_color="#757575", hover_color="#616161", width=100).pack(side="left")
        
        # Settings
        settings_frame = ctk.CTkFrame(parent, fg_color="transparent")
        settings_frame.pack(anchor="w", pady=10)
        
        font_combo = ("Microsoft JhengHei", 15)
        
        ctk.CTkLabel(settings_frame, text="目標畫質:", font=self.font_ui).grid(row=0, column=0, padx=5, sticky="e")
        self.comp_res_var = ctk.StringVar(value="保持原解析度")
        ctk.CTkComboBox(settings_frame, variable=self.comp_res_var, values=["保持原解析度", "1080p (FHD)", "720p (HD)", "480p (SD)"], font=font_combo, dropdown_font=font_combo, width=200).grid(row=0, column=1, padx=5, pady=5)
        
        ctk.CTkLabel(settings_frame, text="壓縮強度:", font=self.font_ui).grid(row=1, column=0, padx=5, sticky="e")
        self.comp_quality_var = ctk.StringVar(value="平衡 (Medium)")
        ctk.CTkComboBox(settings_frame, variable=self.comp_quality_var, values=["高品質 (檔案較大)", "平衡 (Medium)", "強烈壓縮 (檔案極小)"], font=font_combo, dropdown_font=font_combo, width=200).grid(row=1, column=1, padx=5, pady=5)
        
        # Action
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(anchor="w", pady=30)
        self.btn_run_compress = ctk.CTkButton(btn_frame, text="開始壓縮", command=self.run_compress, fg_color="#E91E63", hover_color="#C2185B", font=("Microsoft JhengHei UI", 18, "bold"), width=150, height=45)
        self.btn_run_compress.pack(side="left", padx=(0, 10))
        
        self.btn_stop_compress = ctk.CTkButton(btn_frame, text="中斷", command=self.cancel_ffmpeg, font=("Microsoft JhengHei UI", 16, "bold"), width=80, height=45, fg_color="#C0392B", hover_color="#922B21", state="disabled")
        self.btn_stop_compress.pack(side="left", padx=5)
        
        ctk.CTkButton(btn_frame, text="開啟輸出", command=lambda: os.startfile(self.output_dir), font=("Microsoft JhengHei UI", 16, "bold"), width=120, height=45, fg_color="#4CAF50", hover_color="#388E3C", text_color="white").pack(side="left", padx=10)


    def run_compress(self):
        infiles = self.compress_file_var.get()
        if not infiles: return
        infiles = infiles.split('|')
        
        quality_map = {
            "高品質 (檔案較大)": "22",
            "平衡 (Medium)": "28",
            "強烈壓縮 (檔案極小)": "35"
        }
        crf_val = quality_map.get(self.comp_quality_var.get(), "28")
        
        scale_opt = ""
        res_val = self.comp_res_var.get()
        if "1080p" in res_val: scale_opt = "-vf scale=-2:1080"
        elif "720p" in res_val: scale_opt = "-vf scale=-2:720"
        elif "480p" in res_val: scale_opt = "-vf scale=-2:480"
        
        tasks = []
        for infile in infiles:
            if not infile.strip(): continue
            ext = os.path.splitext(infile)[1]
            outfile = os.path.join(self.output_dir, f"{os.path.splitext(os.path.basename(infile))[0]}_compressed{ext}")
            outfile = self.get_unique_path(outfile)
            
            cmd = [self.ffmpeg_exe, "-y", "-i", infile]
            if scale_opt:
                 cmd.extend(scale_opt.split(" "))
            cmd.extend(["-c:v", "libx264", "-crf", crf_val, "-preset", "medium", "-c:a", "aac", "-b:a", "128k", outfile])
            
            duration = 0.0
            try:
                probe_cmd = [
                    os.path.join(self.tools_dir, "ffprobe.exe") if os.path.exists(os.path.join(self.tools_dir, "ffprobe.exe")) else "ffprobe", 
                    "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", infile
                ]
                startupinfo = subprocess.STARTUPINFO()
                if os.name == 'nt': startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                duration_out = subprocess.check_output(probe_cmd, stderr=subprocess.STDOUT, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW)
                duration = float(duration_out.decode('utf-8').strip())
            except: pass
            
            tasks.append({'cmd': cmd, 'duration': duration, 'out_path': outfile})
            
        if tasks:
            self.run_ffmpeg_batch(tasks, "批次壓縮完成！")
    def setup_cut_silence_tab(self, parent):
        ctk.CTkLabel(parent, text="自動裁剪靜音 (移除影片/音訊中的無聲片段)", font=("Microsoft JhengHei UI", 18, "bold"), text_color="#E64A19").pack(anchor="w", pady=(10, 20))
        
        # File Input
        self.silence_file_var = ctk.StringVar()
        file_frame = ctk.CTkFrame(parent, fg_color="transparent")
        file_frame.pack(anchor="w", pady=5)
        ctk.CTkEntry(file_frame, textvariable=self.silence_file_var, width=750, placeholder_text="選擇要裁剪的影片或音訊...", font=self.font_ui).pack(side="left", padx=(0, 10))
        ctk.CTkButton(file_frame, text="加入檔案", command=lambda: self.browse(self.silence_file_var), font=self.font_ui, fg_color="#E64A19", hover_color="#D84315").pack(side="left")
        
        # Settings
        settings_frame = ctk.CTkFrame(parent, fg_color="transparent")
        settings_frame.pack(anchor="w", pady=10)
        
        ctk.CTkLabel(settings_frame, text="靜音閥值 (dB):", font=self.font_ui).grid(row=0, column=0, padx=5, sticky="e")
        self.silence_thresh_var = ctk.StringVar(value="-40")
        ctk.CTkComboBox(settings_frame, variable=self.silence_thresh_var, values=["-30", "-40", "-50", "-60"], font=self.font_ui, width=150).grid(row=0, column=1, padx=5, pady=5)
        ctk.CTkLabel(settings_frame, text="(音量低於此值視為靜音，越向右側數字越小則越嚴格)", text_color="#ffffff", font=self.font_small).grid(row=0, column=2, padx=5, sticky="w")
        
        ctk.CTkLabel(settings_frame, text="靜音判斷時間 (秒):", font=self.font_ui).grid(row=1, column=0, padx=5, sticky="e")
        self.silence_duration_var = ctk.StringVar(value="0.5")
        ctk.CTkComboBox(settings_frame, variable=self.silence_duration_var, values=["0.3", "0.5", "1.0", "1.5", "2.0"], font=self.font_ui, width=150).grid(row=1, column=1, padx=5, pady=5)
        ctk.CTkLabel(settings_frame, text="(持續靜音超過此長度才會被剪掉)", text_color="#ffffff", font=self.font_small).grid(row=1, column=2, padx=5, sticky="w")
        
        # Alert for Video
        ctk.CTkLabel(parent, text="⚠️ 注意：這項功能會重新編碼影片，可能需要較長的處理時間。\n建議先用較短的檔案測試您的靜音參數。", text_color="#FFB300", font=self.font_ui, justify="left").pack(anchor="w", padx=10, pady=10)

        # Action
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(anchor="w", pady=20)
        
        self.btn_run_silence = ctk.CTkButton(btn_frame, text="開始裁剪", command=self.run_cut_silence, fg_color="#E91E63", hover_color="#C2185B", font=("Microsoft JhengHei UI", 18, "bold"), width=150, height=45)
        self.btn_run_silence.pack(side="left", padx=(0, 10))
        
        self.btn_stop_silence = ctk.CTkButton(btn_frame, text="中斷", command=self.cancel_ffmpeg_advanced, font=("Microsoft JhengHei UI", 16, "bold"), width=80, height=45, fg_color="#C0392B", hover_color="#922B21", state="disabled")
        self.btn_stop_silence.pack(side="left", padx=5)
        
        ctk.CTkButton(btn_frame, text="開啟輸出", command=lambda: os.startfile(self.output_dir), font=("Microsoft JhengHei UI", 16, "bold"), width=120, height=45, fg_color="#4CAF50", hover_color="#388E3C", text_color="white").pack(side="left", padx=10)

    def cancel_ffmpeg_advanced(self):
        self.cancel_ffmpeg()

    def run_cut_silence(self):
        infile = self.silence_file_var.get()
        if not infile: return
        self.clear_inputs("cut_silence")
        
        ext = os.path.splitext(infile)[1].lower()
        outfile = os.path.join(self.output_dir, f"{os.path.splitext(os.path.basename(infile))[0]}_nosilence{ext}")
        outfile = self.get_unique_path(outfile)
        
        thresh = self.silence_thresh_var.get() + "dB"
        duration = self.silence_duration_var.get()
        
        is_video = ext in ['.mp4', '.avi', '.mov', '.mkv']
        
        # Audio filter: silenceremove=stop_periods=-1:stop_duration=X:stop_threshold=Y
        af = f"silenceremove=stop_periods=-1:stop_duration={duration}:stop_threshold={thresh}"
        
        cmd = [self.ffmpeg_exe, "-y", "-i", infile]
        
        if is_video:
            # Note: A simple standard silenceremove filter only cuts audio.
            # To cut BOTH audio and video based on audio silence in ffmpeg is complex and often requires a 2-pass script
            # or uses complex filters and drops async video frames.
            # For this simple "Swiss Army Knife" tool, we use a basic filter approach: (audio silence remove, video syncs to audio using mpdecimate/setpts or similar)
            # However, ffmpeg doesn't have a reliable built-in single command to perfectly cut video according to audio silence.
            # A common workaround for one-line ffmpeg is to drop video frames where audio is silent, but it's very messy.
            # To provide a reliable, single-file drop-in solution without writing a complex Python timestamp parser right now,
            # we will inform the user it works best on Audio, or we use a basic filter that might have slight A/V sync issues on complex cuts.
            # Let's use a robust audio filter and for video, we will rely on a complex filter graph that drops video frames where audio is silent (requires advanced ffmpeg > 4.4).
            
            # Since a robust multi-pass silence cutter for A/V in python would be 100+ lines (like auto-editor),
            # we will implement the simplest native ffmpeg filter:
            # We will use select filter for video based on audio, but ffmpeg does not support this easily.
            # INSTEAD, I will implement a quick pure python logic:
            
            self.log("分析影片靜音中... 這將需要一些時間。")
            
            # Lock UI
            self.btn_run_silence.configure(state="disabled")
            self.btn_stop_silence.configure(state="normal")
            
            threading.Thread(target=self._run_advanced_silence_cut, args=(infile, outfile, self.silence_thresh_var.get(), duration, True), daemon=True).start()
            
        else:
            # Pure Audio is easy
            cmd.extend(["-af", af, outfile])
            # Get Duration for progress bar
            try:
                probe_cmd = [os.path.join(self.tools_dir, "ffprobe.exe"), "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", infile]
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                duration_out = subprocess.check_output(probe_cmd, stderr=subprocess.STDOUT, startupinfo=startupinfo, creationflags=subprocess.CREATE_NO_WINDOW)
                duration = float(duration_out.decode('utf-8').strip())
            except: pass
            self.run_ffmpeg(cmd, "裁剪完成！", duration=duration, out_path=outfile)

    def _run_advanced_silence_cut(self, infile, outfile, thresh, duration_str, is_video):
        # Fallback to FFmpeg silencedetect to gather timestamps, then slice and concat
        try:
             self.after(0, lambda: self.btn_trim.configure(state="disabled") if hasattr(self, 'btn_trim') else None) # generic locking could be better
             self.after(0, lambda: self.update_progress(0, "分析中..."))
             
             # 1. Detect silence
             detect_cmd = [
                 self.ffmpeg_exe, "-i", infile, 
                 "-af", f"silencedetect=noise={thresh}dB:d={duration_str}",
                 "-f", "null", "-"
             ]
             
             startupinfo = subprocess.STARTUPINFO()
             startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
             
             self.log("步驟 1/2: 掃描靜音區間...")
             p = subprocess.Popen(detect_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                        universal_newlines=True, encoding='utf-8', errors='replace', 
                                        startupinfo=startupinfo, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
             self.current_process = p
             
             stdout, stderr = p.communicate()
             output = stderr # silencedetect outputs to stderr
             
             # Check cancellation
             if self.current_process is None or p.returncode != 0:
                 self.after(0, lambda: self.update_progress(0, "⚠️ 分析中斷"))
                 self.current_process = None
                 self.after(0, lambda: self.btn_run_silence.configure(state="normal"))
                 self.after(0, lambda: self.btn_stop_silence.configure(state="disabled"))
                 return
             
             self.current_process = None
                 
             import re
             silence_starts = []
             silence_ends = []
             duration = 0.0
             
             for line in output.split('\n'):
                  if "Duration:" in line:
                       match = re.search(r"Duration: (\d{2}):(\d{2}):(\d{2})\.(\d{2})", line)
                       if match:
                           h, m, s, ms = map(int, match.groups())
                           duration = h * 3600 + m * 60 + s + ms / 100.0
                  elif "silence_start:" in line:
                       silence_starts.append(float(line.split("silence_start: ")[1].split()[0]))
                  elif "silence_end:" in line:
                       silence_ends.append(float(line.split("silence_end: ")[1].split()[0]))
             
             # Ensure pairs match
             if len(silence_starts) > len(silence_ends):
                 silence_ends.append(duration)
                 
             if not silence_starts:
                 self.log("✅ 找不到符合條件的靜音片段。")
                 self.after(0, lambda: self.update_progress(1.0, "完成"))
                 messagebox.showinfo("完成", "影片中沒有符合您設定的靜音片段，無需裁剪。")
                 return
                 
             # Calculate non-silent (keep) chunks
             keep_chunks = []
             current_pos = 0.0
             
             for s, e in zip(silence_starts, silence_ends):
                 if s > current_pos:
                     keep_chunks.append((current_pos, s))
                 current_pos = e
                 
             if current_pos < duration:
                 keep_chunks.append((current_pos, duration))
                 
             if not keep_chunks:
                 self.log("❌ 影片幾乎全為靜音。")
                 self.after(0, lambda: self.update_progress(0, "錯誤"))
                 return
                 
             self.log(f"步驟 2/2: 切割並合併保留的 {len(keep_chunks)} 個片段...")
             
             # 2. Slice and Concat using complex filter
             # For many chunks, building a complex filter graph might hit length limits.
             # If too many chunks (>50), we might need an actual concat file, but complex filter is cleaner for A/V sync
             
             if len(keep_chunks) > 40:
                  self.log("片段過多，使用安全模式處理...")
                  # Create a concat list file
                  list_file_path = os.path.join(self.temp_dir, "concat_list.txt")
                  with open(list_file_path, "w", encoding="utf-8") as f:
                       for i, (start, end) in enumerate(keep_chunks):
                           chunk_path = os.path.join(self.temp_dir, f"chunk_{i}.mp4")
                           
                           # Extract
                           chunk_cmd = [self.ffmpeg_exe, "-y", "-i", infile, "-ss", str(start), "-to", str(end), "-c", "copy", chunk_path]
                           subprocess.run(chunk_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
                           
                           f.write(f"file '{os.path.abspath(chunk_path)}'\n")
                           self.after(0, lambda v=(i/len(keep_chunks))*0.5: self.update_progress(v, "切割中..."))
                           
                  # Concat
                  concat_cmd = [self.ffmpeg_exe, "-y", "-f", "concat", "-safe", "0", "-i", list_file_path, "-c", "copy", outfile]
                  self.run_ffmpeg(concat_cmd, "靜音裁剪完成！")
                  
             else:
                  # Small number of chunks, use filter_complex
                  filter_complex = ""
                  for i, (start, end) in enumerate(keep_chunks):
                      filter_complex += f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}];"
                      filter_complex += f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}];"
                  
                  for i in range(len(keep_chunks)):
                      filter_complex += f"[v{i}][a{i}]"
                      
                  filter_complex += f"concat=n={len(keep_chunks)}:v=1:a=1[outv][outa]"
                  
                  cmd = [
                      self.ffmpeg_exe, "-y", "-i", infile,
                      "-filter_complex", filter_complex,
                      "-map", "[outv]", "-map", "[outa]",
                      outfile
                  ]
                  self.run_ffmpeg(cmd, f"靜音裁剪完成！\n已移除 {len(silence_starts)} 段靜音")
             
        except Exception as e:
             self.log(f"❌ 錯誤: {e}")
             self.after(0, lambda: self.update_progress(0, "錯誤"))
             messagebox.showerror("錯誤", f"裁剪失敗: {e}")
        finally:
              self.current_process = None
              if hasattr(self, 'btn_run_silence'): self.after(0, lambda: self.btn_run_silence.configure(state="normal"))
              if hasattr(self, 'btn_stop_silence'): self.after(0, lambda: self.btn_stop_silence.configure(state="disabled"))

    # --- Helpers ---
    def browse(self, var):
        init_dir = os.path.join(self.script_dir, "Outputs")
        f = filedialog.askopenfilename(initialdir=init_dir)
        if f: var.set(f)

    def browse_multiple(self, var, textbox=None):
        init_dir = os.path.join(self.script_dir, "Outputs")
        files = filedialog.askopenfilenames(initialdir=init_dir)
        if files:
            var.set("|".join(files))
            if textbox:
                textbox.configure(state="normal")
                textbox.delete("1.0", "end")
                textbox.insert("1.0", "\n".join(files))
                textbox.configure(state="disabled")


    # --- Recorder Tab ---
    def setup_record_tab(self, parent):
        # 1. Device Selection
        dev_frame = ctk.CTkFrame(parent, fg_color="transparent")
        dev_frame.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(dev_frame, text="輸入裝置:", font=self.font_ui).pack(side="left")
        self.device_var = ctk.StringVar()
        self.combo_device = ctk.CTkComboBox(dev_frame, variable=self.device_var, width=400, font=("Microsoft JhengHei", 15), dropdown_font=("Microsoft JhengHei", 15))
        self.combo_device.pack(side="left", padx=10)
        
        ctk.CTkButton(dev_frame, text="重新整理", width=100, command=self.refresh_devices, font=self.font_ui).pack(side="left")
        
        # Tip
        tip_text = "💡 提示:\n1. 錄製電腦聲音 (影片): 請選「立體聲混音 (Stereo Mix)」\n2. 錄製人聲 (麥克風): 請選「麥克風 (Microphone)」或「麥克風排列」"
        ctk.CTkLabel(parent, text=tip_text, 
                     text_color="white", font=("Microsoft JhengHei UI", 14, "bold"), justify="left").pack(anchor="w", padx=20)
                     
        # 2. Timer & Status
        # Content Container (Shift Left ~1/4)
        content_frame = ctk.CTkFrame(parent, fg_color="transparent")
        content_frame.pack(anchor="w", padx=100, pady=10)
        
        # 2. Timer & Status
        self.lbl_rec_time = ctk.CTkLabel(content_frame, text="00:00", font=("Consolas", 48, "bold"), text_color="#CFD8DC")
        self.lbl_rec_time.pack(pady=(10, 10))
        
        self.lbl_rec_status = ctk.CTkLabel(content_frame, text="準備就緒", font=self.font_ui, text_color="gray")
        self.lbl_rec_status.pack(pady=(0, 10))
        
        # Waveform Canvas [NEW]
        self.canvas_wave = tk.Canvas(content_frame, width=640, height=120, bg="#1E1E1E", highlightthickness=0)
        self.canvas_wave.pack(pady=10)
        self.wave_data = [0] * 100
        self.current_volume = 0.0
        
        # Denoise Checkbox [NEW]
        self.var_denoise = ctk.BooleanVar(value=True)
        self.chk_denoise = ctk.CTkCheckBox(content_frame, text="啟用 AI 降噪 (Auto Denoise)", variable=self.var_denoise, font=self.font_ui, text_color="#29B6F6")
        self.chk_denoise.pack(pady=(0, 20))
        
        # 3. Controls
        controls_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        controls_frame.pack(pady=10)
        
        self.btn_record = ctk.CTkButton(controls_frame, text="開始錄音", command=self.toggle_record, 
                                        width=180, height=50, font=("Microsoft JhengHei UI", 18, "bold"),
                                        fg_color="#E91E63", hover_color="#C2185B")
        self.btn_record.pack(side="left", padx=5)
        
        self.btn_play_rec = ctk.CTkButton(controls_frame, text="播放錄音", command=self.play_latest_record, 
                                        width=140, height=50, font=("Microsoft JhengHei UI", 16, "bold"),
                                        fg_color="#1E88E5", hover_color="#1565C0", state="disabled")
        self.btn_play_rec.pack(side="left", padx=5)
        
        ctk.CTkButton(controls_frame, text="開啟輸出資料夾", command=lambda: os.startfile(self.output_dir), 
                      width=140, height=50, font=("Microsoft JhengHei UI", 16, "bold"), fg_color="#4CAF50", hover_color="#388E3C", text_color="white").pack(side="left", padx=5)
        
        # 4. Recent File
        self.latest_record_path = None
        self.lbl_rec_file = ctk.CTkLabel(content_frame, text="", font=self.font_ui, text_color="#4CAF50")
        self.lbl_rec_file.pack(pady=5)

        # Hide global progress bar if in this tab (handled by switch_tab later, but let's hide here just in case)
        if hasattr(self, 'progress_bar') and hasattr(self, 'percent_label') and hasattr(self, 'status_label'):
            self.progress_bar.set(0)
            self.percent_label.configure(text="")
            self.status_label.configure(text="就緒")

        # Init Devices
        self.is_recording = False
        self.rec_start_time = 0
        self.after(500, self.refresh_devices) 

    def refresh_devices(self):
        import re
        try:
            input_devs = []
            self.device_map = {} 
            
            # Query devices and APIs
            devices = sd.query_devices()
            default_in = sd.default.device[0]
            hostapis = sd.query_hostapis()
            
            # Map API index to priority (DirectSound > WASAPI > WDM-KS > MME)
            # We explicitly BAN WASAPI and WDM-KS because they cause PyAudio Error -9999 and menu clutter
            # Preference: DirectSound (4) > WASAPI (3) > WDM-KS (2) > MME (1)
            api_priority = {}
            for i, api in enumerate(hostapis):
                name = api['name'].upper()
                if "DIRECTSOUND" in name:
                    api_priority[i] = 4
                elif "WASAPI" in name:
                    api_priority[i] = 3
                elif "WDM" in name or "KS" in name:
                    api_priority[i] = 2
                elif "MME" in name:
                    api_priority[i] = 1
                else:
                    api_priority[i] = 0  # Allow all APIs
            
            # Group by clean name to deduplicate, picking the best API
            best_devices = {}
            
            for i, d in enumerate(devices):
                if d.get('max_input_channels', 0) > 0:
                    try:
                        raw_name = d['name']
                        api_idx = d.get('hostapi', -1)
                        priority = api_priority.get(api_idx, -1)
                        
                        if priority < 0:
                            continue # Skip banned APIs
                            
                        # Clean name: completely remove trailing parentheses to merge duplicates
                        # e.g. "Stereo Mix (Realtek(R) Audio)" -> "Stereo Mix"
                        base_name = re.sub(r"\s*\(.*\)", "", raw_name).strip()
                        if not base_name: base_name = raw_name
                        
                        # Compare and keep the one with higher API priority
                        if base_name not in best_devices or priority > best_devices[base_name]['priority']:
                            # If it's the exact default device from sounddevice, give it a slight boost
                            best_devices[base_name] = {
                                'index': i,
                                'raw_name': raw_name,
                                'priority': priority + (0.5 if i == default_in else 0)
                            }
                    except: pass
            
            # Reconstruct list
            for base_name, info in best_devices.items():
                idx = info['index']
                raw_name = info['raw_name']
                
                display_name = f"{idx}: {raw_name}"
                if idx == default_in:
                    display_name = f"{display_name} (預設)"
                    
                input_devs.append(display_name)
                self.device_map[display_name] = idx
            
            # Sort by device index
            input_devs.sort(key=lambda x: int(x.split(":")[0]))
            
            if input_devs:
                self.combo_device.configure(values=input_devs)
                
                # Default: explicitly prefer Microsoft Sound Mapper > Mic > Stereo Mix
                target_name = None
                mapper_keywords = ["音效對應表", "Sound Mapper"]
                mic_keywords = ["麥克風", "Microphone", "Mic Array", "Mic Input"]
                stereo_keywords = ["Stereo Mix", "立體聲混音"]
                
                # Check Mapper first
                for kw in mapper_keywords:
                    for n in input_devs:
                        if kw.lower() in n.lower():
                            target_name = n; break
                    if target_name: break
                            
                if not target_name:
                    for kw in mic_keywords:
                        for n in input_devs:
                            if kw.lower() in n.lower() and "front" not in n.lower():
                                target_name = n; break
                        if target_name: break
                if not target_name:
                    for kw in stereo_keywords:
                        for n in input_devs:
                            if kw.lower() in n.lower():
                                target_name = n; break
                        if target_name: break
                if not target_name:
                    target_name = next((n for n in input_devs if "(預設)" in n), input_devs[0])
                
                self.combo_device.set(target_name)
            else:
                self.combo_device.configure(values=["找不到輸入裝置"])
                
        except Exception as e:
            print(f"Device Error: {e}")
            self.combo_device.configure(values=["裝置查詢失敗"])

    def toggle_record(self):
        if not self.is_recording:
            # Start
            dev_name = self.device_var.get()
            dev_id = self.device_map.get(dev_name, None)
            
            if dev_id is None:
                messagebox.showerror("錯誤", "請選擇有效的輸入裝置")
                return
                
            save_dir = self.output_dir
            if not os.path.exists(save_dir): os.makedirs(save_dir)
            
            filename = f"rec_{time.strftime('%Y%m%d_%H%M%S')}.wav"
            self.rec_path = os.path.join(save_dir, filename)
            
            self.is_recording = True
            self.btn_record.configure(text="停止錄音", fg_color="#455A64")
            self.lbl_rec_status.configure(text="● 錄音中...", text_color="#FF5252")
            self.lbl_rec_file.configure(text="")
            self.chk_denoise.configure(state="disabled") # Lock check
            self.btn_play_rec.configure(state="disabled") # Lock play button
            self.latest_record_path = None
            
            self.rec_start_time = time.time()
            self.update_record_time()
            
            # Start Waveform animation
            self.wave_data = [0] * 100
            self.current_volume = 0.0
            self.update_waveform()
            
            threading.Thread(target=self._record_thread, args=(dev_id, self.rec_path), daemon=True).start()
            
        else:
            # Stop
            self.is_recording = False
            self.btn_record.configure(text="開始錄音", fg_color="#E91E63")
            self.lbl_rec_status.configure(text="處理中...", text_color="orange")
            self.chk_denoise.configure(state="normal") # Unlock check

    def update_record_time(self):
        if self.is_recording:
            elapsed = int(time.time() - self.rec_start_time)
            mins, secs = divmod(elapsed, 60)
            self.lbl_rec_time.configure(text=f"{mins:02d}:{secs:02d}")
            self.after(500, self.update_record_time)

    def update_waveform(self):
        if not self.is_recording:
            # Clear canvas when stopped
            self.canvas_wave.delete("all")
            h = int(self.canvas_wave.cget("height"))
            w = int(self.canvas_wave.cget("width"))
            self.canvas_wave.create_line(0, h//2, w, h//2, fill="#555555", dash=(2, 2))
            return
            
        # Shift data
        self.wave_data.pop(0)
        
        # Apply smoothing and non-linear scaling to make it look active
        vis_vol = min(self.current_volume * 1.5, 1.0) # Boost visual a bit
        self.wave_data.append(vis_vol)
        
        # Redraw
        self.canvas_wave.delete("all")
        w = int(self.canvas_wave.cget("width"))
        h = int(self.canvas_wave.cget("height"))
        
        # Draw center line
        self.canvas_wave.create_line(0, h//2, w, h//2, fill="#555555", dash=(2, 2))
        
        bar_width = w / len(self.wave_data)
        
        for i, vol in enumerate(self.wave_data):
            bar_h = int(vol * (h // 2) * 0.9)
            x_center = i * bar_width + bar_width/2
            
            if bar_h > 0:
                self.canvas_wave.create_line(x_center, h//2 - bar_h, x_center, h//2 + bar_h, 
                                             fill="#00E676", width=max(1, int(bar_width*0.8)), capstyle="round")
                                             
        self.after(50, self.update_waveform)

    def play_latest_record(self):
        if hasattr(self, 'latest_record_path') and self.latest_record_path and os.path.exists(self.latest_record_path):
            try:
                os.startfile(self.latest_record_path)
            except Exception as e:
                messagebox.showerror("錯誤", f"無法播放檔案: {e}")
        else:
            messagebox.showwarning("提示", "找不到錄音檔案")

    def _record_thread(self, dev_id, path):
        try:
            import sounddevice as sd
            import soundfile as sf
            
            device_info = sd.query_devices(dev_id)
            channels = min(2, device_info['max_input_channels'])
            if channels <= 0: channels = 1
            
            samplerate = int(device_info['default_samplerate'])
            if samplerate <= 0: samplerate = 44100
            
            # Indefinite recording
            with sf.SoundFile(path, mode='w', samplerate=samplerate, channels=channels) as file:
                def callback(indata, frames, time, status):
                    if status:
                        print(status, file=sys.stderr)
                    file.write(indata)
                    if len(indata) > 0:
                        # Extract max absolute amplitude directly
                        # Audio data is typically normalized between -1.0 and 1.0 in float32
                        self.current_volume = float(np.max(np.abs(indata)))
                    
                with sd.InputStream(samplerate=samplerate, device=dev_id, channels=channels, callback=callback):
                    while self.is_recording:
                        time.sleep(0.1)
                        
            self.lbl_rec_status.configure(text="✅ 錄音完成", text_color="green")
            
            # Check Denoise
            if self.var_denoise.get():
                self.lbl_rec_status.configure(text="⏳ 正在進行 AI 降噪...", text_color="#29B6F6")
                
                try:
                    from modules.demucs_runner import DemucsRunner
                    runner = DemucsRunner()
                    # Use standard 'htdemucs' for speed and voice extraction
                    # Use temp_dir instead of output_dir to avoid leaving 'htdemucs' folder in the final output
                    temp_out_base = os.path.join(self.temp_dir, "denoise_work")
                    if not os.path.exists(temp_out_base): os.makedirs(temp_out_base)
                    
                    # Run separation
                    # It returns dict: {'vocals': path, 'drums': path...}
                    res = runner.separate(path, temp_out_base, model_name="htdemucs")
                    
                    if res and 'vocals' in res:
                        vocals_path = res['vocals']
                        
                        # Rename/Move to final output folder as original with suffix
                        base, ext = os.path.splitext(path)
                        denoised_path = f"{base}_denoised{ext}"
                        
                        import shutil
                        if os.path.exists(denoised_path): os.remove(denoised_path) # Overwrite if exists
                        shutil.move(vocals_path, denoised_path)
                        
                        # Cleanup temp work folder
                        try: shutil.rmtree(temp_out_base)
                        except: pass
                        
                        self.lbl_rec_status.configure(text="✨ 錄音與降噪完成！", text_color="#00E676")
                        self.lbl_rec_file.configure(text=f"已儲存: {os.path.basename(denoised_path)}")
                        
                        self.latest_record_path = os.path.abspath(denoised_path)
                        self.after(0, lambda: self.btn_play_rec.configure(state="normal"))
                        
                        # Copy denoised path
                        if self.master:
                            self.master.clipboard_clear()
                            self.master.clipboard_append(os.path.abspath(denoised_path))
                            self.master.update()
                            return # Done
                    else:
                        self.lbl_rec_status.configure(text="⚠️ 降噪失敗 (保留原檔)", text_color="orange")
                        
                except Exception as e:
                    print(f"Denoise Error: {e}")
                    self.lbl_rec_status.configure(text=f"⚠️ 降噪錯誤: {e}", text_color="red")
            
            self.lbl_rec_file.configure(text=f"已儲存: {os.path.basename(path)} (路徑已複製)")
            
            self.latest_record_path = os.path.abspath(path)
            self.after(0, lambda: self.btn_play_rec.configure(state="normal"))
            
            # Copy original path if denoise skipped or failed
            if self.master:
                self.master.clipboard_clear()
                self.master.clipboard_append(os.path.abspath(path))
                self.master.update()
            
        except Exception as e:
            self.is_recording = False
            err_msg = str(e)
            if "-9999" in err_msg and ("MME error 1" in err_msg or "-2147467259" in err_msg):
                self.lbl_rec_status.configure(text=f"❌ 錯誤: 被系統拒絕存取。請至 Windows [設定] > [隱私權] > [麥克風]\n確認已開啟「允許傳統型應用程式存取您的麥克風」。", text_color="red")
            else:
                self.lbl_rec_status.configure(text=f"❌ 錯誤: {err_msg}", text_color="red")
            print(f"Rec Error: {e}")
            self.btn_record.configure(text="🔴 開始錄音", fg_color="#D32F2F")

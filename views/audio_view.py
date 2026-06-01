import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import sys
import time
import shutil
import subprocess
import traceback
import torch
import torchaudio
import numpy as np
import soundfile as sf
import requests

# Demucs Imports - Lazy load to speed up app start if needed
# But for now we import at top-level
try:
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
except ImportError:
    pass # Handle missing dependencies gracefully

class AudioView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        # Paths
        self.script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.output_dir = os.path.join(self.script_dir, "Outputs", "Vocals") # Unified Output Path
        self.tools_dir = os.path.join(self.script_dir, "tools")
        self.models_dir = os.path.join(self.script_dir, "models", "Demucs")
        
        # Ensure directories
        for d in [self.output_dir, self.tools_dir, self.models_dir]:
            if not os.path.exists(d): os.makedirs(d)
            
        os.environ["TORCH_HOME"] = self.models_dir # Force Demucs to download models here

        # State
        self.file_list = []
        self.is_processing = False
        self.model_map = {
            "htdemucs V4 (標準版 - 速度快)": "htdemucs",
            "htdemucs_ft (精修版 - 音質細)": "htdemucs_ft",
            "mdx_extra (MDX-Net V3 - 最佳音質 HQ)": "mdx_extra"
        }
        
        # UI Setup
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1) # File list expands
        
        self.setup_ui()
        self.check_gpu()

    def check_gpu(self):
        try:
            from utils.gpu_utils import safe_check_cuda
            cuda_ok, info = safe_check_cuda()
            if cuda_ok:
                self.gpu_label.configure(text=f"GPU: {info} (CUDA)", text_color=("#2E7D32", "#00E676"))
                self.device = "cuda"
            else:
                self.gpu_label.configure(text=f"GPU: {info} (使用 CPU mode)", text_color="#FF5252")
                self.device = "cpu"
        except Exception:
            self.gpu_label.configure(text="GPU: 偵測失敗 (使用 CPU mode)", text_color="gray")
            self.device = "cpu"

    def setup_ui(self):
        font_title = ("Microsoft JhengHei UI", 20, "bold") # Larger title
        font_label = ("Microsoft JhengHei UI", 15)
        font_option = ("Microsoft JhengHei UI", 15) # Larger for options
        font_btn = ("Microsoft JhengHei UI", 15)
        
        # --- Header ---
        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, pady=(15, 5), padx=20, sticky="ew")
        
        # Title removed based on feedback
        
        self.gpu_label = ctk.CTkLabel(self.header_frame, text="檢查 GPU...", text_color="gray", font=font_label)
        self.gpu_label.pack(side="left")

        # --- Controls Section ---
        self.controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.controls_frame.grid(row=1, column=0, pady=(0, 10), padx=20, sticky="ew")
        
        # Row 1: Model Selection & Checkboxes
        self.controls_row1 = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        self.controls_row1.pack(side="top", fill="x", pady=(0, 10))
        
        # Row 2: Volume Sliders
        self.controls_row2 = ctk.CTkFrame(self.controls_frame, fg_color="transparent")
        self.controls_row2.pack(side="top", fill="x")
        
        # Model Selection
        ctk.CTkLabel(self.controls_row1, text="AI 模型:", font=font_option).pack(side="left", padx=(0, 5))
        self.model_var = ctk.StringVar(value="htdemucs V4 (標準版 - 速度快)")
        self.model_menu = ctk.CTkComboBox(self.controls_row1, values=list(self.model_map.keys()), variable=self.model_var, width=360, font=font_option, dropdown_font=font_option)
        self.model_menu.pack(side="left", padx=5)

        # Options - Save Dry Vocals 
        self.save_dry_var = ctk.BooleanVar(value=True)
        self.chk_save_dry = ctk.CTkCheckBox(self.controls_row1, text="另存乾淨人聲 (WAV)", variable=self.save_dry_var, font=font_label)
        self.chk_save_dry.pack(side="left", padx=(20, 10))
        
        # --- [NEW] De-Reverb Checkbox ---
        self.dereverb_var = ctk.BooleanVar(value=False)
        self.chk_dereverb = ctk.CTkCheckBox(self.controls_row1, text="啟用去回音過濾 (專為模型訓練設計)", variable=self.dereverb_var, font=font_label)
        self.chk_dereverb.pack(side="left", padx=(0, 10))
        # --------------------------------
        
        # Accompaniment Mode (Quick Preset)
        self.acc_mode_var = ctk.BooleanVar(value=True) # Default Enable
        self.chk_acc_mode = ctk.CTkCheckBox(
            self.controls_row1, 
            text="純伴奏模式", 
            variable=self.acc_mode_var, 
            font=font_option,
            command=self.toggle_acc_mode
        )
        self.chk_acc_mode.pack(side="left", padx=(0, 10))

        # Volume Sliders with Numbers (Moved to Row 2)
        # Vocal
        vol_frame = ctk.CTkFrame(self.controls_row2, fg_color="transparent")
        vol_frame.pack(side="left", padx=0)
        
        ctk.CTkLabel(vol_frame, text="人聲音量調整:", font=font_label).pack(side="left", padx=(0, 5))
        self.vol_vocal = ctk.DoubleVar(value=0.0) # Default 0.0
        self.slider_vocal = ctk.CTkSlider(vol_frame, variable=self.vol_vocal, from_=0, to=2, width=150, command=self.update_vol_labels)
        self.slider_vocal.pack(side="left", padx=5)
        self.lbl_vocal_val = ctk.CTkLabel(vol_frame, text="0.0", width=30, font=font_label)
        self.lbl_vocal_val.pack(side="left")
        
        # Backing (Accompaniment)
        ctk.CTkLabel(vol_frame, text="伴奏音量調整:", font=font_label).pack(side="left", padx=(20, 5))
        self.vol_bg = ctk.DoubleVar(value=0.5) # Default 0.5
        self.slider_bg = ctk.CTkSlider(vol_frame, variable=self.vol_bg, from_=0, to=2, width=150, command=self.update_vol_labels)
        self.slider_bg.pack(side="left", padx=5)
        self.lbl_bg_val = ctk.CTkLabel(vol_frame, text="0.5", width=30, font=font_label)
        self.lbl_bg_val.pack(side="left")
        
        # Options (Removed from here)
        # self.save_dry_var ... (Moved up)

        # --- File List (Weight: Smaller) ---
        self.list_frame = ctk.CTkFrame(self)
        self.list_frame.grid(row=2, column=0, padx=20, pady=5, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)
        self.list_frame.grid_rowconfigure(0, weight=1)
        
        # Custom Listbox utilizing CTkScrollableFrame
        self.scroll_list = ctk.CTkScrollableFrame(self.list_frame, fg_color="transparent", height=120)
        self.scroll_list.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        self.no_file_label = ctk.CTkLabel(self.scroll_list, text="請拖曳檔案至此或點擊「加入檔案」", text_color="gray", font=font_label)
        self.no_file_label.pack(pady=30) 

        # Buttons below list
        self.btn_frame = ctk.CTkFrame(self.list_frame, fg_color="transparent")
        self.btn_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        
        self.btn_add = ctk.CTkButton(self.btn_frame, text="加入檔案", command=self.add_files, fg_color="#3949AB", font=font_btn)
        self.btn_add.pack(side="left", padx=5)
        
        self.btn_clear = ctk.CTkButton(self.btn_frame, text="清空列表", command=self.clear_files, fg_color="#424242", width=80, font=font_btn)
        self.btn_clear.pack(side="left", padx=5)
        
        self.btn_process = ctk.CTkButton(self.btn_frame, text="開始處理", command=self.start_processing_thread, 
                                         fg_color="#E91E63", hover_color="#C2185B", font=("Microsoft JhengHei UI", 15, "bold"), width=200)
        self.btn_process.pack(side="right", padx=5)
        
        self.btn_stop_process = ctk.CTkButton(self.btn_frame, text="中斷", command=self.stop_processing, 
                                         fg_color="#D32F2F", hover_color="#B71C1C", font=("Microsoft JhengHei UI", 15, "bold"), width=100, state="disabled")
        self.btn_stop_process.pack(side="right", padx=5)

        # --- Status & Log (Weight: Larger) ---
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=3, column=0, padx=20, pady=(5, 20), sticky="nsew") 
        self.log_frame.grid_rowconfigure(1, weight=1) # Fix: Expand LogBox (Row 1), not Button (Row 2)
        self.log_frame.grid_columnconfigure(0, weight=1)
        
        # Configure Grid Rows for Main Frame to split (File List < Log)
        # Row 2 (List) gets weight 1, Row 3 (Log) gets weight 10 (Force Log to be larger)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=10) 
        
        # Status Layout Container
        self.status_frame = ctk.CTkFrame(self.log_frame, fg_color="transparent")
        self.status_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        # Progress Bar on Top
        self.progress_bar = ctk.CTkProgressBar(self.status_frame, height=10, progress_color="#ffa000")
        self.progress_bar.pack(fill="x", padx=10, pady=(10, 5))
        self.progress_bar.set(0)
        
        # Labels Below
        self.status_label = ctk.CTkLabel(self.status_frame, text="準備就緒", font=("Microsoft JhengHei UI", 15))
        self.status_label.pack(side="left", padx=10, pady=(0, 5))
        
        self.lbl_progress = ctk.CTkLabel(self.status_frame, text="0%", font=("Microsoft JhengHei UI", 15), text_color="#ffa000")
        self.lbl_progress.pack(side="right", padx=10, pady=(0, 5))
        
        self.log_box = ctk.CTkTextbox(self.log_frame, font=("Microsoft JhengHei UI", 15), fg_color=("gray95", "#000000"), text_color=("gray10", "gray90"))
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.log_box.configure(state="disabled")
        
        open_btn = ctk.CTkButton(self.log_frame, text="開啟輸出資料夾", command=self.open_output_folder, height=25, width=120, font=font_btn, fg_color="#4CAF50", hover_color="#388E3C", text_color="white")
        open_btn.grid(row=2, column=0, sticky="e", padx=10, pady=10)

    def toggle_acc_mode(self):
        if self.acc_mode_var.get():
            self.vol_vocal.set(0.0)
            self.vol_bg.set(1.0) # Set to normal max or boosted default? 1.0 is safe.
        else:
            # Optional: Restore defaults? Or just leave it? 
            # Usually user wants to toggle back to "normal".
            self.vol_vocal.set(1.0)
            self.vol_bg.set(1.0)
        self.update_vol_labels()

    def update_vol_labels(self, _=None):
        self.lbl_vocal_val.configure(text=f"{self.vol_vocal.get():.1f}")
        self.lbl_bg_val.configure(text=f"{self.vol_bg.get():.1f}")

    # --- Utilities ---
    def log(self, message):
        self.after(0, self._log_safe, message)

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

    def _log_safe(self, message):
        timestamp = time.strftime("[%H:%M:%S]")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{timestamp} > {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def get_ffmpeg_path(self):
        tools_path = os.path.join(self.tools_dir, "ffmpeg.exe")
        return tools_path if os.path.exists(tools_path) else "ffmpeg"

    def open_output_folder(self):
        os.startfile(os.path.abspath(self.output_dir))

    # --- File Management ---
    def add_files(self):
        # Default to Outputs/Downloads as requested
        # self.output_dir is .../Outputs/Vocals, so we go up one level
        download_dir = os.path.join(os.path.dirname(self.output_dir), "Downloads")
        if not os.path.exists(download_dir):
            try: os.makedirs(download_dir)
            except: pass
            
        files = filedialog.askopenfilenames(
            initialdir=download_dir,
            filetypes=[("Media Files", "*.mp4 *.mp3 *.wav *.m4a *.flac *.avi *.mov *.mkv")]
        )
        if files:
            self.no_file_label.pack_forget()
            for f in files:
                if f not in self.file_list:
                    self.file_list.append(f)
                    # Add simple label to scroll_list
                    # USER REQUEST: Font 15pt, smaller padding
                    lbl = ctk.CTkLabel(self.scroll_list, text=os.path.basename(f), anchor="w", font=("Microsoft JhengHei UI", 15))
                    lbl.pack(fill="x", padx=5, pady=2) # Reduced pady from default (usually 5 or implicit)

    def clear_files(self):
        self.file_list = []
        for widget in self.scroll_list.winfo_children():
            if widget != self.no_file_label:
                widget.destroy()
        self.no_file_label.pack(pady=50)

    # --- Processing Logic ---
    def start_processing_thread(self):
        if not self.file_list:
            messagebox.showwarning("提示", "請先加入檔案")
            return
            
        files_to_process = list(self.file_list) # Copy List
        self.clear_files() # Clear List Immediately
        
        self.is_processing = True
        self.stop_requested = False
        
        self.btn_process.configure(state="disabled")
        self.btn_stop_process.configure(state="normal") # Enable Stop
        self.btn_add.configure(state="disabled")
        self.btn_clear.configure(state="disabled")
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        
        threading.Thread(target=self.run_process, args=(files_to_process,), daemon=True).start()

    def update_progress(self, val):
        self.progress_bar.set(val)
        self.lbl_progress.configure(text=f"{int(val*100)}%")

    def stop_processing(self):
        if not self.is_processing: return
        
        self.stop_requested = True
        self.log("🛑 正在停止任務...")
        self.btn_stop_process.configure(state="disabled")
        
        # Kill FFmpeg process if running
        if hasattr(self, 'current_process') and self.current_process:
             try:
                 self.current_process.terminate()
                 self.log("... 已中斷 FFmpeg 處理")
             except: pass

    def run_process(self, files):
        try:
            total_files = len(files)
            self.log(f"系統準備開始處理 {total_files} 個檔案...")
            self.log(f"載入 Demucs 模型... ({self.device})")
            
            from demucs.pretrained import get_model
            from demucs.apply import apply_model
            
            model_key = self.model_map[self.model_var.get()]
            model = get_model(model_key)
            try:
                model.to(self.device)
            except (RuntimeError, Exception) as e:
                err_str = str(e).lower()
                cuda_keywords = ["cuda", "no kernel image", "out of memory", "driver", "insufficient", "cublas", "cudnn"]
                if self.device == "cuda" and any(kw in err_str for kw in cuda_keywords):
                    self.log(f"⚠️ GPU 載入失敗 ({e})，自動切換至 CPU 模式...")
                    self.device = "cpu"
                    self.gpu_label.configure(text="GPU: 載入失敗 (使用 CPU)", text_color="orange")
                    try:
                        from utils.gpu_utils import safe_cuda_empty_cache
                        safe_cuda_empty_cache()
                    except: pass
                    model = get_model(model_key)  # Re-load fresh
                    model.to("cpu")
                else:
                    raise e
            self.log("模型載入完成")
            
            # Identify suffix based on model (USER REQUEST: Match UI option names)
            model_suffix = ""
            if model_key == "htdemucs": model_suffix = "_V4"
            elif model_key == "htdemucs_ft": model_suffix = "_ft"
            elif model_key == "mdx_extra": model_suffix = "_extra"
            else:
                if "htdemucs" in model_key: model_suffix = "_ht"
                elif "mdx" in model_key: model_suffix = "_mdx"
            
            ffmpeg_exe = self.get_ffmpeg_path()
            total = total_files
            
            self.after(0, lambda: self.progress_bar.stop())
            self.after(0, lambda: self.progress_bar.configure(mode="determinate"))
            
            for idx, file_path in enumerate(files):
                if self.stop_requested:
                    self.log("🛑 任務已由使用者終止")
                    break

                self.log(f"正在處理 ({idx+1}/{total}): {os.path.basename(file_path)}")
                self.after(0, lambda v=(idx / total): self.update_progress(v))
                
                try:
                    self.process_single_file(file_path, model, ffmpeg_exe, model_suffix)
                except Exception as e:
                    self.log(f"處理失敗 {os.path.basename(file_path)}: {e}")
                    traceback.print_exc()
            
            if not self.stop_requested:
                self.after(0, lambda: self.update_progress(1.0))
                self.log("所有任務完成！")
                messagebox.showinfo("完成", "所有檔案處理完成！")
            
        except Exception as e:
            self.log(f"系統錯誤: {e}")
            messagebox.showerror("錯誤", f"執行失敗: {e}")
        finally:
            self.is_processing = False
            self.after(0, self.reset_ui)

    def reset_ui(self):
        self.btn_process.configure(state="normal")
        self.btn_stop_process.configure(state="disabled")
        self.btn_add.configure(state="normal")
        self.btn_clear.configure(state="normal")
        self.progress_bar.set(0)

    def process_single_file(self, input_path, model, ffmpeg_exe, model_suffix=""):
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        temp_wav = os.path.join(self.output_dir, "temp_source.wav")
        
        # 1. Extract Audio to WAV using FFmpeg
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        cmd = [
            ffmpeg_exe, "-y", "-i", input_path, 
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2", 
            temp_wav
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
        
        # 2. Load Audio (use soundfile to avoid torchaudio 2.10's torchcodec dependency)
        wav_np, sr = sf.read(temp_wav, dtype='float32', always_2d=True)
        wav = torch.from_numpy(wav_np.T)  # (channels, samples)
        
        # Resample if needed
        if sr != 44100:
            import julius
            wav = julius.resample_frac(wav, sr, 44100)
            sr = 44100
            
        # Normalize
        ref = wav.mean(0)
        wav = (wav - ref.mean()) / ref.std()
        wav = wav.unsqueeze(0) # Batch dim

        # 3. Apply Demucs with OOM Fallback
        # sources shape: (batch, sources, channels, time)
        try:
            # Try on GPU first if available
            if self.device == "cuda":
                 self.log(f"嘗試使用 GPU 加速: {os.path.basename(input_path)}")
                 wav_gpu = wav.to("cuda")
                 # Check if we need to release cache from previous runs
                 from utils.gpu_utils import safe_cuda_empty_cache
                 safe_cuda_empty_cache()
                 sources = apply_model(model, wav_gpu, shifts=1, split=True, overlap=0.25, progress=True)
                 del wav_gpu
            else:
                 raise RuntimeError("CPU Mode") # Force CPU path

        except RuntimeError as e:
            err_str = str(e).lower()
            # Catch OOM, Manual CPU Mode, and ALL CUDA errors (driver, kernel, library issues)
            cuda_keywords = ["out of memory", "cpu mode", "cuda error", "no kernel image",
                             "cuda driver", "insufficient", "cublas", "cudnn", "cuda_error",
                             "not compiled", "cuda runtime", "cusolver", "cufft"]
            if any(kw in err_str for kw in cuda_keywords):
                
                if "out of memory" in err_str:
                    self.log("⚠️ 顯卡記憶體不足 (OOM)，正在清除快取並切換至 CPU 模式...")
                elif "no kernel image" in err_str or "cuda error" in err_str:
                    self.log("⚠️ 偵測到顯卡相容性問題 (可能是顯卡太新或驅動問題)，已自動切換至 CPU 模式...")
                
                # 1. Aggressive Cleanup (Wrapped to prevent crash during cleanup)
                try:
                    if 'wav_gpu' in locals(): del wav_gpu
                    del model # Release the GPU model
                    import gc
                    gc.collect()
                    from utils.gpu_utils import safe_cuda_empty_cache
                    safe_cuda_empty_cache()
                except Exception as cleanup_err:
                    print(f"Cleanup warning: {cleanup_err}")
                
                # 2. Clear Demucs Internal Cache to force fresh load
                try:
                     # Demucs caches loaded models in demucs.pretrained._models
                     from demucs.pretrained import _models
                     model_key = self.model_map[self.model_var.get()]
                     if model_key in _models:
                         print(f"Clearing {model_key} from demucs cache")
                         del _models[model_key]
                except Exception as clean_err:
                    print(f"Cache clear warning: {clean_err}")

                # 3. Permanently switch to CPU for this session/batch to avoid ping-pong OOM
                # self.device = "cpu" # Optional: Uncomment to force CPU for subsequent files too
                
                self.log("🔄 重新載入模型 (CPU)...")
                
                # 4. Reload Model on CPU
                model_key = self.model_map[self.model_var.get()]
                model = get_model(model_key)
                model.to("cpu")
                
                # 5. Run on CPU
                sources = apply_model(model, wav, shifts=1, split=True, overlap=0.25, progress=True)
                
                if self.device == "cuda":
                     self.log("ℹ️ 為確保穩定，後續任務將維持 CPU 模式。")
            else:
                raise e

        vocal_tensor = sources[0, 3]
        bg_tensor = sources[0, 0] + sources[0, 1] + sources[0, 2]
        
        vocal_data = vocal_tensor.cpu().numpy().T
        bg_data = bg_tensor.cpu().numpy().T
        
        # 4. Save Dry Vocal (Optional)
        if self.save_dry_var.get():
            if getattr(self, "dereverb_var", None) and self.dereverb_var.get():
                # 4.1 Save temp raw vocal
                temp_voc_path = os.path.join(self.output_dir, f"temp_{base_name}_vocal.wav")
                max_v = np.max(np.abs(vocal_data))
                norm_vocal = vocal_data / max_v * 0.9 if max_v > 0 else vocal_data
                sf.write(temp_voc_path, norm_vocal, 44100, subtype='PCM_16')
                
                self.log("啟動第二重過濾 (VR De-Reverb 去回音)...")
                try:
                    from audio_separator.separator import Separator
                    import logging
                    
                    # Add detailed file logging for audio-separator debugging
                    logger = logging.getLogger('audio_separator')
                    logger.setLevel(logging.DEBUG)
                    fh = logging.FileHandler(os.path.join(self.output_dir, 'audio_separator_debug_log.txt'), encoding='utf-8')
                    fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
                    logger.addHandler(fh)
                    
                    # Add local tools dir to PATH so audio-separator finds our ffmpeg
                    original_path = os.environ.get("PATH", "")
                    if self.tools_dir not in original_path:
                        os.environ["PATH"] = self.tools_dir + os.pathsep + original_path
                        
                    # Setup audio-separator
                    sep = Separator(
                        output_dir=self.output_dir, 
                        output_format="WAV"
                    )
                    # Use standard UVR5 VR De-Reverb model. Auto-downloads if missing.
                    sep.load_model(model_filename='5_HP-Karaoke-UVR.pth') 
                    
                    self.log(f"正在分析並抽空房間混響 (約需 1~3 分鐘)...")
                    result_files = sep.separate(temp_voc_path)
                    self.log(f"去回音完成，產生的檔案: {result_files}")
                    
                    final_dry_path = None
                    for f in result_files:
                        # audio-separator might use different suffixes depending on model metadata
                        # Usually it's "(Vocals)" or "(Instrumental)". We want the vocals part.
                        # For VR Architecture, it might be `_(Vocals)`
                        if "(Vocals)" in f or "_Vocals" in f or "vocals" in f.lower():
                            final_dry_path = os.path.join(self.output_dir, f)
                            
                    # Fallback: if we didn't find specific 'vocals' tag but we have exactly 2 files,
                    # one is usually vocals, one is instrumental. If we only have 1 (rare for this model), use it.
                    if not final_dry_path and result_files and len(result_files) > 0:
                         # Just guess the first one if the naming convention drastically changed
                         self.log("⚠️ 找不到帶有 (Vocals) 標記的輸出檔，嘗試使用第一個分離檔案...")
                         final_dry_path = os.path.join(self.output_dir, result_files[0])
                            
                    # Rename to standard _Vocal_Dry.wav
                    user_dry_path = os.path.join(self.output_dir, f"{base_name}_Vocal_Dry{model_suffix}.wav")
                    user_dry_path = self.get_unique_path(user_dry_path)
                    
                    if final_dry_path and os.path.exists(final_dry_path):
                        os.rename(final_dry_path, user_dry_path)
                        self.log(f"✅ 已成功儲存去回音純人聲: {os.path.basename(user_dry_path)}")
                    else:
                        raise Exception(f"去回音輸出檔案遺失，無法重命名 (預期路徑: {final_dry_path})")
                        
                    # Cleanup
                    if os.path.exists(temp_voc_path): os.remove(temp_voc_path)
                    for f in result_files:
                        p = os.path.join(self.output_dir, f)
                        if os.path.exists(p): os.remove(p)
                        
                except ImportError as e:
                    import traceback
                    err_msg = traceback.format_exc()
                    with open(os.path.join(self.output_dir, "audio_separator_error_traceback.txt"), "w", encoding="utf-8") as f:
                        f.write(err_msg)
                    self.log(f"⚠️ 啟動失敗: 尚未安裝 audio-separator 或其依賴套件 (ImportError: {e})，將輸出一般人聲。已將詳細錯誤寫入 audio_separator_error_traceback.txt")
                    dry_path = os.path.join(self.output_dir, f"{base_name}_Vocal{model_suffix}.wav")
                    if os.path.exists(temp_voc_path): os.rename(temp_voc_path, dry_path)
                except Exception as e:
                    import traceback
                    err_msg = traceback.format_exc()
                    with open(os.path.join(self.output_dir, "audio_separator_error_traceback.txt"), "w", encoding="utf-8") as f:
                        f.write(err_msg)
                    self.log(f"⚠️ 去回音運算失敗 (Exception: {e})，回退輸出一般人聲。已將詳細錯誤寫入 audio_separator_error_traceback.txt")
                    dry_path = os.path.join(self.output_dir, f"{base_name}_Vocal{model_suffix}.wav")
                    if os.path.exists(temp_voc_path): os.rename(temp_voc_path, dry_path)
            else:
                dry_path = os.path.join(self.output_dir, f"{base_name}_Vocal{model_suffix}.wav")
                dry_path = self.get_unique_path(dry_path)
                max_v = np.max(np.abs(vocal_data))
                norm_vocal = vocal_data / max_v * 0.9 if max_v > 0 else vocal_data
                sf.write(dry_path, norm_vocal, 44100, subtype='PCM_16')
                self.log(f"已儲存人聲: {os.path.basename(dry_path)}")

        # 5. Mix and Save
        # Apply Volumes
        mixed_data = (bg_data * self.vol_bg.get()) + (vocal_data * self.vol_vocal.get())
        mixed_data = np.clip(mixed_data, -1.0, 1.0)
        
        temp_parsed = os.path.join(self.output_dir, "temp_mixed.wav")
        sf.write(temp_parsed, mixed_data, 44100)
        
        # 6. Merge with Video (if video) or Save Audio
        ext = os.path.splitext(input_path)[1].lower()
        duration = len(mixed_data) / 44100.0 # Duration in seconds

        import re # Local import for safety
        
        if ext in ['.mp4', '.avi', '.mov', '.mkv']:
            final_out = os.path.join(self.output_dir, f"{base_name}_Karaoke{model_suffix}.mp4")
            final_out = self.get_unique_path(final_out)
            self.log(f"正在合成影片 (這可能需要幾分鐘)...")
            
            # Uses ultrafast/crf 28 for preview-like speed
            cmd_merge = [
                ffmpeg_exe, "-y",
                "-i", input_path,
                "-i", temp_parsed,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-c:a", "aac",
                "-shortest",
                final_out
            ]
            
            self.current_process = subprocess.Popen(
                cmd_merge, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                encoding='utf-8',
                startupinfo=startupinfo
            )
            
            for line in self.current_process.stdout:
                if "time=" in line:
                    match = re.search(r"time=(\d{2}:\d{2}:\d{2}\.\d+)", line)
                    if match and duration > 0:
                        t_str = match.group(1)
                        try:
                            h, m, s = map(float, t_str.split(':'))
                            curr_sec = h*3600 + m*60 + s
                            progress = curr_sec / duration
                            if progress > 1.0: progress = 1.0
                            self.after(0, lambda p=progress: self.update_progress(p))
                        except: pass
            
            self.current_process.wait()
            if self.current_process.returncode != 0:
                 self.log("❌ 影片合成失敗")
                 
        else:
            final_out = os.path.join(self.output_dir, f"{base_name}_Karaoke{model_suffix}{ext}")
            final_out = self.get_unique_path(final_out)
            cmd_merge = [ffmpeg_exe, "-y", "-i", temp_parsed, final_out]
            subprocess.run(cmd_merge, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
            
        self.log(f"已建立檔案: {os.path.basename(final_out)}")
        
        # Cleanup
        if os.path.exists(temp_wav): os.remove(temp_wav)
        if os.path.exists(temp_parsed): os.remove(temp_parsed)

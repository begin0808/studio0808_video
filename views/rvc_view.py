import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import sys
import time
import subprocess
import traceback
import shutil
import torch
import librosa
import soundfile as sf

class RVCView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        # Paths
        self.script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.models_dir = os.path.join(self.script_dir, "models", "RVC")
        self.output_dir = os.path.join(self.script_dir, "Outputs", "RVC")
        self.temp_dir = os.path.join(self.script_dir, "temp")
        
        for d in [self.models_dir, self.output_dir, self.temp_dir]:
            if not os.path.exists(d): os.makedirs(d)

        # Fonts
        self.font_title = ("Microsoft JhengHei UI", 24, "bold")
        self.font_header = ("Microsoft JhengHei UI", 20, "bold") # Section Headers
        self.font_ui = ("Microsoft JhengHei UI", 15)            # Labels/Buttons (Requested 15px)
        self.font_small = ("Microsoft JhengHei UI", 12)

        # UI Variables
        self.file_path_var = ctk.StringVar()
        self.pth_var = ctk.StringVar()
        self.index_var = ctk.StringVar()
        self.pitch_var = ctk.IntVar(value=0)
        self.f0_method_var = ctk.StringVar(value="rmvpe")
        self.index_rate_var = ctk.DoubleVar(value=0.75)
        self.filter_radius_var = ctk.IntVar(value=3)
        self.rms_mix_var = ctk.DoubleVar(value=0.25)
        self.auto_mix_var = ctk.BooleanVar(value=False)
        self.source_shift_var = ctk.IntVar(value=0)
        self.is_processing = False

        # UI Layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        
        self.create_header()
        self.create_main_content()
        self.create_footer()
        self.check_gpu()
        
    def check_gpu(self):
        try:
            from utils.gpu_utils import safe_check_cuda
            cuda_ok, info = safe_check_cuda()
            if cuda_ok:
                self.gpu_label.configure(text=f"GPU: {info} (CUDA)", text_color=("#2E7D32", "#00E676"))
            else:
                self.gpu_label.configure(text=f"GPU: {info} (使用 CPU mode)", text_color="#FF5252")
        except Exception:
            self.gpu_label.configure(text="GPU: 偵測失敗", text_color="gray")
        
    def create_header(self):
        header = ctk.CTkFrame(self, height=60, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(5, 5))
        
        # Title removed based on feedback
        
        self.gpu_label = ctk.CTkLabel(header, text="檢查 GPU...", text_color="gray", font=self.font_ui)
        self.gpu_label.pack(side="left")

    def create_main_content(self):
        self.scroll_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.scroll_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        self.scroll_frame.grid_columnconfigure(0, weight=1)
        
        # 1. Input Audio
        self.create_section("1. 輸入音訊", 0, "#42A5F5") # Blue
        
        input_frame = ctk.CTkFrame(self.scroll_frame)
        input_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        
        self.entry_file = ctk.CTkEntry(input_frame, textvariable=self.file_path_var, placeholder_text="請選擇音訊檔案 (.wav, .mp3)...", width=400, font=self.font_ui)
        self.entry_file.pack(side="left", padx=10, pady=10, expand=True, fill="x")
        
        ctk.CTkButton(input_frame, text="加入檔案", command=self.browse_file, width=80, font=self.font_ui, fg_color="#3949AB").pack(side="left", padx=10)
        
        shift_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        shift_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))
        
        ctk.CTkLabel(shift_frame, text="原音升降 Key (Source Shift):", font=self.font_ui).pack(side="left", padx=(10, 5))
        self.slider_source_shift = ctk.CTkSlider(shift_frame, from_=-24, to=24, number_of_steps=48, variable=self.source_shift_var, width=150)
        self.slider_source_shift.pack(side="left", padx=5)
        self.lbl_source_shift_val = ctk.CTkLabel(shift_frame, text="0", width=30, font=self.font_ui)
        self.lbl_source_shift_val.pack(side="left")
        
        def _update_shift(v): self.lbl_source_shift_val.configure(text=f"{int(v)}")
        self.slider_source_shift.configure(command=_update_shift)
        
        ctk.CTkLabel(shift_frame, text="(轉換前先處理原音，有助於解決男女互轉破音)", text_color="gray", font=self.font_ui).pack(side="left", padx=10)

        ctk.CTkCheckBox(self.scroll_frame, text="自動分離人聲與混音 (Auto-Mix) - 需輸入完整歌曲", 
                        variable=self.auto_mix_var, font=self.font_ui, text_color="#FFB74D").grid(row=3, column=0, sticky="w", padx=30, pady=(0, 10))

        # 2. Model
        self.create_section("2. 模型選擇", 4, "#66BB6A") # Green
        
        model_frame_grid = ctk.CTkFrame(self.scroll_frame)
        model_frame_grid.grid(row=5, column=0, sticky="ew", padx=10, pady=5)
        
        ctk.CTkLabel(model_frame_grid, text="模型權重 (.pth):", font=self.font_ui).grid(row=0, column=0, padx=5, sticky="w")
        self.entry_pth = ctk.CTkEntry(model_frame_grid, textvariable=self.pth_var, height=35, width=500, font=self.font_ui)
        self.entry_pth.grid(row=0, column=1, padx=5, sticky="ew")
        ctk.CTkButton(model_frame_grid, text="選擇模型", width=100, height=35, command=self.browse_model, font=self.font_ui).grid(row=0, column=2, padx=5)
        
        ctk.CTkLabel(model_frame_grid, text="特徵索引 (.index):", font=self.font_ui).grid(row=1, column=0, padx=5, sticky="w", pady=10)
        self.entry_index = ctk.CTkEntry(model_frame_grid, textvariable=self.index_var, height=35, width=500, font=self.font_ui, placeholder_text="(選填 / Optional)")
        self.entry_index.grid(row=1, column=1, padx=5, sticky="ew", pady=10)
        ctk.CTkButton(model_frame_grid, text="選擇索引", width=100, height=35, command=self.browse_index, font=self.font_ui).grid(row=1, column=2, padx=5, pady=10)
        
        model_frame_grid.grid_columnconfigure(1, weight=1)

        # 3. Parameters
        self.create_section("3. 轉換參數", 6, "#FFA726") # Orange
        
        param_frame = ctk.CTkFrame(self.scroll_frame)
        param_frame.grid(row=7, column=0, sticky="ew", padx=10, pady=5)
        
        # Grid layout for params
        # Pitch
        ctk.CTkLabel(param_frame, text="變調 (Pitch):", font=self.font_ui).grid(row=0, column=0, padx=10, pady=5, sticky="w")
        
        pitch_ctrl = ctk.CTkFrame(param_frame, fg_color="transparent")
        pitch_ctrl.grid(row=0, column=1, sticky="w")
        
        # Pitch Slider (-24 to 24)
        self.slider_pitch = ctk.CTkSlider(pitch_ctrl, from_=-24, to=24, number_of_steps=48, variable=self.pitch_var, width=200)
        self.slider_pitch.pack(side="left")
        ctk.CTkLabel(pitch_ctrl, textvariable=self.pitch_var, width=40, font=self.font_ui).pack(side="left", padx=5)
        ctk.CTkLabel(pitch_ctrl, text="(男轉女+12, 女轉男-12)", text_color="gray", font=self.font_ui).pack(side="left", padx=10)

        # F0 Method
        ctk.CTkLabel(param_frame, text="F0 預測算法:", font=self.font_ui).grid(row=1, column=0, padx=10, pady=5, sticky="w")
        ctk.CTkComboBox(param_frame, variable=self.f0_method_var, values=["fcpe", "rmvpe", "crepe", "pm", "harvest"], font=self.font_ui, dropdown_font=self.font_ui).grid(row=1, column=1, sticky="w", padx=0)
        
        # Index Rate
        ctk.CTkLabel(param_frame, text="索引率 (Index Rate):", font=self.font_ui).grid(row=2, column=0, padx=10, pady=5, sticky="w")
        
        ir_frame = ctk.CTkFrame(param_frame, fg_color="transparent")
        ir_frame.grid(row=2, column=1, sticky="ew")
        self.slider_ir = ctk.CTkSlider(ir_frame, from_=0, to=1, number_of_steps=20, variable=self.index_rate_var, width=200, command=self.update_ir_label)
        self.slider_ir.pack(side="left")
        self.label_ir = ctk.CTkLabel(ir_frame, text="0.75", width=40, font=self.font_ui)
        self.label_ir.pack(side="left", padx=5)
        
        # Post-process
        ctk.CTkLabel(param_frame, text="後處理:", font=self.font_ui).grid(row=3, column=0, padx=10, pady=5, sticky="w")
        
        fr_frame = ctk.CTkFrame(param_frame, fg_color="transparent")
        fr_frame.grid(row=3, column=1, sticky="ew")
        self.slider_fr = ctk.CTkSlider(fr_frame, from_=0, to=7, number_of_steps=7, variable=self.filter_radius_var, width=200)
        self.slider_fr.pack(side="left")
        ctk.CTkLabel(fr_frame, textvariable=self.filter_radius_var, width=40, font=self.font_ui).pack(side="left", padx=5)
        
        ctk.CTkCheckBox(param_frame, text="混音響度包絡 (Volume Envelope)", variable=self.rms_mix_var, onvalue=0.25, offvalue=0, font=self.font_ui).grid(row=3, column=2, padx=10)

        self.refresh_models()

    def create_section(self, title, row, color="#FFFFFF"):
        label = ctk.CTkLabel(self.scroll_frame, text=title, font=self.font_header, anchor="w", text_color=color)
        label.grid(row=row, column=0, sticky="ew", padx=10, pady=(5, 0))
        
    def create_footer(self):
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=20, pady=(5, 10))
        
        # Progress UI
        self.progress_frame = ctk.CTkFrame(footer, fg_color="transparent")
        self.progress_frame.pack(fill="x", pady=(0, 10))
        
        self.rvc_progress = ctk.CTkProgressBar(self.progress_frame, height=10, progress_color="#ffa000", mode="indeterminate")
        self.rvc_progress.pack(fill="x", side="left", expand=True, padx=(0, 10))
        self.rvc_progress.set(0)
        
        # self.percent_label = ctk.CTkLabel(self.progress_frame, text="0%", font=self.font_ui, text_color="#ffa000")
        # self.percent_label.pack(side="right", padx=5)

        # Status & Button
        self.status_label = ctk.CTkLabel(footer, text="", font=self.font_ui)
        self.status_label.pack(side="top", pady=5)
        
        btn_frame = ctk.CTkFrame(footer, fg_color="transparent")
        btn_frame.pack(side="bottom", fill="x", padx=20, pady=(5, 10))
        
        self.btn_run = ctk.CTkButton(btn_frame, text="開始轉換", command=self.start_inference, 
                                     height=50, width=200, font=("Microsoft JhengHei UI", 16, "bold"), fg_color="#E91E63", hover_color="#C2185B")
        self.btn_run.pack(side="left", padx=(0, 10))
        
        self.btn_stop = ctk.CTkButton(btn_frame, text="中斷", command=self.stop_inference,
                                      height=50, width=100, font=("Microsoft JhengHei UI", 16, "bold"), fg_color="#D32F2F", hover_color="#B71C1C", state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 10))

        self.btn_open_folder = ctk.CTkButton(btn_frame, text="開啟輸出資料夾", command=self.open_output_folder,
                                             height=50, width=140, font=("Microsoft JhengHei UI", 16, "bold"), fg_color="#4CAF50", hover_color="#388E3C", text_color="white")
        self.btn_open_folder.pack(side="left")

    # --- Logic ---

    def open_output_folder(self):
        if os.path.exists(self.output_dir):
            if os.name == 'nt':
                os.startfile(self.output_dir)
        else:
            messagebox.showinfo("提示", "目前還沒有輸出檔案！")

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

    # --- Logic ---

    def update_ir_label(self, value):
        self.label_ir.configure(text=f"{value:.2f}")

    def browse_file(self):
        # Default to D:\Studio0808_Video\Outputs\Vocals
        # Assuming current script is roughly in root or views/, we need path to Outputs/Vocals relative to project root
        # In __init__, self.output_dir = Outputs/RVC
        # We want Outputs/Vocals
        
        # Calculate Outputs/Vocals
        # self.output_dir is usually project/Outputs/RVC/
        # So parent of it is Outputs/
        
        outputs_dir = os.path.dirname(self.output_dir)
        vocals_dir = os.path.join(outputs_dir, "Vocals") if os.path.exists(outputs_dir) else "/"
        
        if not os.path.exists(vocals_dir):
            try:
                os.makedirs(vocals_dir, exist_ok=True)
            except: 
                vocals_dir = "/" # Fallback
                
        f = filedialog.askopenfilename(filetypes=[("Audio", "*.wav *.mp3 *.flac *.m4a")], initialdir=vocals_dir)
        if f: self.file_path_var.set(f)

    def browse_model(self):
        # Open in models/RVC by default but allow anywhere
        initial = self.models_dir if os.path.exists(self.models_dir) else "/"
        f = filedialog.askopenfilename(filetypes=[("RVC Model", "*.pth")], initialdir=initial)
        if f: 
            self.pth_var.set(f)
            # Auto-guess index if possible? User said remove auto-match button, but maybe implicit is okay?
            # User said: "萬一資料夾裡面很多... 比較好選擇", implies manual control.
            # I will NOT auto-match index to respect "manual control".

    def browse_index(self):
        initial = self.models_dir if os.path.exists(self.models_dir) else "/"
        f = filedialog.askopenfilename(filetypes=[("RVC Index", "*.index")], initialdir=initial)
        if f: 
            self.index_var.set(f)

    def refresh_models(self):
        # Optional: Set a default model if none selected and one exists in default dir?
        # Maybe just leave it empty to force user to choose.
        pass
        
    def on_model_change(self, choice):
        pass
        
    def auto_match_index(self):
        pass
        
    def update_progress(self, val, msg=None):
        # Indeterminate mode: Don't set value during process, only message if provided
        if not self.is_processing and val is not None:
             self.rvc_progress.set(val)
        if msg: self.status_label.configure(text=msg)

    def start_inference(self):
        if self.is_processing: return
        
        input_file = self.file_path_var.get()
        pth_file = self.pth_var.get()
        
        if not input_file or not os.path.exists(input_file):
            return messagebox.showerror("錯誤", "找不到輸入檔案")
        if not pth_file:
            return messagebox.showerror("錯誤", "請先選擇有效的 RVC 模型 (.pth)")
            
        self.is_processing = True
        self.btn_run.configure(state="disabled", text="處理中...")
        self.btn_stop.configure(state="normal")
        self.status_label.configure(text="正在準備環境...")
        
        self.rvc_progress.configure(mode="indeterminate")
        self.rvc_progress.start() # Start animation
        
        self.current_process = None # Reset process handle
        threading.Thread(target=self.run_rvc_thread, daemon=True).start()

    def stop_inference(self):
        if self.current_process and self.current_process.poll() is None:
            self.current_process.terminate()
            self.rvc_progress.stop()
            self.rvc_progress.configure(mode="determinate")
            self.rvc_progress.set(0)
            self.status_label.configure(text="已中斷 (使用者操作)")
            self.is_processing = False
        
    def run_rvc_thread(self):
        try:
            # Prepare paths
            pth_input = self.pth_var.get()
            if os.path.exists(pth_input):
                pth_path = pth_input
            else:
                pth_path = os.path.join(self.models_dir, pth_input)
            
            index_input = self.index_var.get()
            if not index_input or "無索引" in index_input or index_input.strip() == "":
                index_path = None
            elif os.path.exists(index_input):
                 index_path = index_input
            else:
                 index_path = os.path.join(self.models_dir, index_input)

            # --- Auto-Mix Logic ---
            original_input = self.file_path_var.get()
            rvc_input = original_input
            inst_path = None
            stem_dir = None
            is_auto_mix = self.auto_mix_var.get()
            
            if is_auto_mix:
                self.after(0, lambda: self.update_progress(None, "正在分離人聲與伴奏 (Demucs)..."))
                self.rvc_progress.configure(mode="indeterminate")
                self.rvc_progress.start()
                
                # Import DemucsRunner dynamically
                sys.path.append(os.path.join(self.script_dir, "modules"))
                from modules.demucs_runner import DemucsRunner
                
                demucs = DemucsRunner(os.path.join(self.script_dir, "models", "Demucs"))
                stem_dir = os.path.join(self.temp_dir, f"stems_{int(time.time())}")
                if not os.path.exists(stem_dir): os.makedirs(stem_dir)
                
                # Separate
                stems = demucs.separate(original_input, stem_dir, model_name="htdemucs")
                
                # Cleanup Demucs
                del demucs
                import gc
                gc.collect()
                
                if not stems or "vocals" not in stems or "no_vocals" not in stems:
                     raise Exception("人聲分離失敗，無法進行自動混音。")
                
                rvc_input = stems["vocals"]
                inst_path = stems["no_vocals"]
                self.after(0, lambda: self.update_progress(None, "分離完成，準備進行變音/變聲..."))
            
            # --- Source Pitch Shift Logic ---
            shift_steps = self.source_shift_var.get()
            if shift_steps != 0:
                self.after(0, lambda: self.update_progress(None, f"正在調整原音升降 Key ({shift_steps} 個半音)..."))
                try:
                    y, sr = librosa.load(rvc_input, sr=None)
                    y_shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=shift_steps)
                    
                    shifted_path = os.path.join(self.temp_dir, f"shifted_{int(time.time())}.wav")
                    sf.write(shifted_path, y_shifted, sr)
                    
                    rvc_input = shifted_path
                    self.after(0, lambda: self.update_progress(None, "原音變調完成，準備進行變聲..."))
                    
                    # Cleanup
                    import gc
                    del y, y_shifted
                    gc.collect()
                except Exception as e:
                    self.after(0, lambda: self.update_progress(None, f"原音升降 Key 失敗，將使用原音繼續: {e}"))
                    print(f"Pitch shift error: {e}")

            # Extract model name for filename
            model_name = os.path.splitext(os.path.basename(pth_input))[0]
            
            output_name = f"{os.path.splitext(os.path.basename(original_input))[0]}_RVC_{model_name}.wav"
            output_path = os.path.join(self.output_dir, output_name)
            output_path = self.get_unique_path(output_path)
            
            rvc_output_path = output_path 
            if is_auto_mix:
                rvc_output_path = os.path.join(stem_dir, f"rvc_vocals.wav")
            
            rvc_cli = os.path.join(self.script_dir, "modules", "rvc_cli.py")
            
            # Determine base executable and arguments
            if getattr(sys, 'frozen', False):
                # In frozen EXE, we call ourselves with the --rvc_cli flag
                base_cmd = [sys.executable, "--rvc_cli"]
            else:
                # In development, we call the script directly
                base_cmd = [sys.executable, rvc_cli]

            cmd = base_cmd + [
                "--model", pth_path,
                "--input", rvc_input,
                "--output", rvc_output_path,
                "--pitch", str(self.pitch_var.get()),
                "--f0", self.f0_method_var.get(),
                "--index_rate", str(self.index_rate_var.get()),
                "--filter_radius", str(self.filter_radius_var.get()),
                "--rms_mix_rate", str(self.rms_mix_var.get()),
                "--protect", "0.33" 
            ]
            if index_path and os.path.exists(index_path):
                cmd.extend(["--index", index_path])
                
            # Check if CLI exists
            if not os.path.exists(rvc_cli):
                # Fallback: Explain missing backend
                raise FileNotFoundError(f"找不到 RVC 核心模組 modules/rvc_cli.py")
            
            print(f"[DEBUG] Executing RVC: {cmd}")
            # Ensure CWD is set to modules/ so that relative paths in RVC config work
            cwd_path = os.path.join(self.script_dir, "modules")
            self.current_process = subprocess.Popen(cmd, cwd=cwd_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                    universal_newlines=True, encoding='utf-8', errors='replace')
            
            proc = self.current_process
            
            # Progress Logic based on CLI output
            logs = []
            for line in proc.stdout:
                line = line.strip()
                if not line: continue
                # print(f"[RVC CLI]: {line}") # Debug print
                logs.append(line)
                if len(logs) > 20: logs.pop(0) # Keep last 20 lines
                
                # Check messages
                msg = ""
                if "Initializing" in line: msg = "正在初始化環境..."
                elif "Loading Hubert" in line: msg = "正在載入核心模型 (需耗時)..."
                elif "Loading VC Pipeline" in line: msg = "正在載入 AI 管道..."
                elif "Loading rmvpe model" in line: msg = "正在載入聲調預測模型..."
                elif "Loading Model" in line: msg = "正在載入變聲模型..."
                elif "Transforming audio" in line: msg = "正在進行變聲轉換 (請耐心等候)..."
                elif "Saving to" in line: msg = "正在儲存檔案..."
                elif "Success." in line: msg = "轉換成功！"
                
                if msg: self.after(0, lambda m=msg: self.update_progress(None, m))
                
                # Removed overwrite with raw logs to keep Chinese messages visible
            
            proc.wait()
            self.rvc_progress.stop() # Stop animation
            
            if proc.returncode == 0:
                # Auto-Mix Mixing Step
                if is_auto_mix and inst_path and os.path.exists(rvc_output_path):
                      self.after(0, lambda: self.update_progress(None, "變聲完成，正在合成伴奏..."))
                      
                      ffmpeg_exe = "ffmpeg"
                      tools_ffmpeg = os.path.join(self.script_dir, "tools", "ffmpeg.exe")
                      if os.path.exists(tools_ffmpeg): ffmpeg_exe = tools_ffmpeg
                      
                      # Mix: rvc_output (vocals) + inst_path (bgm)
                      mix_cmd = [
                          ffmpeg_exe, "-y",
                          "-i", rvc_output_path,
                          "-i", inst_path,
                          "-filter_complex", "amix=inputs=2:duration=longest",
                          output_path
                      ]
                      subprocess.run(mix_cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                      
                      try: shutil.rmtree(stem_dir)
                      except: pass

                self.rvc_progress.configure(mode="determinate")
                self.rvc_progress.set(1) # Show full bar
                self.after(0, lambda: self.update_progress(1.0, "處理完成"))
                messagebox.showinfo("完成", f"轉換成功！\n檔案已儲存至: {output_path}")
                # Open folder and highlight the file
                if os.name == 'nt':
                     subprocess.Popen(f'explorer /select,"{output_path}"')
            elif proc.returncode != 0 and self.is_processing: # is_processing flag might still be true if it was an error
                 # If we manually terminated, verify if we want to show error or just ignore
                 # Detect if it was a real error or just a kill (checking return code alone might be enough if we set a flag)
                 full_log = "\n".join(logs)
                 print(f"[RVC ERROR] Return Code: {proc.returncode}")
                 print(f"[RVC ERROR] Log: {full_log}")
                 raise Exception(f"RVC CLI Failed (Code {proc.returncode}):\n{full_log}")

        except Exception as e:
            self.rvc_progress.stop()
            self.rvc_progress.configure(mode="determinate")
            self.rvc_progress.set(0)
            
            # If the user stopped the process manually, don't show error dialog
            if not self.is_processing:
                 pass 
            else:
                traceback.print_exc()
                self.after(0, lambda: self.update_progress(0, "錯誤"))
                messagebox.showerror("轉換失敗", f"發生錯誤: {str(e)}")
        finally:
            self.is_processing = False
            self.current_process = None
            if self.btn_run.winfo_exists():
                self.after(0, lambda: self.btn_run.configure(state="normal", text="開始轉換"))
                self.after(0, lambda: self.btn_stop.configure(state="disabled"))
                self.after(0, lambda: self.status_label.configure(text=""))
                self.after(0, lambda: self.rvc_progress.stop())

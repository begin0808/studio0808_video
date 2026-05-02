import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import sys
import threading
import sounddevice as sd
import numpy as np
import torch
import gc

class RealTimeVCView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        
        # Paths
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.root_dir = os.path.dirname(self.script_dir) # Go up from views/
        self.models_dir = os.path.join(self.root_dir, "models")
        
        # Engine
        sys.path.append(os.path.join(self.root_dir, "modules"))
        from modules.realtime_rvc_engine import RealTimeRVCEngine
        self.engine = RealTimeRVCEngine()
        
        # Fonts
        self.font_title = ("Microsoft JhengHei UI", 24, "bold")
        self.font_ui = ("Microsoft JhengHei UI", 16)
        self.font_small = ("Microsoft JhengHei UI", 12)
        
        # Variables
        self.input_device_var = ctk.StringVar()
        self.output_device_var = ctk.StringVar()
        self.input_devices = []
        self.output_devices = []
        
        self.pth_path_var = ctk.StringVar()
        self.index_path_var = ctk.StringVar()
        
        self.gain_input_var = ctk.DoubleVar(value=1.0)
        self.gain_output_var = ctk.DoubleVar(value=1.0)
        self.pitch_var = ctk.DoubleVar(value=0)
        self.threshold_var = ctk.DoubleVar(value=-40)
        self.release_var = ctk.DoubleVar(value=0.0) # VAD Hangover delay (0.0=instant cut to prevent echo)
        self.chunk_var = ctk.DoubleVar(value=0.3) # Default to 0.3s for Blackwell stability
        
        self.is_running = False
        
        self.create_ui()
        self.refresh_devices()
        self.check_gpu()
        
    def check_gpu(self):
        try:
            from utils.gpu_utils import safe_check_cuda
            cuda_ok, info = safe_check_cuda()
            if cuda_ok:
                self.gpu_label.configure(text=f"GPU: {info} (CUDA)", text_color="#00E676")
            else:
                self.gpu_label.configure(text=f"GPU: {info} (使用 CPU mode)", text_color="#FF5252")
        except Exception:
            self.gpu_label.configure(text="GPU: 偵測失敗", text_color="gray")
        
    def create_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(5, 5))
        # Title removed based on feedback
        
        self.gpu_label = ctk.CTkLabel(header, text="檢查 GPU...", text_color="gray", font=self.font_ui)
        self.gpu_label.pack(side="left")
        
        # Main Frame (No longer Scrollable)
        self.scroll = ctk.CTkFrame(self, fg_color="transparent")
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
        self.scroll.grid_columnconfigure(0, weight=1)
        
        # 1. Device Selection
        self.add_section("1. 裝置選擇", 0, "#42A5F5")
        dev_frame = ctk.CTkFrame(self.scroll)
        dev_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        
        ctk.CTkLabel(dev_frame, text="輸入裝置 (Mic):", font=self.font_ui, width=160, anchor="w").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.combo_input = ctk.CTkComboBox(dev_frame, variable=self.input_device_var, width=400, font=("Microsoft JhengHei UI", 15), dropdown_font=("Microsoft JhengHei UI", 15))
        self.combo_input.grid(row=0, column=1, padx=10, sticky="w")
        
        ctk.CTkLabel(dev_frame, text="輸出裝置 (Speaker):", font=self.font_ui, width=160, anchor="w").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.combo_output = ctk.CTkComboBox(dev_frame, variable=self.output_device_var, width=400, font=("Microsoft JhengHei UI", 15), dropdown_font=("Microsoft JhengHei UI", 15))
        self.combo_output.grid(row=1, column=1, padx=10, sticky="w")
        
        ctk.CTkButton(dev_frame, text="重新掃描", command=self.refresh_devices, width=100, font=self.font_ui).grid(row=0, column=2, padx=10, sticky="w")
        
        # 2. Model Selection
        self.add_section("2. 模型選擇", 2, "#66BB6A")
        model_frame = ctk.CTkFrame(self.scroll)
        model_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
        
        ctk.CTkLabel(model_frame, text="模型 (.pth):", font=self.font_ui, width=160, anchor="w").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        ctk.CTkEntry(model_frame, textvariable=self.pth_path_var, width=400, font=self.font_ui).grid(row=0, column=1, padx=10, sticky="w")
        ctk.CTkButton(model_frame, text="加入檔案", command=self.browse_pth, width=80, font=self.font_ui, fg_color="#3949AB").grid(row=0, column=2, padx=10, sticky="w")
        
        ctk.CTkLabel(model_frame, text="索引 (.index):", font=self.font_ui, width=160, anchor="w").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        ctk.CTkEntry(model_frame, textvariable=self.index_path_var, width=400, font=self.font_ui, placeholder_text="選填").grid(row=1, column=1, padx=10, sticky="w")
        ctk.CTkButton(model_frame, text="加入檔案", command=self.browse_index, width=80, font=self.font_ui, fg_color="#3949AB").grid(row=1, column=2, padx=10, sticky="w")
        
        # 3. Controls
        self.add_section("3. 參數控制", 4, "#FFA726")
        ctrl_frame = ctk.CTkFrame(self.scroll)
        ctrl_frame.grid(row=5, column=0, sticky="ew", padx=10, pady=5)
        
        # Configure grid weights for 2-column layout (Compact)
        ctrl_frame.columnconfigure(1, weight=0)
        ctrl_frame.columnconfigure(3, weight=0, minsize=40) # Spacer
        ctrl_frame.columnconfigure(5, weight=0)
        ctrl_frame.columnconfigure(7, weight=1) # Push to left
        
        # Row 0: Pitch | Gain
        # Shorten slider width (remove sticky=ew, add width)
        ctk.CTkLabel(ctrl_frame, text="變調 (Pitch):", font=self.font_ui, width=160, anchor="w").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        slider_pitch = ctk.CTkSlider(ctrl_frame, from_=-24, to=24, number_of_steps=48, variable=self.pitch_var, command=self.update_params, width=140)
        slider_pitch.grid(row=0, column=1, padx=5, sticky="w")
        self.lbl_pitch = ctk.CTkLabel(ctrl_frame, text=f"{self.pitch_var.get():.0f}", font=self.font_ui, width=35)
        self.lbl_pitch.grid(row=0, column=2, sticky="w")
        
        ctk.CTkLabel(ctrl_frame, text="輸入增益 (Gain):", font=self.font_ui).grid(row=0, column=4, padx=5, pady=10, sticky="w")
        ctk.CTkSlider(ctrl_frame, from_=0, to=5, variable=self.gain_input_var, command=self.update_params, width=140).grid(row=0, column=5, padx=5, sticky="w")
        self.lbl_gain = ctk.CTkLabel(ctrl_frame, text=f"{self.gain_input_var.get():.1f}", font=self.font_ui, width=35)
        self.lbl_gain.grid(row=0, column=6, sticky="w")
        
        # Row 1: Threshold | Chunk
        ctk.CTkLabel(ctrl_frame, text="靜音閥值 (dB):", font=self.font_ui, width=160, anchor="w").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        ctk.CTkSlider(ctrl_frame, from_=-60, to=0, number_of_steps=60, variable=self.threshold_var, command=self.update_params, width=140).grid(row=1, column=1, padx=5, sticky="w")
        self.lbl_threshold = ctk.CTkLabel(ctrl_frame, text=f"{self.threshold_var.get():.0f}", font=self.font_ui, width=35)
        self.lbl_threshold.grid(row=1, column=2, sticky="w")
        
        ctk.CTkLabel(ctrl_frame, text="延遲 (Sec):", font=self.font_ui).grid(row=1, column=4, padx=5, pady=10, sticky="w")
        self.slider_chunk = ctk.CTkSlider(ctrl_frame, from_=0.1, to=2.0, number_of_steps=19, variable=self.chunk_var, command=self.update_params, width=140)
        self.slider_chunk.grid(row=1, column=5, padx=5, sticky="w")
        self.lbl_chunk = ctk.CTkLabel(ctrl_frame, text=f"{self.chunk_var.get():.1f}", font=self.font_ui, width=35)
        self.lbl_chunk.grid(row=1, column=6, sticky="w")
        
        # Row 2: Release Time | RNNoise
        ctk.CTkLabel(ctrl_frame, text="釋放時間 (Rel):", font=self.font_ui, width=160, anchor="w").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        ctk.CTkSlider(ctrl_frame, from_=0, to=2.0, number_of_steps=20, variable=self.release_var, command=self.update_params, width=140).grid(row=2, column=1, padx=5, sticky="w")
        self.lbl_release = ctk.CTkLabel(ctrl_frame, text=f"{self.release_var.get():.1f}s", font=self.font_ui, width=35)
        self.lbl_release.grid(row=2, column=2, sticky="w")
        
        # RNNoise Checkbox
        self.rnnoise_var = ctk.BooleanVar(value=False)
        self.chk_rnnoise = ctk.CTkCheckBox(ctrl_frame, text="AI 降噪 (RNNoise)", variable=self.rnnoise_var, command=self.update_params, font=self.font_ui, text_color="#00E676")
        self.chk_rnnoise.grid(row=2, column=4, columnspan=3, padx=5, pady=10, sticky="w")
        
        # Row 3: F0 Method | (Explain)
        font_algo = ("Microsoft JhengHei UI", 15)
        ctk.CTkLabel(ctrl_frame, text="演算法:", font=self.font_ui, width=160, anchor="w").grid(row=3, column=0, padx=10, pady=10, sticky="w")
        self.combo_f0 = ctk.CTkComboBox(ctrl_frame, values=["fcpe", "rmvpe", "pm"], state="readonly", command=self.update_params, 
                                        font=font_algo, dropdown_font=font_algo, width=140)
        self.combo_f0.grid(row=3, column=1, padx=5, sticky="w")
        self.combo_f0.set("fcpe")
        
        
        
        # Footer
        footer = ctk.CTkFrame(self, height=70, fg_color="#2b2b2b")
        footer.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        
        # We want everything in one row on the left
        # Recording Checkbox
        self.record_var = ctk.BooleanVar(value=False)
        self.chk_record = ctk.CTkCheckBox(footer, text="同步錄製變聲結果 (儲存為 WAV)", variable=self.record_var, font=self.font_ui, text_color="#00E676")
        self.chk_record.pack(side="left", padx=(20, 15), pady=15)
        
        self.btn_run = ctk.CTkButton(footer, text="開始變聲", command=self.toggle_conversion, 
                                     width=140, height=45, font=("Microsoft JhengHei UI", 16, "bold"), fg_color="#E91E63", hover_color="#C2185B")
        self.btn_run.pack(side="left", padx=5, pady=10)
        
        self.btn_open = ctk.CTkButton(footer, text="開啟輸出資料夾", command=self.open_output_folder, 
                                     width=140, height=45, font=("Microsoft JhengHei UI", 16, "bold"), fg_color="#4CAF50", hover_color="#388E3C", text_color="white")
        self.btn_open.pack(side="left", padx=5, pady=10)
        
        self.status_label = ctk.CTkLabel(footer, text="準備就緒", font=("Microsoft JhengHei UI", 16, "bold"), text_color="#FF9800")
        self.status_label.pack(side="left", padx=(15, 0), pady=15)

    def add_section(self, text, row, color):
        lbl = ctk.CTkLabel(self.scroll, text=text, font=("Microsoft JhengHei UI", 18, "bold"), text_color=color)
        lbl.grid(row=row, column=0, sticky="w", padx=10, pady=(5, 5))

    def refresh_devices(self):
        try:
            devices = sd.query_devices()
            hostapis = sd.query_hostapis()
            
            # Map API index to priority (DirectSound > WASAPI > WDM-KS > MME)
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

            import re
            
            # Process Input Devices
            best_in = {}
            for i, d in enumerate(devices):
                if d.get('max_input_channels', 0) > 0:
                    api_idx = d.get('hostapi', -1)
                    priority = api_priority.get(api_idx, 0)
                    if priority < 0: continue
                        
                    raw_name = d['name']
                    base_name = re.sub(r"\s*\(.*\)", "", raw_name).strip()
                    if not base_name: base_name = raw_name
                    
                    if base_name not in best_in or priority > best_in[base_name]['priority']:
                        best_in[base_name] = {'index': i, 'raw_name': raw_name, 'priority': priority}

            self.input_devices = [f"{info['index']}: {info['raw_name']}" for info in sorted(best_in.values(), key=lambda x: x['index'])]
            
            # Process Output Devices
            best_out = {}
            for i, d in enumerate(devices):
                if d.get('max_output_channels', 0) > 0:
                    api_idx = d.get('hostapi', -1)
                    priority = api_priority.get(api_idx, -1)
                    if priority < 0: continue
                        
                    raw_name = d['name']
                    base_name = re.sub(r"\s*\(.*\)", "", raw_name).strip()
                    if not base_name: base_name = raw_name
                    
                    if base_name not in best_out or priority > best_out[base_name]['priority']:
                        best_out[base_name] = {'index': i, 'raw_name': raw_name, 'priority': priority}

            self.output_devices = [f"{info['index']}: {info['raw_name']}" for info in sorted(best_out.values(), key=lambda x: x['index'])]
            
            # Fallbacks if list is empty
            if not self.input_devices: self.input_devices = ["未偵測到輸入裝置"]
            if not self.output_devices: self.output_devices = ["未偵測到輸出裝置"]
            
            self.combo_input.configure(values=self.input_devices)
            self.combo_output.configure(values=self.output_devices)
            
            # Smart default selection: 優先選「音效對應表」，若無再選「麥克風」裝置
            current_in = self.input_device_var.get()
            if current_in and current_in in self.input_devices:
                pass
            else:
                default_in = self.input_devices[0] if self.input_devices else ""
                mapper_keywords = ["音效對應表", "sound mapper"]
                mic_keywords = ["麥克風", "microphone", "mic"]
                
                found = False
                for kw in mapper_keywords:
                    for dev in self.input_devices:
                        if kw in dev.lower():
                            default_in = dev
                            found = True
                            break
                    if found: break
                
                if not found:
                    for dev in self.input_devices:
                        dev_lower = dev.lower()
                        if "front" in dev_lower:
                            continue
                        if any(kw in dev_lower for kw in mic_keywords):
                            default_in = dev
                            break
                            
                self.combo_input.set(default_in)
                
            current_out = self.output_device_var.get()
            if current_out and current_out in self.output_devices:
                pass 
            elif self.output_devices:
                self.combo_output.set(self.output_devices[0])
                
        except Exception as e:
            self.combo_input.configure(values=["裝置讀取失敗"])
            self.combo_output.configure(values=["裝置讀取失敗"])
            self.combo_input.set("裝置讀取失敗")
            self.combo_output.set("裝置讀取失敗")
            print(f"Device error: {e}")

    def browse_pth(self):
        f = filedialog.askopenfilename(filetypes=[("RVC Model", "*.pth")], initialdir=self.models_dir)
        if f: self.pth_path_var.set(f)

    def browse_index(self):
        f = filedialog.askopenfilename(filetypes=[("RVC Index", "*.index")], initialdir=self.models_dir)
        if f: self.index_path_var.set(f)

    def update_params(self, _=None):
        if self.engine:
            self.engine.pitch = self.pitch_var.get()
            self.engine.input_gain = self.gain_input_var.get()
            self.engine.threshold = self.threshold_var.get()
            self.engine.silence_delay = self.release_var.get()
            if hasattr(self, 'combo_f0'):
                self.engine.f0_method = self.combo_f0.get()
            if hasattr(self, 'rnnoise_var'):
                self.engine.use_rnnoise = self.rnnoise_var.get()
        
        # Update Labels
        if hasattr(self, 'lbl_pitch'): self.lbl_pitch.configure(text=f"{self.pitch_var.get():.0f}")
        if hasattr(self, 'lbl_gain'): self.lbl_gain.configure(text=f"{self.gain_input_var.get():.1f}")
        if hasattr(self, 'lbl_threshold'): self.lbl_threshold.configure(text=f"{self.threshold_var.get():.1f}")
        if hasattr(self, 'lbl_chunk'): self.lbl_chunk.configure(text=f"{self.chunk_var.get():.1f}")
        if hasattr(self, 'lbl_release'): self.lbl_release.configure(text=f"{self.release_var.get():.1f}s")

    def toggle_conversion(self):
        if not self.is_running:
            # Start
            pth = self.pth_path_var.get()
            if not os.path.exists(pth):
                messagebox.showerror("Error", "請選擇有效的模型檔案 (.pth)")
                return
            
            # Lock UI
            self.btn_run.configure(state="disabled", text="啟動中...")
            self.status_label.configure(text="正在載入模型...", text_color="yellow")
            self.update_idletasks()
            
            def _start_logic():
                success = self.engine.load_model(pth, self.index_path_var.get())
                if not success:
                    self.status_label.configure(text="模型載入失敗", text_color="red")
                    self.btn_run.configure(state="normal", text="開始變聲")
                    return
                
                # Get Device Indices
                try:
                    in_idx = int(self.input_device_var.get().split(":")[0])
                    out_idx = int(self.output_device_var.get().split(":")[0])
                except:
                    messagebox.showerror("Error", "請選擇有效的輸入與輸出裝置")
                    self.btn_run.configure(state="normal", text="開始變聲")
                    return
                
                # Setup Output Dir for Recording
                output_dir = os.path.join(self.root_dir, "Outputs", "RVC")
                record_audio = self.record_var.get()
                
                # Start Engine
                try:
                    self.engine.start(in_idx, out_idx, chunk_duration=self.chunk_var.get(), record_audio=record_audio, output_dir=output_dir)
                    self.is_running = True
                    self.btn_run.configure(state="normal", text="停止變聲", fg_color="#F44336")
                    self.status_label.configure(text="正在運行變聲...", text_color="#66BB6A")
                except Exception as e:
                    messagebox.showerror("Error", f"引擎啟動失敗:\n{e}")
                    self.btn_run.configure(state="normal", text="開始變聲")
                    self.status_label.configure(text="啟動失敗", text_color="red")
            
            # Run in thread to prevent UI freezing during model load
            threading.Thread(target=_start_logic, daemon=True).start()
            
        else:
            # Stop
            self.btn_run.configure(state="disabled", text="停止中...")
            self.update_idletasks()
            
            def _stop_logic():
                saved_path = self.engine.stop()
                self.is_running = False
                self.btn_run.configure(state="normal", text="開始變聲", fg_color="#E91E63")
                if saved_path:
                    self.status_label.configure(text=f"已儲存錄音: {os.path.basename(saved_path)}", text_color="#4CAF50")
                else:
                    self.status_label.configure(text="已停止", text_color="gray")
            
            threading.Thread(target=_stop_logic, daemon=True).start()

    def on_leave(self):
        try:
            if self.is_running:
                self.engine.stop()
                self.is_running = False
                self.btn_run.configure(text="開始變聲", fg_color="#E91E63")
                self.status_label.configure(text="已停止", text_color="gray")
                
            # Deep release resources
            if hasattr(self, 'engine'):
                self.engine.model = None
            gc.collect()
            from utils.gpu_utils import safe_cuda_empty_cache
            safe_cuda_empty_cache()
        except Exception as e:
            print(f"Error on leaving Realtime VC: {e}")

    def open_output_folder(self):
        import os
        from tkinter import messagebox
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(os.path.dirname(script_dir), "Outputs", "RVC")
        if not os.path.exists(output_dir): os.makedirs(output_dir)
        try:
            if os.name == 'nt':
                os.startfile(output_dir)
        except Exception as e:
            messagebox.showerror("錯誤", f"無法開啟資料夾: {e}")

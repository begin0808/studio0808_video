import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import sys
import subprocess
import time
import torch
from modules.gpt_sovits_client import GPTSovitsClient

class CloneView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        # UI State
        self.script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.output_dir = os.path.join(self.script_dir, "Outputs", "Cloned")
        if not os.path.exists(self.output_dir): os.makedirs(self.output_dir)

        # Variables
        self.api_url_var = ctk.StringVar(value="http://127.0.0.1:9880")
        self.ref_audio_var = ctk.StringVar()
        self.ref_text_var = ctk.StringVar()
        self.ref_lang_var = ctk.StringVar(value="中文 (Chinese)")
        self.target_lang_var = ctk.StringVar(value="中文 (Chinese)")
        self.target_text_var = ctk.StringVar()
        
        self.temp_var = ctk.DoubleVar(value=0.8)
        self.top_p_var = ctk.DoubleVar(value=0.8)
        
        self.gpt_model_var = ctk.StringVar()
        self.sovits_model_var = ctk.StringVar()
        
        # Client
        self.client = None

        # Fonts
        self.font_header = ("Microsoft JhengHei UI", 24, "bold")
        self.font_ui = ("Microsoft JhengHei UI", 14)
        self.font_mono = ("Consolas", 12)

        # Setup UI
        self.create_ui()
        self.check_gpu()
        
        # Init Logger adapter class to pipe to our text box
        class UILogger:
            def __init__(self, view): self.view = view
            def log(self, msg): self.view.log(msg)
            
        self.client_logger = UILogger(self)

    def create_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(10, 5))
        # Title removed based on feedback
        
        self.gpu_label = ctk.CTkLabel(header, text="檢查 GPU...", text_color="gray", font=self.font_ui)
        self.gpu_label.pack(side="left")

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

        # Scrollable Content
        self.scroll_content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_content.pack(fill="both", expand=True, padx=20, pady=5)
        
        # 1. API Connection
        frame_api = ctk.CTkFrame(self.scroll_content)
        frame_api.pack(fill="x", pady=2)
        
        ctk.CTkLabel(frame_api, text="1. API 連線設定", font=("Microsoft JhengHei UI", 16, "bold"), text_color="#42A5F5").pack(anchor="w", padx=15, pady=(5, 2))
        
        api_row = ctk.CTkFrame(frame_api, fg_color="transparent")
        api_row.pack(fill="x", padx=15, pady=(0, 5))
        
        ctk.CTkLabel(api_row, text="API 位址:", font=self.font_ui).pack(side="left")
        ctk.CTkEntry(api_row, textvariable=self.api_url_var, width=300, font=self.font_ui).pack(side="left", padx=10)
        
        # Start API Button
        self.btn_start_api = ctk.CTkButton(api_row, text="啟動 API", command=self.start_api_server, font=self.font_ui, width=100, fg_color="#E91E63")
        self.btn_start_api.pack(side="left", padx=(0, 5))
        
        self.btn_stop_api = ctk.CTkButton(api_row, text="關閉 API", command=self.stop_api_server, font=self.font_ui, width=100, fg_color="#E53935", state="disabled")
        self.btn_stop_api.pack(side="left", padx=(0, 5))
        
        self.btn_start_webui = ctk.CTkButton(api_row, text="啟動訓練面板", command=self.start_training_webui, font=self.font_ui, width=120, fg_color="#9C27B0")
        self.btn_start_webui.pack(side="left", padx=(15, 5))
        
        self.lbl_status = ctk.CTkLabel(api_row, text="未連線", text_color="gray", font=self.font_ui)
        self.lbl_status.pack(side="left", padx=15)

        # 1.5 Custom Models
        frame_models = ctk.CTkFrame(self.scroll_content)
        frame_models.pack(fill="x", pady=2)
        
        ctk.CTkLabel(frame_models, text="2. 模型設定 (選填)", font=("Microsoft JhengHei UI", 16, "bold"), text_color="#9C27B0").pack(anchor="w", padx=15, pady=(5, 2))
        
        model_row1 = ctk.CTkFrame(frame_models, fg_color="transparent")
        model_row1.pack(fill="x", padx=15)
        ctk.CTkLabel(model_row1, text="GPT 模型:", font=self.font_ui, width=100, anchor="e").pack(side="left")
        ctk.CTkEntry(model_row1, textvariable=self.gpt_model_var, width=400, font=self.font_ui, placeholder_text="(預設官方模型) 選擇 .ckpt 檔").pack(side="left", padx=5)
        ctk.CTkButton(model_row1, text="加入檔案", command=self.browse_gpt, font=self.font_ui, width=80, fg_color="#3949AB").pack(side="left", padx=5)
        
        model_row2 = ctk.CTkFrame(frame_models, fg_color="transparent")
        model_row2.pack(fill="x", padx=15, pady=(2, 5))
        ctk.CTkLabel(model_row2, text="SoVITS 模型:", font=self.font_ui, width=100, anchor="e").pack(side="left")
        ctk.CTkEntry(model_row2, textvariable=self.sovits_model_var, width=400, font=self.font_ui, placeholder_text="(預設官方模型) 選擇 .pth 檔").pack(side="left", padx=5)
        ctk.CTkButton(model_row2, text="加入檔案", command=self.browse_sovits, font=self.font_ui, width=80, fg_color="#3949AB").pack(side="left", padx=5)
        
        # 模型載入已改為自動觸發

        # 2. Reference Audio
        frame_ref = ctk.CTkFrame(self.scroll_content)
        frame_ref.pack(fill="x", pady=2)
        
        ctk.CTkLabel(frame_ref, text="3. 參考音訊 (必填)", font=("Microsoft JhengHei UI", 16, "bold"), text_color="#66BB6A").pack(anchor="w", padx=15, pady=(5, 2))
        
        # Ref Audio File
        ref_row1 = ctk.CTkFrame(frame_ref, fg_color="transparent")
        ref_row1.pack(fill="x", padx=15)
        ctk.CTkLabel(ref_row1, text="音訊檔案:", font=self.font_ui, width=80, anchor="e").pack(side="left")
        ctk.CTkEntry(ref_row1, textvariable=self.ref_audio_var, width=400, font=self.font_ui).pack(side="left", padx=5)
        ctk.CTkButton(ref_row1, text="加入檔案", command=self.browse_ref, font=self.font_ui, width=80, fg_color="#3949AB").pack(side="left", padx=5)
        ctk.CTkLabel(ref_row1, text="(建議 3-10秒 乾淨人聲)", text_color="gray", font=self.font_ui).pack(side="left", padx=5)

        # Ref Text
        ref_row2 = ctk.CTkFrame(frame_ref, fg_color="transparent")
        ref_row2.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(ref_row2, text="參考文本:", font=self.font_ui, width=80, anchor="e").pack(side="left")
        ctk.CTkEntry(ref_row2, textvariable=self.ref_text_var, width=500, font=self.font_ui, placeholder_text="輸入該段音訊說的內容...").pack(side="left", padx=5)
        
        # Ref Lang
        ref_row3 = ctk.CTkFrame(frame_ref, fg_color="transparent")
        ref_row3.pack(fill="x", padx=15, pady=(0, 5))
        ctk.CTkLabel(ref_row3, text="參考語言:", font=self.font_ui, width=80, anchor="e").pack(side="left")
        ctk.CTkOptionMenu(ref_row3, variable=self.ref_lang_var, 
                         values=["中文 (Chinese)", "英文 (English)", "日文 (Japanese)"], 
                         font=self.font_ui, dropdown_font=self.font_ui, width=150).pack(side="left", padx=5)

        # 3. Target
        frame_target = ctk.CTkFrame(self.scroll_content)
        frame_target.pack(fill="x", pady=2)
        ctk.CTkLabel(frame_target, text="4. 目標生成 (必填)", font=("Microsoft JhengHei UI", 16, "bold"), text_color="#FFA726").pack(anchor="w", padx=15, pady=(5, 2))
        
        # Target Lang & Text Label
        target_row1 = ctk.CTkFrame(frame_target, fg_color="transparent")
        target_row1.pack(fill="x", padx=20)
        
        ctk.CTkLabel(target_row1, text="目標語言:", font=self.font_ui).pack(side="left")
        ctk.CTkOptionMenu(target_row1, variable=self.target_lang_var, 
                         values=["中文 (Chinese)", "英文 (English)", "日文 (Japanese)"], 
                         font=self.font_ui, dropdown_font=self.font_ui, width=150).pack(side="left", padx=10)
        
        self.target_mode_var = ctk.StringVar(value="text")
        ctk.CTkRadioButton(target_row1, text="單句輸入", variable=self.target_mode_var, value="text", command=self.toggle_target_mode, font=self.font_ui).pack(side="left", padx=15)
        ctk.CTkRadioButton(target_row1, text="SRT 批量配音", variable=self.target_mode_var, value="srt", command=self.toggle_target_mode, font=self.font_ui).pack(side="left", padx=5)

        # Container for Target Input
        self.target_container = ctk.CTkFrame(frame_target, fg_color="transparent")
        self.target_container.pack(fill="x", padx=20, pady=5)
        
        # Text Mode
        self.frame_target_text = ctk.CTkFrame(self.target_container, fg_color="transparent")
        ctk.CTkLabel(self.frame_target_text, text="目標文本:", font=self.font_ui).pack(anchor="w")
        self.txt_target = ctk.CTkTextbox(self.frame_target_text, height=80, font=self.font_ui)
        self.txt_target.pack(fill="x", pady=(5, 0))
        
        # SRT Mode
        self.frame_target_srt = ctk.CTkFrame(self.target_container, fg_color="transparent")
        self.srt_path_var = ctk.StringVar()
        ctk.CTkLabel(self.frame_target_srt, text="SRT 檔案:", font=self.font_ui).pack(side="left")
        ctk.CTkEntry(self.frame_target_srt, textvariable=self.srt_path_var, width=400, font=self.font_ui).pack(side="left", padx=5)
        ctk.CTkButton(self.frame_target_srt, text="瀏覽...", command=self.browse_srt, font=self.font_ui, width=80).pack(side="left")
        
        self.toggle_target_mode()

        # 4. Parameters
        frame_params = ctk.CTkFrame(self.scroll_content)
        frame_params.pack(fill="x", pady=2)
        
        # Grid layout for params to save space
        params_inner = ctk.CTkFrame(frame_params, fg_color="transparent")
        params_inner.pack(fill="x", padx=15, pady=5)
        
        # Temp
        ctk.CTkLabel(params_inner, text="情感變異 (Temp):", font=self.font_ui).pack(side="left")
        
        self.lbl_temp_val = ctk.CTkLabel(params_inner, text=f"{self.temp_var.get():.2f}", font=self.font_ui, width=40)
        def _update_temp(v): 
            val = round(v * 20) / 20
            self.lbl_temp_val.configure(text=f"{val:.2f}")
            self.temp_var.set(val)
        ctk.CTkSlider(params_inner, from_=0.1, to=2.0, number_of_steps=38, variable=self.temp_var, width=120, command=_update_temp).pack(side="left", padx=5)
        self.lbl_temp_val.pack(side="left")
        
        # Top P
        ctk.CTkLabel(params_inner, text="穩定度 (Top_P):", font=self.font_ui).pack(side="left", padx=(20, 0))
        
        self.lbl_topp_val = ctk.CTkLabel(params_inner, text=f"{self.top_p_var.get():.2f}", font=self.font_ui, width=40)
        def _update_topp(v): 
            val = round(v * 20) / 20
            self.lbl_topp_val.configure(text=f"{val:.2f}")
            self.top_p_var.set(val)
        ctk.CTkSlider(params_inner, from_=0.1, to=1.0, number_of_steps=18, variable=self.top_p_var, width=120, command=_update_topp).pack(side="left", padx=5)
        self.lbl_topp_val.pack(side="left")

        # Action and Output controls
        action_frame = ctk.CTkFrame(self.scroll_content, fg_color="transparent")
        action_frame.pack(pady=15, fill="x", padx=20)
        
        self.btn_run = ctk.CTkButton(action_frame, text="開始推理", command=self.run_inference, font=("Microsoft JhengHei UI", 16, "bold"), height=40, width=200, fg_color="#E91E63")
        self.btn_run.pack(side="left", padx=(0, 10))
        
        ctk.CTkButton(action_frame, text="開啟輸出資料夾", command=self.open_output_folder, 
                      width=150, height=40, font=("Microsoft JhengHei UI", 16, "bold"), fg_color="#4CAF50", hover_color="#388E3C", text_color="white").pack(side="left", padx=10)

        # Log
        ctk.CTkLabel(self.scroll_content, text="執行日誌:", font=self.font_ui).pack(anchor="w", padx=20)
        self.log_box = ctk.CTkTextbox(self.scroll_content, height=100, font=("Microsoft JhengHei UI", 15), fg_color=("gray95", "#000000"), text_color=("gray10", "gray90"), state="disabled") # Taller log box
        self.log_box.pack(fill="x", pady=5, padx=20)

    def log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

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

    def browse_ref(self):
        opts_dir = self.output_dir
        if not os.path.exists(opts_dir):
            os.makedirs(opts_dir, exist_ok=True)
        f = filedialog.askopenfilename(initialdir=opts_dir, filetypes=[("Audio", "*.wav;*.mp3;*.flac")])
        if f: self.ref_audio_var.set(f)
        
    def _get_models_dir(self):
        d = os.path.join(self.script_dir, "models", "SoVITS")
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        return d
        
    def browse_gpt(self):
        f = filedialog.askopenfilename(initialdir=self._get_models_dir(), filetypes=[("GPT Model", "*.ckpt")])
        if f: self.gpt_model_var.set(f)
        
    def browse_sovits(self):
        f = filedialog.askopenfilename(initialdir=self._get_models_dir(), filetypes=[("SoVITS Model", "*.pth")])
        if f: self.sovits_model_var.set(f)
        
    def browse_srt(self):
        f = filedialog.askopenfilename(filetypes=[("Subtitle", "*.srt")])
        if f: self.srt_path_var.set(f)

    def toggle_target_mode(self):
        mode = self.target_mode_var.get()
        if mode == "text":
            self.frame_target_srt.pack_forget()
            self.frame_target_text.pack(fill="x")
        else:
            self.frame_target_text.pack_forget()
            self.frame_target_srt.pack(fill="x")
        
    def apply_models(self):
        """ 此方法保留供內部調用，或在需要時透過介面外觸發 """
        if not self.client:
            if not self.test_connection(silent=True): return
        gpt_path = self.gpt_model_var.get().strip() or None
        sovits_path = self.sovits_model_var.get().strip() or None
        
        self.btn_apply_models.configure(state="disabled")
        threading.Thread(target=self._apply_models_thread, args=(gpt_path, sovits_path), daemon=True).start()
        
    def _apply_models_thread(self, gpt_path, sovits_path):
        success = self.client.init_models(gpt_path, sovits_path)
        if success:
            self.log("✅ 成功切換至自訂模型！")
        else:
            self.log("❌ 模型切換失敗，請確認檔案路徑或 API 狀態。")
        self.btn_apply_models.configure(state="normal")
        
    def open_output_folder(self):
        if os.path.exists(self.output_dir):
            os.startfile(self.output_dir)
        else:
            messagebox.showwarning("提示", "輸出資料夾尚未建立")

    def test_connection(self, silent=False):
        url = self.api_url_var.get()
        self.client = GPTSovitsClient(url, logger=self.client_logger)
        if self.client.check_connection():
            self.lbl_status.configure(text="✅ 已連線", text_color="green")
            if not silent: messagebox.showinfo("成功", "API 連線成功！")
            return True
        else:
            self.lbl_status.configure(text="❌ 連線失敗", text_color="red")
            if not silent: messagebox.showerror("錯誤", "無法連線至 API")
            return False

    def run_inference(self):
        # Validation
        if not self.client:
             # Try auto init
             if not self.test_connection(silent=True): return

        ref_audio = self.ref_audio_var.get()
        ref_text = self.ref_text_var.get()
        mode = self.target_mode_var.get()
        target_text = self.txt_target.get("0.0", "end").strip() if mode == "text" else ""
        srt_path = self.srt_path_var.get() if mode == "srt" else ""
        
        if not ref_audio or not os.path.exists(ref_audio):
            messagebox.showwarning("提示", "請選擇參考音訊")
            return
        if not ref_text:
            messagebox.showwarning("提示", "請輸入參考文本")
            return
        if mode == "text" and not target_text:
            messagebox.showwarning("提示", "請輸入目標文本")
            return
        if mode == "srt" and not os.path.exists(srt_path):
            messagebox.showwarning("提示", "請選擇有效的 SRT 檔案")
            return
            
        gpt_path = self.gpt_model_var.get().strip() or None
        sovits_path = self.sovits_model_var.get().strip() or None
        
        self.btn_run.configure(state="disabled")
        if mode == "text":
            threading.Thread(target=self._infer_thread, args=(ref_audio, ref_text, target_text, gpt_path, sovits_path), daemon=True).start()
        else:
            threading.Thread(target=self._infer_srt_thread, args=(ref_audio, ref_text, srt_path, gpt_path, sovits_path), daemon=True).start()

    def _infer_thread(self, ref_audio, ref_text, target_text, gpt_path=None, sovits_path=None):
        try:
            # Auto Apply Models if provided
            if gpt_path or sovits_path:
                self.log("🔄 正在自動載入選定模型...")
                if not self.client.init_models(gpt_path, sovits_path):
                    self.log("❌ 模型載入失敗，中止推理。")
                    return
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            outfile = os.path.join(self.output_dir, f"clone_{timestamp_str}.wav")
            outfile = self.get_unique_path(outfile)
            
            self.log("🚀 開始推理...")
            
            lang_map = {
                "中文 (Chinese)": "zh",
                "英文 (English)": "en", 
                "日文 (Japanese)": "ja",
                "zh-ALL": "zh", "en-ALL": "en", "ja-JP": "ja" # fallback
            }
            
            ref_lang_code = lang_map.get(self.ref_lang_var.get(), "zh")
            target_lang_code = lang_map.get(self.target_lang_var.get(), "zh")
            
            success, msg = self.client.infer(
                ref_audio_path=ref_audio,
                ref_text=ref_text,
                ref_lang=ref_lang_code,
                target_text=target_text,
                target_lang=target_lang_code,
                output_path=outfile,
                temperature=self.temp_var.get(),
                top_p=self.top_p_var.get()
            )
            
            if success:
                self.log(f"✅ 生成成功: {os.path.basename(outfile)}")
                os.startfile(outfile)
            else:
                self.log(f"❌ 生成失敗: {msg}")
                
        except Exception as e:
            self.log(f"❌ 錯誤: {e}")
            
        finally:
            self.btn_run.configure(state="normal")

    def _infer_srt_thread(self, ref_audio, ref_text, srt_path, gpt_path=None, sovits_path=None):
        import time, gc, re
        from pydub import AudioSegment
        
        try:
            # Auto Apply Models if provided
            if gpt_path or sovits_path:
                self.log("🔄 正在自動載入選定模型...")
                if not self.client.init_models(gpt_path, sovits_path):
                    self.log("❌ 模型載入失敗，中止推理。")
                    return
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(os.path.basename(srt_path))[0]
            outfile = os.path.join(self.output_dir, f"{base_name}_clone_{timestamp_str}.wav")
            outfile = self.get_unique_path(outfile)
            
            self.log("🚀 開始 SRT 批量推理...")
            
            lang_map = {"中文 (Chinese)": "zh", "英文 (English)": "en", "日文 (Japanese)": "ja"}
            ref_lang_code = lang_map.get(self.ref_lang_var.get(), "zh")
            target_lang_code = lang_map.get(self.target_lang_var.get(), "zh")
            
            with open(srt_path, "r", encoding="utf-8") as f:
                content = f.read().replace("\r\n", "\n").replace("\r", "\n")
            
            blocks = re.split(r'\n{2,}', content.strip())
            segments = []
            
            def parse_time(t_str):
                parts = t_str.strip().replace(',', '.').split(':')
                return int(parts[0])*3600 + int(parts[1])*60 + float(parts[2])

            for block in blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                     idx = 0 if "-->" in lines[0] else 1
                     if len(lines) > idx+1 and "-->" in lines[idx]: # fix possible index error
                         start_str, end_str = lines[idx].split("-->")
                         text = re.sub(r'<[^>]+>', '', " ".join(lines[idx+1:]))
                         segments.append({"start": parse_time(start_str), "end": parse_time(end_str), "text": text})
                         
            if not segments:
                self.log("❌ SRT 為空或解析失敗")
                return

            full_audio = AudioSegment.silent(duration=int((segments[-1]["end"] + 10.0) * 1000))
            last_end_ms = 0
            temp_files = []
            
            for i, seg in enumerate(segments):
                if not seg['text'].strip(): continue
                self.log(f"[{i+1}/{len(segments)}] 處理中: {seg['text'][:20]}...")
                
                temp_f = os.path.join(self.output_dir, f"srt_temp_{timestamp_str}_{i}.wav")
                success, msg = self.client.infer(
                    ref_audio_path=ref_audio, ref_text=ref_text, ref_lang=ref_lang_code,
                    target_text=seg['text'], target_lang=target_lang_code, output_path=temp_f,
                    temperature=self.temp_var.get(), top_p=self.top_p_var.get()
                )
                
                if success and os.path.exists(temp_f):
                    seg_audio = AudioSegment.from_file(temp_f)
                    actual_start_ms = max(int(seg['start'] * 1000), last_end_ms)
                    full_audio = full_audio.overlay(seg_audio, position=actual_start_ms)
                    last_end_ms = actual_start_ms + len(seg_audio)
                    temp_files.append(temp_f)
                else:
                    self.log(f"⚠️ 生成失敗: {msg}")

            full_audio.export(outfile, format="wav")
            del full_audio
            gc.collect()
            
            for f in temp_files:
                try: os.remove(f)
                except: pass
                
            self.log(f"🎉 批量配音完成: {os.path.basename(outfile)}")
            os.startfile(outfile)
            
        except Exception as e:
            self.log(f"❌ 錯誤: {e}")
            import traceback; traceback.print_exc()
        finally:
            self.btn_run.configure(state="normal")

    def start_api_server(self):
        # Dynamic Path Detection
        # 1. Check relative path (if moved inside project)
        local_gpt_path = os.path.join(self.script_dir, "GPT-SoVITS")
        # 2. Check absolute path (original location)
        abs_gpt_path = r"D:\GPT-SoVITS"
        
        gpt_sovits_path = None
        if os.path.exists(os.path.join(local_gpt_path, "api.py")):
            gpt_sovits_path = local_gpt_path
        elif os.path.exists(os.path.join(abs_gpt_path, "api.py")):
            gpt_sovits_path = abs_gpt_path
            
        if not gpt_sovits_path:
            messagebox.showerror("錯誤", f"找不到 GPT-SoVITS！\n請確認是否位於:\n1. {local_gpt_path}\n2. {abs_gpt_path}")
            return

        api_script = os.path.join(gpt_sovits_path, "api.py")
        python_exe = os.path.join(gpt_sovits_path, "runtime", "python.exe")
        
        if not os.path.exists(python_exe):
             # Try system python or fallback
             if getattr(sys, 'frozen', False):
                 # In packaged app, sys.executable is the main EXE. 
                 # NEVER use it to run python scripts as it triggers splash screen and fails.
                 python_exe = "python" # Fallback to system path
             else:
                 python_exe = sys.executable 
        
        # Defaults
        gpt_weights = os.path.join(gpt_sovits_path, "GPT_SoVITS", "pretrained_models", "s1bert25hz-2kh-longer-epoch=68e-step=50232.ckpt")
        sovits_weights = os.path.join(gpt_sovits_path, "GPT_SoVITS", "pretrained_models", "s2G488k.pth")
        
        cmd = [
            python_exe, api_script,
            "-g", gpt_weights,
            "-s", sovits_weights,
            "-dl", "zh",
            "-a", "127.0.0.1",
            "-p", "9880",
            "-fp"  # Force full precision to avoid CUDA kernel compatibility issues on new GPUs (like RTX 5060)
        ]
        
        self.log(f"🚀 正在啟動 API 伺服器... (路徑: {gpt_sovits_path})")
        self.lbl_status.configure(text="啟動中...", text_color="#E67E22")
        self.btn_start_api.configure(state="disabled")
        
        def _run():
            try:
                self.api_process = subprocess.Popen(
                    cmd,
                    cwd=gpt_sovits_path,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                self.log("✅ API 啟動指令已發送！模型加載通常需要 30-60 秒，請耐心候...")
                self.after(0, lambda: self.btn_stop_api.configure(state="normal"))
                
                # Wait 5 seconds before starting first test
                time.sleep(5)
                self.after(0, self.auto_test_connection)
                
            except Exception as e:
                self.log(f"❌ 啟動失敗: {e}")
                self.btn_start_api.configure(state="normal")
                self.lbl_status.configure(text="啟動失敗", text_color="red")
        
        threading.Thread(target=_run, daemon=True).start()

    def auto_test_connection(self):
        self.log("🔄 正在自動測試 API 連線 (模型加載中)...")
        self.client = GPTSovitsClient(self.api_url_var.get(), logger=self.client_logger)
        
        def _check():
            connected = False
            max_retries = 24 # 增加頻率 (24次 * 5秒 = 2分鐘)
            for i in range(max_retries):
                # Check if process is still alive
                if hasattr(self, 'api_process') and self.api_process:
                    if self.api_process.poll() is not None:
                        self.log("❌ API 伺服器已意外停止 (Process terminated)。")
                        break
                        
                if not self.client:
                    break
                
                self.log(f"⏳ 正在進行連線檢測 ({i+1}/{max_retries})...")
                self.after(0, lambda idx=i: self.lbl_status.configure(text=f"載入中 ({idx+1}/{max_retries})", text_color="#E91E63"))
                
                if self.client.check_connection():
                    connected = True
                    break
                time.sleep(5) 
                
            if connected:
                self.after(0, lambda: self.lbl_status.configure(text="✅ 已連線", text_color="green"))
                self.after(0, lambda: messagebox.showinfo("成功", "API 已成功啟動並連線！\n您可以開始測試。"))
            else:
                self.after(0, lambda: self.lbl_status.configure(text="❌ 連線失敗", text_color="red"))
                self.after(0, lambda: self.btn_start_api.configure(state="normal")) # 修正按鈕鎖定問題
                self.after(0, lambda: messagebox.showwarning("提示", "API 啟動超時或失敗。\n請查看 Console 視窗中的錯誤訊息，確認模型路徑或環境是否正確。"))
                
        threading.Thread(target=_check, daemon=True).start()

    def stop_api_server(self):
        if hasattr(self, 'api_process') and self.api_process:
            try:
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.api_process.pid)], check=True, capture_output=True)
                self.log("🛑 已送出終止 API 伺服器指令。")
            except Exception as e:
                self.log(f"⚠️ 終止 API 發生錯誤: {e}")
            self.api_process = None
            
        self.btn_stop_api.configure(state="disabled")
        self.btn_start_api.configure(state="normal")
        self.lbl_status.configure(text="未連線", text_color="gray")
        self.client = None

    def start_training_webui(self):
        """直接透過主程式(Python)啟動訓練面板，繞過 Windows Defender 對 .bat 檔的封鎖"""
        local_gpt_path = os.path.join(self.script_dir, "GPT-SoVITS")
        abs_gpt_path = r"D:\GPT-SoVITS"
        
        gpt_sovits_path = None
        if os.path.exists(os.path.join(local_gpt_path, "webui.py")):
            gpt_sovits_path = local_gpt_path
        elif os.path.exists(os.path.join(abs_gpt_path, "webui.py")):
            gpt_sovits_path = abs_gpt_path
            
        if not gpt_sovits_path:
            messagebox.showerror("錯誤", "找不到 GPT-SoVITS 核心資料夾，請確認已下載完整版！")
            return
            
        python_exe = os.path.join(gpt_sovits_path, "runtime", "python.exe")
        if not os.path.exists(python_exe):
            messagebox.showerror("錯誤", "找不到 runtime\python.exe 執行環境。")
            return
            
        cmd = ["cmd", "/k", python_exe, "-I", "webui.py", "zh_CN"]
        
        self.log("🟣 正在開啟進階訓練面板 (WebUI)...")
        try:
            subprocess.Popen(
                cmd,
                cwd=gpt_sovits_path,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            self.log("✅ 訓練面板已成功啟動！(請查看新跳出的黑色視窗或瀏覽器)")
        except Exception as e:
            self.log(f"❌ 啟動訓練面板失敗: {e}")
            messagebox.showerror("啟動失敗", f"無法啟動 WebUI:\n{e}")

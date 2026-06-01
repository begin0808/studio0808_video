import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import sys
import subprocess
import asyncio
import edge_tts
import time
import shutil
import gc
import torch
from datetime import datetime
# Import Pydub
from pydub import AudioSegment

class TTSView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        # UI State
        self.script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.output_dir = os.path.join(self.script_dir, "Outputs", "TTS")
        if not os.path.exists(self.output_dir): os.makedirs(self.output_dir)
        
        # SRT Path
        self.srt_path = None

        # Variables
        self.voice_var = ctk.StringVar()
        self.lang_var = ctk.StringVar(value="中文 (Chinese - All)")
        self.speed_var = ctk.StringVar(value="+0%")
        
        # New Role Vars (5 Roles)
        self.voice_man_var = ctk.StringVar()
        self.voice_woman_var = ctk.StringVar()
        self.voice_boy_var = ctk.StringVar()
        self.voice_girl_var = ctk.StringVar()
        
        # Fonts
        self.font_header = ("Microsoft JhengHei UI", 24, "bold")
        self.font_tab = ("Microsoft JhengHei UI", 16, "bold")
        self.font_ui = ("Microsoft JhengHei UI", 14)
        self.font_option = ("Microsoft JhengHei", 13) # Specific for options
        self.font_log = ("Microsoft JhengHei", 15) 

        self.is_stopped = False
        
        # Setup UI
        self.create_ui()
        
        # Data
        self.setup_voice_data()
        self.update_voice_lists("中文 (Chinese - All)")
        
        # Init FFmpeg for Pydub
        self.init_ffmpeg()
        
        # Check EdgeTTS Version
        try:
            self.log(f"Edge-TTS Version: {edge_tts.__version__}")
        except:
            self.log("Edge-TTS Version: Unknown")
            
        # Check GPU status
        self.check_gpu()

    def init_ffmpeg(self):
        # Improved FFmpeg detection from reference
        found_ffmpeg = shutil.which("ffmpeg")
        
        if getattr(sys, 'frozen', False):
            script_dir = os.path.dirname(sys.executable)
        else:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            script_dir = os.path.dirname(script_dir)

        ffmpeg_candidates = [
            os.path.join(script_dir, "tools", "ffmpeg.exe"),
            os.path.join(os.getcwd(), "tools", "ffmpeg.exe"),
            os.path.join(script_dir, "ffmpeg.exe"),
            os.path.join(os.getcwd(), "ffmpeg.exe"),
        ]
        
        for p in ffmpeg_candidates:
            if os.path.exists(p):
                found_ffmpeg = p
                break
        
        if found_ffmpeg:
            AudioSegment.converter = found_ffmpeg
            # Add to PATH
            os.environ["PATH"] = os.path.dirname(found_ffmpeg) + os.pathsep + os.environ["PATH"]
            self.log(f"✅ FFmpeg 設定完成: {found_ffmpeg}")
        else:
            self.log("⚠️ 警告: 找不到 ffmpeg.exe，音訊合併與轉檔可能失敗！")

    def create_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(20, 10))
        # Title removed based on feedback

        # GPU Status
        self.gpu_label = ctk.CTkLabel(header, text="檢查 GPU...", text_color="gray", font=self.font_ui)
        self.gpu_label.pack(side="left")

        # Content Grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0) # Header
        self.grid_rowconfigure(1, weight=1) # Main Content

        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Left Panel: Settings
        left_panel = ctk.CTkFrame(main_frame, width=380) # Widen for Pitch controls
        left_panel.pack(side="left", fill="y", padx=(0, 10))
        
        # 1. Language & global settings
        ctk.CTkLabel(left_panel, text="語言設定", font=("Microsoft JhengHei UI", 16, "bold")).pack(anchor="w", padx=10, pady=(10, 5))
        
        self.combo_lang = ctk.CTkOptionMenu(
            left_panel,
            variable=self.lang_var,
            values=["中文 (Chinese - All)", "English (All)", "日本語 (Japan)", "韓語 (Korea)", "泰語 (Thailand)", "法語 (France)", "德語 (Germany)"], 
            font=self.font_option,
            dropdown_font=self.font_option,
            command=self.update_voice_lists,
            width=300
        )
        self.combo_lang.pack(padx=10, pady=5)
        
        ctk.CTkLabel(left_panel, text="全域語速 (Speed):", font=self.font_ui).pack(anchor="w", padx=10, pady=(10, 0))
        speeds = ["-50%", "-30%", "-20%", "-10%", "-5%", "+0%", "+5%", "+10%", "+20%", "+30%", "+50%"]
        self.combo_speed = ctk.CTkOptionMenu(left_panel, variable=self.speed_var, values=speeds, font=self.font_option, dropdown_font=self.font_option, width=300)
        self.combo_speed.pack(padx=10, pady=5)

        # 2. Roles (5 Roles) - Voice & Pitch
        ctk.CTkLabel(left_panel, text="角色聲音與音調 (Pitch)", font=("Microsoft JhengHei UI", 16, "bold")).pack(anchor="w", padx=10, pady=(20, 5))
        
        # Init Pitch Vars
        self.pitch_var = ctk.StringVar(value="+0Hz")
        self.pitch_man_var = ctk.StringVar(value="+0Hz")
        self.pitch_woman_var = ctk.StringVar(value="+0Hz")
        self.pitch_boy_var = ctk.StringVar(value="+0Hz")
        self.pitch_girl_var = ctk.StringVar(value="+0Hz")
        
        # Init Custom Tag Vars
        self.role_man_var = ctk.StringVar(value="Man")
        self.role_woman_var = ctk.StringVar(value="Woman")
        self.role_boy_var = ctk.StringVar(value="Boy")
        self.role_girl_var = ctk.StringVar(value="Girl")
        
        pitch_opts = ["-50Hz", "-30Hz", "-20Hz", "-10Hz", "-5Hz", "+0Hz", "+5Hz", "+10Hz", "+20Hz", "+30Hz", "+50Hz"]

        def create_role_selector(label_str, voice_var, pitch_var, color=None, role_var=None):
            # Container
            frame = ctk.CTkFrame(left_panel, fg_color="transparent")
            frame.pack(fill="x", padx=5, pady=5)
            
            if role_var:
                header_frame = ctk.CTkFrame(frame, fg_color="transparent")
                header_frame.pack(fill="x", padx=5, pady=(0, 2))
                entry = ctk.CTkEntry(header_frame, textvariable=role_var, font=self.font_ui, text_color=color, width=100, height=28)
                entry.pack(side="left")
                desc_label = ctk.CTkLabel(header_frame, text=label_str, font=self.font_ui, text_color=color)
                desc_label.pack(side="left", padx=5)
            else:
                lbl = ctk.CTkLabel(frame, text=label_str, font=self.font_ui, text_color=color)
                lbl.pack(anchor="w", padx=5, pady=(0, 2))
            
            # Controls Row
            row = ctk.CTkFrame(frame, fg_color="transparent")
            row.pack(fill="x")
            
            # Voice Menu (Larger)
            menu_voice = ctk.CTkOptionMenu(row, variable=voice_var, values=[], font=self.font_option, dropdown_font=self.font_option, width=220)
            menu_voice.pack(side="left", padx=5)
            
            # Pitch Menu (Smaller)
            menu_pitch = ctk.CTkOptionMenu(row, variable=pitch_var, values=pitch_opts, font=self.font_option, dropdown_font=self.font_option, width=100)
            menu_pitch.pack(side="left", padx=5)
            
            return menu_voice

        self.menu_main = create_role_selector("主要聲音 (Main):", self.voice_var, self.pitch_var, "#9B59B6")
        self.menu_man = create_role_selector(" (男聲):", self.voice_man_var, self.pitch_man_var, "#2980B9", self.role_man_var)
        self.menu_woman = create_role_selector(" (女聲):", self.voice_woman_var, self.pitch_woman_var, "#E74C3C", self.role_woman_var)
        self.menu_boy = create_role_selector(" (男童):", self.voice_boy_var, self.pitch_boy_var, "#27AE60", self.role_boy_var)
        self.menu_girl = create_role_selector(" (女童):", self.voice_girl_var, self.pitch_girl_var, "#F1C40F", self.role_girl_var)

        # Update Button
        ctk.CTkLabel(left_panel, text="系統維護", font=("Microsoft JhengHei UI", 16, "bold")).pack(anchor="w", padx=10, pady=(20, 5))
        self.btn_update = ctk.CTkButton(left_panel, text="更新組件", command=self.update_edge_tts, font=self.font_ui, fg_color="#E67E22")
        self.btn_update.pack(padx=10, pady=5, fill="x")

        # Right Panel: Text Input & Log
        right_panel = ctk.CTkFrame(main_frame)
        right_panel.pack(side="left", fill="both", expand=True)
        # ... (rest of UI code kept same logic by structure) ...
        # (Actually, I need to ensure I don't duplicate code if replace block is small.
        # But this replace block covers 'left_panel' creation to 'right_panel' start.
        # So I will continue the replacement correctly.)
        
        # Custom Tabs
        self.tab_bar = ctk.CTkFrame(right_panel, fg_color="transparent")
        self.tab_bar.pack(fill="x", padx=10, pady=5)
        
        self.tabs = {
            "text": {"text": "一般文字模式", "color": "#1E88E5", "frame": None},
            "srt":  {"text": "SRT 字幕配音", "color": "#8E24AA", "frame": None}
        }
        self.tab_buttons = {}
        for key, data in self.tabs.items():
            btn = ctk.CTkButton(self.tab_bar, text=data["text"], font=self.font_tab,
                                fg_color="transparent", border_width=2, border_color=data["color"], text_color=data["color"],
                                hover_color=data["color"],
                                width=150, height=40,
                                command=lambda k=key: self.switch_tab(k))
            btn.pack(side="left", padx=(0, 15))
            self.tab_buttons[key] = btn
            
        # Content Area
        self.content_area = ctk.CTkFrame(right_panel, fg_color="transparent")
        self.content_area.pack(fill="x", expand=False, padx=10, pady=5)
        
        self.init_tab_content()
        self.switch_tab("text") # Default
        
        # Buttons
        btn_frame = ctk.CTkFrame(right_panel, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        self.btn_gen = ctk.CTkButton(btn_frame, text="開始生成", command=self.run_tts_thread, font=("Microsoft JhengHei UI", 16, "bold"), height=40, fg_color="#E91E63", hover_color="#C2185B")
        self.btn_gen.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.btn_stop = ctk.CTkButton(btn_frame, text="中斷", command=self.stop_tts, font=("Microsoft JhengHei UI", 16, "bold"), height=40, width=80, fg_color="#F44336", hover_color="#D32F2F", state="disabled")
        self.btn_stop.pack(side="left", padx=(5, 5))
        
        self.btn_play = ctk.CTkButton(btn_frame, text="播放", command=self.play_audio, font=self.font_ui, height=40, width=100, fg_color="#546E7A", state="disabled")
        self.btn_play.pack(side="left", padx=(5, 0))
        
        self.btn_open = ctk.CTkButton(btn_frame, text="開啟輸出", command=self.open_output_folder, font=self.font_ui, height=40, width=100, fg_color="#4CAF50", hover_color="#388E3C", text_color="white")
        self.btn_open.pack(side="left", padx=(5, 0))

        # Log
        ctk.CTkLabel(right_panel, text="執行日誌", font=self.font_ui).pack(anchor="w", padx=10, pady=(10, 5))
        self.log_box = ctk.CTkTextbox(right_panel, font=self.font_log, height=150, fg_color=("gray95", "#000000"), text_color=("gray10", "gray90"), state="disabled")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.last_output_file = None
        self.current_tab_key = "text"

    # ... (init_tab_content, switch_tab, log, setup_voice_data, update_voice_lists, get_voice_code, load_srt, clean_srt_chinese) ...
    # Wait, I can't skip methods in replace_file_content unless I target specific lines.
    # The target StartLine is 108.
    
    # I need to handle run_tts_text and run_srt_dubbing too.
    # To avoid huge replacement, I will split into chunks.
    # This chunk handles UI updates.

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


    def init_tab_content(self):
        # Text Tab
        self.tabs["text"]["frame"] = ctk.CTkFrame(self.content_area, fg_color="transparent")
        ctk.CTkLabel(self.tabs["text"]["frame"], text="輸入文字 (支援角色標籤: Man:, Woman:, Boy:, Girl:)", font=self.font_ui).pack(anchor="w", pady=(5, 5))
        self.text_input = ctk.CTkTextbox(self.tabs["text"]["frame"], font=self.font_ui, height=200)
        self.text_input.pack(fill="both", expand=True, pady=5)
        self.text_input.insert("0.0", "你好，這是一個測試。\nMan: 我是男生。\nWoman: 我是女生。\nBoy: 我是小男生。\nGirl: 我是小女生。")
        
        # SRT Tab
        self.tabs["srt"]["frame"] = ctk.CTkFrame(self.content_area, fg_color="transparent")
        ctk.CTkLabel(self.tabs["srt"]["frame"], text="載入 SRT 字幕檔，將依據時間軸生成完整配音檔 (WAV)。", font=self.font_ui).pack(anchor="w", pady=10)
        
        srt_row = ctk.CTkFrame(self.tabs["srt"]["frame"], fg_color="transparent")
        srt_row.pack(fill="x", pady=10)
        
        self.btn_load_srt = ctk.CTkButton(srt_row, text="載入 SRT", command=self.load_srt, font=self.font_ui, width=120)
        self.btn_load_srt.pack(side="left", padx=5)
        
        self.btn_clean_srt = ctk.CTkButton(srt_row, text="只保留中文", command=self.clean_srt_chinese, font=self.font_ui, width=120, fg_color="#E74C3C")
        self.btn_clean_srt.pack(side="left", padx=5)
        
        self.lbl_srt_name = ctk.CTkLabel(srt_row, text="未選擇檔案", font=self.font_ui, text_color="gray")
        self.lbl_srt_name.pack(side="left", padx=10)

    def clean_srt_chinese(self):
        if not self.srt_path:
            messagebox.showwarning("提示", "請先載入 SRT 檔案")
            return
            
        try:
            import re
            with open(self.srt_path, "r", encoding="utf-8") as f:
                content = f.read().replace("\r\n", "\n")
            
            blocks = re.split(r'\n{2,}', content.strip())
            new_blocks = []
            
            for block in blocks:
                lines = block.strip().split('\n')
                if len(lines) < 2: continue
                
                # Find Time Line
                time_idx = -1
                for i, line in enumerate(lines):
                    if "-->" in line:
                        time_idx = i
                        break
                
                if time_idx == -1: continue
                
                header = lines[:time_idx+1]
                text_lines = lines[time_idx+1:]
                
                # Filter: Keep line if it contains Chinese characters
                clean_lines = [l for l in text_lines if re.search(r'[\u4e00-\u9fff]', l)]
                
                # Only keep block if there is chinese content
                if clean_lines:
                    new_blocks.append("\n".join(header + clean_lines))
            
            if not new_blocks:
                messagebox.showwarning("警告", "清洗後內容為空！(找不到中文字幕)")
                return

            new_content = "\n\n".join(new_blocks)
            base_name = os.path.splitext(self.srt_path)[0]
            new_path = f"{base_name}_zh.srt"
            
            with open(new_path, "w", encoding="utf-8") as f:
                f.write(new_content)
                
            self.srt_path = new_path
            self.lbl_srt_name.configure(text=os.path.basename(new_path), text_color="#2ECC71")
            self.log(f"✅ 字幕清洗完成: {os.path.basename(new_path)}")
            messagebox.showinfo("成功", f"已建立純中文字幕：\n{os.path.basename(new_path)}")
            
        except Exception as e:
            self.log(f"❌ 清洗失敗: {e}")
            messagebox.showerror("錯誤", f"清洗失敗: {e}")

    def switch_tab(self, key):
        self.current_tab_key = key
        # Update Buttons
        for k, btn in self.tab_buttons.items():
            if k == key:
                btn.configure(fg_color=self.tabs[k]["color"], text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color=self.tabs[k]["color"])
        
        # Show Frame
        for k, data in self.tabs.items():
            if data["frame"]: data["frame"].pack_forget()
        
        if self.tabs[key]["frame"]:
            self.tabs[key]["frame"].pack(fill="both", expand=True)

    def log(self, msg):
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")
        msg = f"{timestamp}{msg}"
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

    def setup_voice_data(self):
        # ... (Same voice data map)
        zh_voices = [
            {"name": "🇹🇼 臺灣女聲 - 曉臻 (HsiaoChen)", "code": "zh-TW-HsiaoChenNeural", "gender": "Female"},
            {"name": "🇹🇼 臺灣男聲 - 雲哲 (YunJhe)", "code": "zh-TW-YunJheNeural", "gender": "Male"},
            {"name": "🇹🇼 臺灣女聲 - 曉雨 (HsiaoYu)", "code": "zh-TW-HsiaoYuNeural", "gender": "Female"},
            {"name": "🇨🇳 大陸女聲 - 曉曉 (Xiaoxiao)", "code": "zh-CN-XiaoxiaoNeural", "gender": "Female"},
            {"name": "🇨🇳 大陸男聲 - 雲希 (Yunxi)", "code": "zh-CN-YunxiNeural", "gender": "Male"},
            {"name": "🇨🇳 大陸男童 - 雲健 (Yunjian)", "code": "zh-CN-YunjianNeural", "gender": "Boy"},
            {"name": "🇨🇳 大陸女童 - 曉伊 (Xiaoyi)", "code": "zh-CN-XiaoyiNeural", "gender": "Girl"},
            {"name": "🇭🇰 香港粵語 - 曉佳 (HiuGaai)", "code": "zh-HK-HiuGaaiNeural", "gender": "Female"},
            {"name": "🇭🇰 香港粵語 - 雲龍 (WanLung)", "code": "zh-HK-WanLungNeural", "gender": "Male"},
        ]
        
        en_voices = [
            {"name": "🇺🇸 美式女聲 - Jenny", "code": "en-US-JennyNeural", "gender": "Female"},
            {"name": "🇺🇸 美式男聲 - Guy", "code": "en-US-GuyNeural", "gender": "Male"},
            {"name": "🇺🇸 美式女童 - Ana", "code": "en-US-AnaNeural", "gender": "Girl"}, 
            {"name": "🇬🇧 英式女聲 - Sonia", "code": "en-GB-SoniaNeural", "gender": "Female"},
            {"name": "🇬🇧 英式男聲 - Ryan", "code": "en-GB-RyanNeural", "gender": "Male"},
            {"name": "🇬🇧 英式女童 - Maisie", "code": "en-GB-MaisieNeural", "gender": "Girl"},
        ]

        self.voice_library = {
            "zh-ALL": zh_voices,
            "en-ALL": en_voices,
            "ja-JP": [
                {"name": "🇯🇵 日語女聲 - 七海 (Nanami)", "code": "ja-JP-NanamiNeural", "gender": "Female"},
                {"name": "🇯🇵 日語男聲 - 圭太 (Keita)", "code": "ja-JP-KeitaNeural", "gender": "Male"},
            ],
            "ko-KR": [
                {"name": "🇰🇷 韓語女聲 - SunHi", "code": "ko-KR-SunHiNeural", "gender": "Female"},
                {"name": "🇰🇷 韓語男聲 - InJoon", "code": "ko-KR-InJoonNeural", "gender": "Male"},
            ],
            "th-TH": [
                {"name": "🇹🇭 泰語女聲 - Premwadee", "code": "th-TH-PremwadeeNeural", "gender": "Female"},
                {"name": "🇹🇭 泰語男聲 - Niwat", "code": "th-TH-NiwatNeural", "gender": "Male"},
            ],
            "fr-FR": [
                {"name": "🇫🇷 法語女聲 - Denise", "code": "fr-FR-DeniseNeural", "gender": "Female"},
                {"name": "🇫🇷 法語男聲 - Henri", "code": "fr-FR-HenriNeural", "gender": "Male"},
            ],
            "de-DE": [
                {"name": "🇩🇪 德語女聲 - Katja", "code": "de-DE-KatjaNeural", "gender": "Female"},
                {"name": "🇩🇪 德語男聲 - Conrad", "code": "de-DE-ConradNeural", "gender": "Male"},
            ]
        }
        
        self.lang_map = {
            "中文 (Chinese - All)": "zh-ALL",
            "English (All)": "en-ALL",
            "日本語 (Japan)": "ja-JP",
            "韓語 (Korea)": "ko-KR",
            "泰語 (Thailand)": "th-TH",
            "法語 (France)": "fr-FR",
            "德語 (Germany)": "de-DE",
        }

    def update_voice_lists(self, selected_lang_name):
        lang_code = self.lang_map.get(selected_lang_name, "zh-ALL")
        voices = self.voice_library.get(lang_code, [])
        voice_names = [v["name"] for v in voices]
        
        if not voice_names: return

        # Update Menus
        for menu in [self.menu_main, self.menu_man, self.menu_woman, self.menu_boy, self.menu_girl]:
            menu.configure(values=voice_names)
            
        # Defaults
        if self.voice_var.get() not in voice_names:
            self.voice_var.set(voice_names[0])
        
        def find_gender(g):
            return next((v["name"] for v in voices if v["gender"] == g), voice_names[0])
            
        self.voice_man_var.set(find_gender("Male"))
        self.voice_woman_var.set(find_gender("Female"))
        self.voice_boy_var.set(find_gender("Boy"))
        self.voice_girl_var.set(find_gender("Girl"))

    def get_voice_code(self, name):
         for lang_code, voices in self.voice_library.items():
             for v in voices:
                 if v['name'] == name: return v['code']
         return None

    def load_srt(self):
        srt_dir = os.path.join(self.script_dir, "Outputs", "Subtitles")
        if not os.path.exists(srt_dir): srt_dir = self.script_dir
        
        f = filedialog.askopenfilename(initialdir=srt_dir, filetypes=[("Subtitle", "*.srt")])
        if f:
            self.srt_path = f
            self.lbl_srt_name.configure(text=os.path.basename(f), text_color="white")
            self.log(f"已載入字幕: {os.path.basename(f)}")

    def run_tts_thread(self):
        # Determine Mode
        current_tab = self.current_tab_key
        if current_tab == "srt":
            if not self.srt_path:
                messagebox.showwarning("提示", "請先載入 SRT 字幕檔")
                return
            target_func = self.run_srt_dubbing
            arg = self.srt_path
        else:
            text = self.text_input.get("0.0", "end").strip()
            if not text:
                messagebox.showwarning("提示", "請輸入文字")
                return
            target_func = self.run_tts_text
            arg = text
            
        self.is_stopped = False
        self.btn_gen.configure(state="disabled")
        self.btn_play.configure(state="disabled") # Disable playback during generation
        self.btn_stop.configure(state="normal")
        threading.Thread(target=target_func, args=(arg,), daemon=True).start()

    def stop_tts(self):
        if not self.is_stopped:
            self.is_stopped = True
            self.log("⚠️ 收到中斷請求，正在停止處理...")
            self.btn_stop.configure(state="disabled", text="停止中...")

    def run_tts_text(self, text):
        try:
            self.log("⏳ 開始生成語音 (文字模式)...")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            outfile = os.path.join(self.output_dir, f"tts_{timestamp}.wav")
            outfile = self.get_unique_path(outfile)
            
            # 1. Parse Segments
            lines = text.split('\n')
            import re
            segments = []
            
            man_tag = self.role_man_var.get().strip()
            woman_tag = self.role_woman_var.get().strip()
            boy_tag = self.role_boy_var.get().strip()
            girl_tag = self.role_girl_var.get().strip()

            role_map = {
                man_tag.lower(): (self.voice_man_var.get(), self.pitch_man_var.get()),
                woman_tag.lower(): (self.voice_woman_var.get(), self.pitch_woman_var.get()),
                boy_tag.lower(): (self.voice_boy_var.get(), self.pitch_boy_var.get()),
                girl_tag.lower(): (self.voice_girl_var.get(), self.pitch_girl_var.get())
            }
            main_voice = self.voice_var.get()
            main_pitch = self.pitch_var.get()
            
            tags = [tag for tag in [man_tag, woman_tag, boy_tag, girl_tag] if tag]
            if tags:
                import re
                escaped_tags = [re.escape(tag) for tag in tags]
                tag_pattern = "|".join(escaped_tags)
                compiled_pattern = re.compile(f"^({tag_pattern}):\\s*(.*)", re.IGNORECASE)
            else:
                compiled_pattern = None
            
            for line in lines:
                line = line.strip()
                if not line: continue
                voice_name = main_voice
                pitch_val = main_pitch
                line_text = line
                
                match = compiled_pattern.match(line) if compiled_pattern else None
                if match:
                    role_key = match.group(1).lower()
                    voice_name, pitch_val = role_map.get(role_key, (main_voice, main_pitch))
                    line_text = match.group(2)
                voice_code = self.get_voice_code(voice_name)
                segments.append((line_text, voice_code, pitch_val))
                
            # 2. Generate
            temp_files = []
            rate = self.speed_var.get()
            
            for i, (seg_text, seg_voice, seg_pitch) in enumerate(segments):
                if self.is_stopped:
                    self.log("⛔ 任務已被使用者中斷！")
                    break
                
                if not seg_text: continue
                temp_f = os.path.join(self.output_dir, f"temp_{timestamp}_{i}.mp3")
                
                self.log(f"處理段落 {i+1}: {seg_text[:20]}... ({seg_voice}, {seg_pitch})")
                
                async def _gen():
                     try:
                        comm = edge_tts.Communicate(seg_text, seg_voice, rate=rate, pitch=seg_pitch)
                        await comm.save(temp_f)
                     except Exception as e:
                        raise e 
                try:
                    asyncio.run(_gen())
                except Exception as e:
                     err_str = str(e)
                     if "403" in err_str:
                         self.log(f"❌ API 403 錯誤 (段落 {i+1}): 版本過舊，請更新 edge-tts！")
                         self.log("➡️ 請在終端機執行: pip install --upgrade edge-tts")
                     elif "No audio was received" in err_str:
                         # Check for specific language mismatch
                         if "zh-" not in seg_voice and any('\u4e00' <= char <= '\u9fff' for char in seg_text):
                             voice_display_name = next((v['name'] for lang, voices in self.voice_library.items() for v in voices if v['code'] == seg_voice), seg_voice)
                             self.log(f"❌ 語言不匹配 (段落 {i+1}): 【{voice_display_name}】 無法朗讀中文內容！")
                             self.log(f"   內容: {seg_text[:10]}...")
                         else:
                             self.log(f"❌ API 錯誤 (段落 {i+1}): 無法生成音訊 (參數或內容錯誤)")
                     else:
                         self.log(f"❌ API 錯誤 (段落 {i+1}): {e}")
                     continue

                if os.path.exists(temp_f):
                    temp_files.append(temp_f)
                else:
                    self.log(f"❌ 段落 {i+1} 生成失敗 (檔案未建立)")

            # 3. Concatenate and Export as WAV
            if temp_files and not self.is_stopped:
                combined = AudioSegment.empty()
                for f in temp_files:
                    try:
                        combined += AudioSegment.from_file(f)
                    except Exception as e:
                        self.log(f"⚠️ 合併失敗 {f}: {e}")
                
                combined.export(outfile, format="wav")
                self.log(f"🎉 生成成功: {os.path.basename(outfile)}")
                self.last_output_file = outfile
                self.btn_play.configure(state="normal")
                
                # Clean memory
                del combined
                gc.collect()
            else:
                self.log("❌ 無法生成任何音訊 (可能是文字與語言不匹配)")

            time.sleep(0.5)
            
            for f in temp_files:
                if os.path.exists(f):
                    try: 
                        os.remove(f)
                    except Exception as e:
                        self.log(f"⚠️ 無法刪除暫存檔: {os.path.basename(f)}")

        except Exception as e:
            self.log(f"❌ 嚴重錯誤: {e}")
            import traceback
            print(traceback.format_exc())
        finally:
            self.btn_gen.configure(state="normal")
            self.btn_stop.configure(state="disabled", text="中斷")
            if not self.is_stopped and self.last_output_file:
                self.after(0, lambda: messagebox.showinfo("完成", "配音完成！"))

    def run_srt_dubbing(self, srt_path):
        try:
            self.log(f"⏳ 開始生成語音 (SRT 模式 - 智慧避讓重疊)...")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            base_name = os.path.splitext(os.path.basename(srt_path))[0]
            outfile = os.path.join(self.output_dir, f"{base_name}_dub_{timestamp}.wav")
            outfile = self.get_unique_path(outfile)
            
            # 1. Parse SRT
            import re
            with open(srt_path, "r", encoding="utf-8") as f:
                content = f.read().replace("\r\n", "\n").replace("\r", "\n")
            
            blocks = re.split(r'\n{2,}', content.strip())
            segments = []
            
            man_tag = self.role_man_var.get().strip()
            woman_tag = self.role_woman_var.get().strip()
            boy_tag = self.role_boy_var.get().strip()
            girl_tag = self.role_girl_var.get().strip()
            
            role_map = {
                man_tag.lower(): (self.voice_man_var.get(), self.pitch_man_var.get()),
                woman_tag.lower(): (self.voice_woman_var.get(), self.pitch_woman_var.get()),
                boy_tag.lower(): (self.voice_boy_var.get(), self.pitch_boy_var.get()),
                girl_tag.lower(): (self.voice_girl_var.get(), self.pitch_girl_var.get())
            }
            main_voice = self.voice_var.get()
            main_pitch = self.pitch_var.get()
            
            tags = [tag for tag in [man_tag, woman_tag, boy_tag, girl_tag] if tag]
            if tags:
                escaped_tags = [re.escape(tag) for tag in tags]
                tag_pattern = "|".join(escaped_tags)
                compiled_pattern = re.compile(f"^({tag_pattern}):\\s*(.*)", re.IGNORECASE)
            else:
                compiled_pattern = None
            
            def parse_time(t_str):
                t_str = t_str.strip().replace(',', '.')
                parts = t_str.split(':')
                return int(parts[0])*3600 + int(parts[1])*60 + float(parts[2])

            for block in blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                     # Check if index line exists
                     idx = 0
                     if "-->" not in lines[1]: idx = 1 # shift
                     
                     if len(lines) > idx+1 and "-->" in lines[idx+1]:
                         start_str, end_str = lines[idx+1].split("-->")
                         start_sec = parse_time(start_str)
                         end_sec = parse_time(end_str)
                         
                         text_lines = lines[idx+2:]
                         text = " ".join(text_lines)
                         text = re.sub(r'<[^>]+>', '', text)
                         
                         voice_name = main_voice
                         pitch_val = main_pitch
                         line_text = text
                         match = compiled_pattern.match(text) if compiled_pattern else None
                         if match:
                             role_key = match.group(1).lower()
                             voice_name, pitch_val = role_map.get(role_key, (main_voice, main_pitch))
                             line_text = match.group(2)
                         
                         voice_code = self.get_voice_code(voice_name)
                         segments.append({
                             "start": start_sec,
                             "end": end_sec,
                             "text": line_text,
                             "voice": voice_code,
                             "pitch": pitch_val
                         })

            if not segments:
                self.log("❌ SRT 為空或解析失敗")
                return
                
            # Calculate total duration dynamically roughly
            total_duration = segments[-1]["end"] + 10.0 # extra buffer
            full_audio = AudioSegment.silent(duration=int(total_duration * 1000))
            
            rate = self.speed_var.get()
            last_end_ms = 0 # Track insertion point
            
            for i, seg in enumerate(segments):
                if self.is_stopped:
                    self.log("⛔ 任務已被使用者中斷！")
                    break
                    
                if not seg['text']: continue
                self.log(f"[{i+1}/{len(segments)}] {seg['text'][:15]}... ({seg['voice']}, {seg['pitch']})")
                
                temp_f = os.path.join(self.output_dir, f"srt_temp_{timestamp}_{i}.mp3")
                try:
                    asyncio.run(edge_tts.Communicate(seg['text'], seg['voice'], rate=rate, pitch=seg['pitch']).save(temp_f))
                    
                    if os.path.exists(temp_f):
                        seg_audio = AudioSegment.from_file(temp_f)
                        
                        # Calculate Position Logic
                        srt_start_ms = int(seg['start'] * 1000)
                        
                        # SHIFT LOGIC: max(SRT time, End of last clip)
                        # This guarantees NO overlap.
                        # However, if TTS overlaps, it pushes this clip LATER than video.
                        actual_start_ms = max(srt_start_ms, last_end_ms)
                        
                        full_audio = full_audio.overlay(seg_audio, position=actual_start_ms)
                        
                        last_end_ms = actual_start_ms + len(seg_audio)
                        
                        os.remove(temp_f)
                    else:
                         self.log(f"⚠️ 生成失敗: {temp_f}")

                except Exception as e:
                    self.log(f"❌ 段落 {i+1} 錯誤: {e}")

            # Export
            # Trim silence at end if too long? No, keep it safe.
            if not self.is_stopped:
                full_audio.export(outfile, format="wav")
                self.log(f"🎉 配音完成: {os.path.basename(outfile)}")
                self.last_output_file = outfile
                self.btn_play.configure(state="normal")
            
            # Clean memory
            del full_audio
            gc.collect()
            time.sleep(0.5)
            self.log(f"🎉 配音完成: {os.path.basename(outfile)}")
            self.last_output_file = outfile
            self.btn_play.configure(state="normal")
            
        except Exception as e:
             self.log(f"❌ 嚴重錯誤: {e}")
             import traceback
             print(traceback.format_exc())
        finally:
             self.btn_gen.configure(state="normal")
             self.btn_stop.configure(state="disabled", text="中斷")
             if not self.is_stopped and self.last_output_file:
                 self.after(0, lambda: messagebox.showinfo("完成", "配音完成！"))

    def update_edge_tts(self):
        if not messagebox.askyesno("更新確認", "是否執行 edge-tts 組件更新？\n(這將修復 403 錯誤，需連接網路)"):
            return
            
        self.btn_update.configure(state="disabled", text="更新中...")
        self.log("🚀 開始更新 edge-tts...")
        
        def _run_update():
            try:
                if getattr(sys, 'frozen', False):
                    self.log("⚠️ 偵測到您使用的是打包過的獨立執行檔版本 (.exe)")
                    self.log("獨立執行檔無法直接透過 pip 更新內部套件。")
                    self.log("請等待作者發布最新版本的主程式，或改用 Python 原始碼執行。")
                    self.after(0, lambda: messagebox.showinfo("提示", "打包過的獨立執行檔版本無法自動更新核心套件。\n請下載作者發布的最新版主程式。"))
                    return
                
                # pip install --upgrade edge-tts
                cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "edge-tts"]
                
                # Run command
                process = subprocess.Popen(
                    cmd, 
                    stdout=subprocess.PIPE, 
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
                )
                
                stdout, stderr = process.communicate()
                
                if process.returncode == 0:
                    self.log("✅ 更新成功！")
                    self.log(stdout)
                    messagebox.showinfo("成功", "組件已更新至最新版！\n請重啟程式以確保生效。")
                else:
                    self.log("❌ 更新失敗")
                    self.log(stderr)
                    messagebox.showerror("失敗", f"更新過程中發生錯誤:\n{stderr}")
                    
            except Exception as e:
                self.log(f"❌ 執行錯誤: {e}")
                messagebox.showerror("錯誤", str(e))
            finally:
                self.btn_update.configure(state="normal", text="🔄 更新組件 (Fix 403)")
        
        threading.Thread(target=_run_update, daemon=True).start()

    def play_audio(self):
        if self.last_output_file and os.path.exists(self.last_output_file):
            os.startfile(self.last_output_file)

    def open_output_folder(self):
        if os.path.exists(self.output_dir):
            os.startfile(self.output_dir)
        else:
            messagebox.showinfo("提示", "輸出資料夾尚未建立")

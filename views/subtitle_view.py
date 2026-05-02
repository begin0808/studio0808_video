import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, font, colorchooser
import threading
import os
import sys
import time
import subprocess
import traceback
import math
import shutil
import re
from datetime import datetime
from PIL import Image, ImageTk, ImageDraw, ImageFont # pip install pillow
try:
    from deep_translator import GoogleTranslator # pip install deep-translator
except ImportError:
    GoogleTranslator = None

from views.srt_editor import SRTEditorWindow

class SubtitleView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        # Paths
        self.script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
        self.output_dir = os.path.join(self.script_dir, "Outputs", "Subtitles")
        self.tools_dir = os.path.join(self.script_dir, "tools")
        self.models_dir = os.path.join(self.script_dir, "models", "Whisper")
        
        for d in [self.output_dir, self.tools_dir, self.models_dir]:
            if not os.path.exists(d): os.makedirs(d)
            
        self.ffmpeg_exe = os.path.join(self.tools_dir, "ffmpeg.exe")
        if not os.path.exists(self.ffmpeg_exe): self.ffmpeg_exe = "ffmpeg"

        # Logic State
        self.file_list = []
        self.is_running = False
        self.is_processing = False
        self.stop_requested = False
        self.manual_srt_path = None # For manual tools
        self.current_process = None
        
        # UI Fonts
        self.font_ui = ("Microsoft JhengHei UI", 15)
        self.font_bold = ("Microsoft JhengHei UI", 15, "bold")
        self.font_title = ("Microsoft JhengHei UI", 24, "bold")

        # UI State Variables (AI)
        self.model_var = ctk.StringVar(value="large-v3 (最優)")
        self.lang_var = ctk.StringVar(value="Auto (自動偵測)")
        self.compute_mode_var = ctk.StringVar(value="Auto (自動最佳化)")  # [NEW]
        self.trans_var = ctk.StringVar(value="Auto-Translate (自動轉繁中)") # Changed to string for Mode
        # [NEW] VAD Option
        self.vad_var = ctk.BooleanVar(value=False) 
        self.bilingual_var = ctk.BooleanVar(value=False)
        self.gen_vtt_var = ctk.BooleanVar(value=False)
        self.gen_txt_var = ctk.BooleanVar(value=False)
        # [NEW] Diarization Option
        self.diarization_var = ctk.BooleanVar(value=False)
        self.burn_var = ctk.BooleanVar(value=False)

        # UI State Variables (Style - Primary)
        self.font_var = ctk.StringVar(value="Microsoft JhengHei UI")
        self.size_var = ctk.StringVar(value="24")
        self.bold_var = ctk.BooleanVar(value=True) # Changed default to True for main subtitle
        self.color_var = ctk.StringVar(value="#FFD700") # Gold default
        self.border_color_var = ctk.StringVar(value="#000000")
        self.outline_var = ctk.StringVar(value="2") # Outline default
        self.spacing_var = ctk.StringVar(value="0") # [NEW] Spacing
        self.bgbox_var = ctk.BooleanVar(value=False)
        self.bg_color_var = ctk.StringVar(value="#000000")
        self.bg_alpha_var = ctk.IntVar(value=30)
        
        # UI State Variables (Style - Secondary)
        self.sec_font_var = ctk.StringVar(value="Microsoft JhengHei UI")
        self.sec_size_var = ctk.StringVar(value="20")
        self.sec_bold_var = ctk.BooleanVar(value=False)
        self.sec_color_var = ctk.StringVar(value="#FFFFFF")
        self.sec_border_color_var = ctk.StringVar(value="#000000")
        self.sec_outline_var = ctk.StringVar(value="1")
        self.sec_spacing_var = ctk.StringVar(value="0") # [NEW] Secondary Spacing
        self.sec_bgbox_var = ctk.BooleanVar(value=False)
        self.sec_bg_color_var = ctk.StringVar(value="#000000")
        self.sec_bg_alpha_var = ctk.IntVar(value=30)

        # UI Setup
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=0) # File List (Fixed)
        self.grid_rowconfigure(3, weight=1) # Log Area (Expanded)
        
        self.create_header()
        self.create_settings()
        self.create_file_list()
        self.create_log_area()

    def create_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(15, 5))
        
        # Title removed based on feedback
        
        # GPU Status
        self.gpu_label = ctk.CTkLabel(header, text="檢查 GPU...", text_color="gray", font=self.font_ui)
        self.gpu_label.pack(side="left")
        self.check_gpu()
    
    # ... (Settings skipped) ...

    def create_file_list(self):
        list_container = ctk.CTkFrame(self)
        list_container.grid(row=2, column=0, sticky="ew", padx=20, pady=2) # Changed sticky to ew (not nsew)
        # list_container.grid_rowconfigure(0, weight=1) # REMOVED weight to stop expansion
        list_container.grid_columnconfigure(0, weight=1)
        
        # List Area (Height forced to ~40-50px)
        self.scroll_list = ctk.CTkScrollableFrame(list_container, label_text="待處理檔案列表", height=40, label_font=self.font_bold)
        self.scroll_list.grid(row=0, column=0, sticky="ew", padx=5, pady=2) # Changed sticky to ew
        
        self.no_file_label = ctk.CTkLabel(self.scroll_list, text="請加入影片或音訊檔案", text_color="gray", font=self.font_ui)
        self.no_file_label.pack(pady=5) # Reduced pady for compact view

    def create_settings(self):
        settings_frame = ctk.CTkFrame(self)
        settings_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=5)
        settings_frame.grid_columnconfigure(0, weight=1)
        settings_frame.grid_columnconfigure(1, weight=1)

        # --- Left Column: AI Parameters ---
        left_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
        
        ctk.CTkLabel(left_frame, text="[ 辨識核心 ]", font=self.font_bold).pack(anchor="w", pady=2)
        
        # Model & Lang
        r1 = ctk.CTkFrame(left_frame, fg_color="transparent")
        r1.pack(fill="x", pady=2)
        ctk.CTkLabel(r1, text="AI 模型:", font=self.font_ui).pack(side="left")
        ctk.CTkComboBox(r1, variable=self.model_var, values=["medium (中)", "large-v2 (佳)", "large-v3-turbo (優)", "large-v3 (最優)"], width=180, font=self.font_ui, dropdown_font=self.font_ui).pack(side="left", padx=5)
        
        ctk.CTkLabel(r1, text="影片語言:", font=self.font_ui).pack(side="left", padx=(10, 5))
        ctk.CTkComboBox(r1, variable=self.lang_var, values=["Auto (自動偵測)", "Chinese (中文)", "English (英文)", "Japanese (日文)", "Korean (韓文)"], width=160, font=self.font_ui, dropdown_font=self.font_ui).pack(side="left", padx=5)

        # [NEW] Compute Mode
        r1_5 = ctk.CTkFrame(left_frame, fg_color="transparent")
        r1_5.pack(fill="x", pady=2)
        ctk.CTkLabel(r1_5, text="運算模式:", font=self.font_ui).pack(side="left")
        compute_options = [
            "Auto (自動最佳化)",
            "GPU (float16) - 預設最快",
            "GPU (int8) - 節省顯存",
            "GPU (int8_float16) - 混合精度",
            "GPU (float32) - 精度測試",
            "CPU (int8) - 穩定相容",
            "CPU (float32) - 慢速精準"
        ]
        ctk.CTkComboBox(r1_5, variable=self.compute_mode_var, values=compute_options, width=310, font=self.font_ui, dropdown_font=self.font_ui).pack(side="left", padx=5)

        # Mode
        r2 = ctk.CTkFrame(left_frame, fg_color="transparent")
        r2.pack(fill="x", pady=2)
        ctk.CTkLabel(r2, text="處理模式:", font=self.font_ui).pack(side="left")
        ctk.CTkComboBox(r2, variable=self.trans_var, values=["Auto-Translate (自動轉繁中)", "Original (原文字幕)"], width=260, font=self.font_ui, dropdown_font=self.font_ui).pack(side="left", padx=5)

        # Options
        r3 = ctk.CTkFrame(left_frame, fg_color="transparent")
        r3.pack(fill="x", pady=2)
        ctk.CTkCheckBox(r3, text="VAD 濾除雜音", variable=self.vad_var, font=self.font_ui).pack(side="left", padx=(0, 10))
        ctk.CTkCheckBox(r3, text="雙語字幕 (中上原文下)", variable=self.bilingual_var, font=self.font_ui, command=self.update_preview).pack(side="left", padx=(0, 10))
        ctk.CTkCheckBox(r3, text="分辨說話者", variable=self.diarization_var, font=self.font_ui, text_color="#00E676", command=self.toggle_diarization).pack(side="left")
        
        r4 = ctk.CTkFrame(left_frame, fg_color="transparent")
        r4.pack(fill="x", pady=2)
        ctk.CTkCheckBox(r4, text="生成 VTT", variable=self.gen_vtt_var, font=self.font_ui).pack(side="left", padx=(0, 10))
        ctk.CTkCheckBox(r4, text="生成 TXT", variable=self.gen_txt_var, font=self.font_ui).pack(side="left")
        ctk.CTkCheckBox(r4, text="自動壓制影片", variable=self.burn_var, font=self.font_ui).pack(side="left", padx=(10, 0))

        # --- Right Column: Style & Appearance ---
        right_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=5)
        
        # Create Tabview for Primary/Secondary Styles
        self.style_tabs = ctk.CTkTabview(right_frame, height=170, border_width=1, border_color="#555")
        self.style_tabs.pack(fill="x", pady=(2, 0)) # Reduced bottom pady
        
        self.style_tabs.add("主字幕外觀")
        self.style_tabs.add("副字幕外觀 (原文)")
        
        # Change the font of the tab buttons
        self.style_tabs._segmented_button.configure(font=("Microsoft JhengHei UI", 15))
        
        # Build UI for Primary
        self.build_style_ui(self.style_tabs.tab("主字幕外觀"), 
                            self.font_var, self.size_var, self.bold_var, self.spacing_var,
                            self.color_var, self.border_color_var, self.outline_var, 
                            self.bgbox_var, self.bg_color_var, self.bg_alpha_var, prefix="pri")
        
        # Build UI for Secondary
        self.build_style_ui(self.style_tabs.tab("副字幕外觀 (原文)"), 
                            self.sec_font_var, self.sec_size_var, self.sec_bold_var, self.sec_spacing_var,
                            self.sec_color_var, self.sec_border_color_var, self.sec_outline_var, 
                            self.sec_bgbox_var, self.sec_bg_color_var, self.sec_bg_alpha_var, prefix="sec")

        # Preview Canvas (Bottom of Right Column)
        self.preview_frame = ctk.CTkFrame(right_frame, fg_color="#000000", height=80) # Increased height
        self.preview_frame.pack(fill="both", expand=True, pady=(0, 5)) # Use expand=True to fill remaining space
        self.preview_canvas = tk.Canvas(self.preview_frame, height=80, bg="#000000", highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True)
        
        # Trigger initial preview
        self.after(500, self.update_preview)

    def build_style_ui(self, parent, font_v, size_v, bold_v, space_v, color_v, bcolor_v, out_v, bgbox_v, bgcol_v, bgalph_v, prefix):
        # Font & Bold (Row 1)
        sr1 = ctk.CTkFrame(parent, fg_color="transparent")
        sr1.pack(fill="x", pady=2)
        
        btn_font = ctk.CTkButton(sr1, text=f"🔤 {font_v.get()}", command=lambda: self.open_font_picker_var(font_v, btn_font), font=self.font_ui, width=150, fg_color="#444444")
        btn_font.pack(side="left", padx=(0, 5))
        
        self.create_color_picker(sr1, "文字", color_v)
        
        vals_size = [str(x) for x in range(12, 30, 2)]
        combo_size = ctk.CTkComboBox(sr1, variable=size_v, values=vals_size, width=60, font=self.font_ui, command=self.update_preview)
        combo_size.pack(side="left", padx=5)
        combo_size.bind("<Return>", lambda e: self.update_preview())
        ctk.CTkCheckBox(sr1, text="粗體", variable=bold_v, font=self.font_ui, width=50, command=self.update_preview).pack(side="left", padx=5)
        
        ctk.CTkLabel(sr1, text="間距:", font=self.font_ui).pack(side="left", padx=(5, 2))
        ctk.CTkComboBox(sr1, variable=space_v, values=["0", "2", "4", "6", "8", "10", "12", "15"], width=60, font=self.font_ui, command=self.update_preview).pack(side="left", padx=2)
        
        # Outline (Row 2)
        sr2 = ctk.CTkFrame(parent, fg_color="transparent")
        sr2.pack(fill="x", pady=2)
        self.create_color_picker(sr2, "邊框", bcolor_v)
        ctk.CTkLabel(sr2, text="粗細:", font=self.font_ui).pack(side="left", padx=(5, 2))
        ctk.CTkComboBox(sr2, variable=out_v, values=["0", "1", "2", "3", "4", "5"], width=60, font=self.font_ui, command=self.update_preview).pack(side="left", padx=2)
        
        # Background (Row 3)
        sr3 = ctk.CTkFrame(parent, fg_color="transparent")
        sr3.pack(fill="x", pady=2)
        ctk.CTkCheckBox(sr3, text="底框", variable=bgbox_v, font=self.font_ui, width=60, command=self.update_preview).pack(side="left", padx=(0, 5))
        self.create_color_picker(sr3, "顏色", bgcol_v)
        ctk.CTkLabel(sr3, text="透明度:", font=self.font_ui).pack(side="left", padx=5)
        
        lbl_alpha_val = ctk.CTkLabel(sr3, text=str(bgalph_v.get()), width=30, font=self.font_ui)
        def bg_alpha_update(v, lbl=lbl_alpha_val, var=bgalph_v):
            var.set(int(v))
            lbl.configure(text=str(int(v)))
            self.update_preview()
            
        slider_alpha = ctk.CTkSlider(sr3, from_=0, to=100, number_of_steps=100, width=100, command=bg_alpha_update)
        slider_alpha.set(bgalph_v.get())
        slider_alpha.pack(side="left", padx=5)
        lbl_alpha_val.pack(side="left", padx=0)

    def create_color_picker(self, parent, label, var):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        f.pack(side="left", padx=(0, 10))
        ctk.CTkLabel(f, text=f"{label}:", font=self.font_ui).pack(side="left", padx=(0, 2))
        
        btn = ctk.CTkButton(f, text="", width=24, height=24, border_width=1, border_color="#888", 
                            fg_color=var.get(), command=lambda: self.pick_color(var, btn))
        btn.pack(side="left")
        
        # Keep button color synced
        var.trace_add("write", lambda *args: btn.configure(fg_color=var.get()))

    def pick_color(self, var, btn):
        color = colorchooser.askcolor(color=var.get(), title="選擇顏色")[1]
        if color:
            var.set(color)
            btn.configure(fg_color=color)
            self.update_preview()

    def toggle_diarization(self):
        if self.diarization_var.get():
            # Check if token exists
            token_path = os.path.join(self.script_dir, "models", "hf_token.txt")
            if not os.path.exists(token_path):
                # Custom Window for Dialog to ensure Font control
                dialog = ctk.CTkToplevel(self)
                dialog.title("Hugging Face Token")
                dialog.geometry("450x250")
                dialog.transient(self.winfo_toplevel())
                dialog.grab_set()
                
                # Center it
                dialog.update_idletasks()
                x = self.winfo_toplevel().winfo_x() + (self.winfo_toplevel().winfo_width() // 2) - (450 // 2)
                y = self.winfo_toplevel().winfo_y() + (self.winfo_toplevel().winfo_height() // 2) - (250 // 2)
                dialog.geometry(f"+{x}+{y}")

                lbl = ctk.CTkLabel(dialog, text="請輸入您的 Hugging Face Access Token:\n(這是使用 Pyannote AI 說話者辨識必須的，\n請確保您已同意模型條款)", font=("Microsoft JhengHei UI", 15))
                lbl.pack(pady=20)
                
                entry = ctk.CTkEntry(dialog, width=350, font=("Microsoft JhengHei UI", 15))
                entry.pack(pady=10)
                
                def on_confirm():
                    token = entry.get()
                    if token and token.startswith("hf_"):
                        with open(token_path, "w") as f:
                            f.write(token.strip())
                        messagebox.showinfo("成功", "Token 已儲存！")
                        dialog.destroy()
                    else:
                        messagebox.showwarning("警告", "未提供有效的 Token (需以 hf_ 開頭)，已取消勾選。")
                        self.diarization_var.set(False)
                        dialog.destroy()
                        
                def on_cancel():
                    self.diarization_var.set(False)
                    dialog.destroy()

                btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
                btn_frame.pack(pady=10)
                ctk.CTkButton(btn_frame, text="確認", font=("Microsoft JhengHei UI", 15), command=on_confirm).pack(side="left", padx=10)
                ctk.CTkButton(btn_frame, text="取消", font=("Microsoft JhengHei UI", 15), fg_color="gray", command=on_cancel).pack(side="left", padx=10)
                
                # Wait for window to close before continuing
                self.wait_window(dialog)
            else:
                pass # Token already exists


    def open_font_picker_var(self, font_var, btn):
        dialog = ctk.CTkToplevel(self)
        dialog.title("選擇字體")
        dialog.geometry("300x400")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        all_fonts = sorted(list(font.families()))
        
        # Listbox for fast scrolling
        frame = ctk.CTkFrame(dialog)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        scroll = ctk.CTkScrollbar(frame)
        scroll.pack(side="right", fill="y")
        
        listbox = tk.Listbox(frame, font=("Microsoft JhengHei UI", 12), yscrollcommand=scroll.set, bd=0, highlightthickness=0)
        listbox.pack(side="left", fill="both", expand=True)
        scroll.configure(command=listbox.yview)
        
        for f in all_fonts:
            # Filter standard MS fonts, ignore weird symbols
            if not f.startswith("@"):
                listbox.insert("end", f)

        def on_select():
            sel = listbox.curselection()
            if sel:
                sel_font = listbox.get(sel[0])
                font_var.set(sel_font)
                btn.configure(text=f"🔤 {sel_font}")
                self.update_preview()
            dialog.destroy()

        ctk.CTkButton(dialog, text="確認", command=on_select, font=self.font_ui).pack(pady=10)
        
        # Double click to select
        listbox.bind("<Double-Button-1>", lambda e: on_select())

    def update_preview(self, *args):
        # Schedule update to avoid rapid fires
        if hasattr(self, '_preview_timer'):
            self.after_cancel(self._preview_timer)
        self._preview_timer = self.after(100, self.draw_preview)

    def draw_preview(self):
        w = self.preview_canvas.winfo_width()
        h = self.preview_canvas.winfo_height()
        if w <= 1: w = 400
        if h <= 1: h = 60
        
        # Refresh background image logic inside draw_preview
        img_path = os.path.join(self.script_dir, "assets", "preview_bg.jpg")
        if os.path.exists(img_path):
            bg_img = Image.open(img_path).resize((w, h), Image.Resampling.LANCZOS)
        else:
            bg_img = Image.new('RGB', (w, h), color=(50, 50, 50))
            
        draw = ImageDraw.Draw(bg_img, 'RGBA')
        
        # Helper to draw a single line of subtitle
        def _draw_line(text, font_name, size_str, is_bold, text_color, out_width_str, out_color, bg_box, bg_color, bg_alpha, spacing_str, center_y):
            # 1. Load Font
            try:
                font_size = int(size_str)
                f_path = "arial.ttf"
                
                fn_lower = font_name.lower().replace(" ", "")
                f_path = self.get_system_font_path(font_name, is_bold=is_bold)
                if not f_path:
                    if "jhenghei" in fn_lower or "正黑" in font_name:
                        f_path = "msjhbd.ttc" if is_bold else "msjh.ttc"
                    elif "yahei" in fn_lower or "微软雅黑" in font_name:
                        f_path = "msyhbd.ttc" if is_bold else "msyh.ttc"
                    elif "mingliu" in fn_lower or "細明體" in font_name:
                        f_path = "mingliub.ttc" if is_bold else "mingliu.ttc"
                    elif "kai" in fn_lower or "楷" in font_name:
                        f_path = "kaiu.ttf" if "標楷" in font_name or "dfkai" in fn_lower else "simkai.ttf"
                    elif "simsun" in fn_lower or "宋體" in font_name or "宋体" in font_name:
                        f_path = "simsunb.ttf" if is_bold else "simsun.ttc"
                    elif "simhei" in fn_lower or "黑體" in font_name or "黑体" in font_name:
                        f_path = "simhei.ttf"
                    elif "arial" in fn_lower:
                        f_path = "arialbd.ttf" if is_bold else "arial.ttf"
                    else:
                        f_path = font_name.replace(" ", "") + ".ttf"


                try:
                    ttf = ImageFont.truetype(f_path, font_size)
                except OSError:
                    # Final fallback if font file not found
                    ttf = ImageFont.truetype("msjh.ttc" if "msjh" not in f_path else "arial.ttf", font_size)
            except Exception as e:
                self.log(f"[預覽] 字體載入失敗 ({font_name}): {e}")
                ttf = ImageFont.load_default()
                
            # 2. Measure Text
            try: char_space = int(spacing_str)
            except: char_space = 0
            
            # Measure each char to find total width
            char_boxes = []
            tw = 0
            th = 0
            for c in text:
                left, top, right, bottom = draw.textbbox((0, 0), c, font=ttf)
                cw = right - left
                ch = bottom - top
                char_boxes.append((c, cw, ch))
                tw += cw + char_space
            
            if len(text) > 0:
                tw -= char_space # remove trailing space
                th = max([b[2] for b in char_boxes]) if char_boxes else 0
                
            x = (w - tw) / 2
            y = center_y - (th / 2)
            
            # 3. Draw Background Box
            if bg_box:
                pad = 4
                # Convert hex to RGB + Alpha
                r = int(bg_color[1:3], 16)
                g = int(bg_color[3:5], 16)
                b = int(bg_color[5:7], 16)
                alpha = int((bg_alpha / 100.0) * 255)
                draw.rectangle([x - pad, y - pad, x + tw + pad, y + th + pad], fill=(r, g, b, alpha))
            
            # 4 & 5. Draw Outline and Text character by character
            out_w = int(out_width_str)
            curr_x = x
            for c, cw, ch in char_boxes:
                # Poor man's outline
                if out_w > 0:
                    for dx in range(-out_w, out_w + 1):
                        for dy in range(-out_w, out_w + 1):
                            if dx*dx + dy*dy <= out_w*out_w:
                                draw.text((curr_x + dx, y + dy), c, font=ttf, fill=out_color)
                # Main text
                draw.text((curr_x, y), c, font=ttf, fill=text_color)
                curr_x += cw + char_space

        
        if self.bilingual_var.get():
            # Draw Primary (Top)
            _draw_line("這裡是一句中文測試", self.font_var.get(), self.size_var.get(), self.bold_var.get(), self.color_var.get(), 
                       self.outline_var.get(), self.border_color_var.get(), self.bgbox_var.get(), self.bg_color_var.get(), self.bg_alpha_var.get(), self.spacing_var.get(), h * 0.35)
            # Draw Secondary (Bottom)
            _draw_line("Here is an English subtitle test", self.sec_font_var.get(), self.sec_size_var.get(), self.sec_bold_var.get(), self.sec_color_var.get(), 
                       self.sec_outline_var.get(), self.sec_border_color_var.get(), self.sec_bgbox_var.get(), self.sec_bg_color_var.get(), self.sec_bg_alpha_var.get(), self.sec_spacing_var.get(), h * 0.7)
        else:
            # Draw Single (Center)
            _draw_line("這裡是一句中文測試", self.font_var.get(), self.size_var.get(), self.bold_var.get(), self.color_var.get(), 
                       self.outline_var.get(), self.border_color_var.get(), self.bgbox_var.get(), self.bg_color_var.get(), self.bg_alpha_var.get(), self.spacing_var.get(), h / 2)
            
            
        self.preview_photo = ImageTk.PhotoImage(bg_img)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(0, 0, image=self.preview_photo, anchor="nw")

    def create_file_list(self):
        # Enforce fixed height of 180px for the entire container (List + Buttons)
        # This allocates ~140px for List and ~40px for Buttons
        self.list_container = ctk.CTkFrame(self, height=180)
        self.list_container.grid(row=2, column=0, sticky="ew", padx=20, pady=2)
        self.list_container.grid_propagate(False) # Stop automatic expansion
        
        self.list_container.grid_rowconfigure(0, weight=1) # List takes available space
        self.list_container.grid_rowconfigure(1, weight=0) # Buttons take fixed space
        self.list_container.grid_columnconfigure(0, weight=1)
        
        # List Area
        self.scroll_list = ctk.CTkScrollableFrame(self.list_container, label_text="待處理檔案列表", label_font=self.font_bold)
        self.scroll_list.grid(row=0, column=0, sticky="nsew", padx=5, pady=(5, 0))
        
        self.no_file_label = ctk.CTkLabel(self.scroll_list, text="請加入影片或音訊檔案", text_color="gray", font=self.font_ui)
        self.no_file_label.pack(pady=5)
        
        # Buttons below list
        self.btn_frame = ctk.CTkFrame(self.list_container, fg_color="transparent")
        self.btn_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        
        self.btn_add = ctk.CTkButton(self.btn_frame, text="加入檔案", command=self.add_files, fg_color="#3949AB", font=self.font_ui)
        self.btn_add.pack(side="left", padx=5)
        
        self.btn_clear = ctk.CTkButton(self.btn_frame, text="清空列表", command=self.clear_files, fg_color="#424242", width=80, font=self.font_ui)
        self.btn_clear.pack(side="left", padx=5)
        
        # Start Process
        self.btn_process = ctk.CTkButton(self.btn_frame, text="開始生成字幕", command=self.start_thread, 
                                         fg_color="#E91E63", hover_color="#C2185B", font=("Microsoft JhengHei UI", 15, "bold"), width=140)
        self.btn_process.pack(side="left", padx=20)
        
        # --- Manual Tools (Right of Start) ---
        self.btn_select_srt = ctk.CTkButton(self.btn_frame, text="選擇字幕", command=self.select_srt, fg_color="#E67E22", font=self.font_ui, width=100)
        self.btn_select_srt.pack(side="left", padx=5)

        self.btn_edit_srt = ctk.CTkButton(self.btn_frame, text="編輯字幕", command=self.open_srt_editor, fg_color="#16A085", font=self.font_ui, width=100)
        self.btn_edit_srt.pack(side="left", padx=5)

        self.btn_burn_manual = ctk.CTkButton(self.btn_frame, text="壓制影片", command=self.start_burn_thread, fg_color="#8E44AD", font=self.font_ui, width=100, state="disabled")
        self.btn_burn_manual.pack(side="left", padx=5)
        
        self.btn_stop = ctk.CTkButton(self.btn_frame, text="中斷", command=self.stop_process, width=80, fg_color="#D32F2F", state="disabled", font=self.font_ui)
        self.btn_stop.pack(side="right", padx=5)

    def create_log_area(self):
        log_frame = ctk.CTkFrame(self) # Removed fixed height to let it expand
        log_frame.grid(row=3, column=0, sticky="nsew", padx=20, pady=(5, 20))
        log_frame.grid_rowconfigure(2, weight=1) # Log box row
        log_frame.grid_columnconfigure(0, weight=1)
        
        # Status Layout
        status_frame = ctk.CTkFrame(log_frame, fg_color="transparent")
        status_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(0, 5))
        
        # Progress Bar on Top
        self.pbar = ctk.CTkProgressBar(status_frame, height=10, progress_color="#ffa000")
        self.pbar.pack(fill="x", padx=10, pady=(10, 5))
        self.pbar.set(0)
        
        # Labels Below
        self.status_label = ctk.CTkLabel(status_frame, text="就緒", anchor="w", font=self.font_ui)
        self.status_label.pack(side="left", padx=10, pady=(0, 5))
        
        self.percent_label = ctk.CTkLabel(status_frame, text="0%", font=self.font_ui, text_color="#ffa000")
        self.percent_label.pack(side="right", padx=10, pady=(0, 5))
        
        self.log_box = ctk.CTkTextbox(log_frame, font=self.font_ui, fg_color="#000000")
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.log_box.configure(state="disabled")
        
        ctk.CTkButton(log_frame, text="開啟輸出資料夾", command=lambda: os.startfile(self.output_dir), width=150, height=28, font=self.font_ui, fg_color="#4CAF50", hover_color="#388E3C", text_color="white").place(relx=1.0, rely=1.0, anchor="se", x=-15, y=-10)

    # --- Logic ---

    def check_gpu(self):
        try:
            from utils.gpu_utils import safe_check_cuda
            cuda_ok, info = safe_check_cuda()
            if cuda_ok:
                self.gpu_label.configure(text=f"GPU: {info} (CUDA)", text_color="#00E676")
                self.device = "cuda"
                self.compute_type = "float16"
            else:
                self.gpu_label.configure(text=f"GPU: {info} (使用 CPU mode)", text_color="#FF5252")
                self.device = "cpu"
                self.compute_type = "int8"
        except Exception:
            self.gpu_label.configure(text="GPU: 偵測失敗 (使用 CPU mode)", text_color="gray")
            self.device = "cpu"
            self.compute_type = "int8"

    def update_progress_ui(self, val):
        self.pbar.set(val)
        self.percent_label.configure(text=f"{int(val*100)}%")

    def log(self, msg):
        self.after(0, self._log_safe, msg)

    def _log_safe(self, msg):
        self.status_label.configure(text=msg)
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{time.strftime('%H:%M:%S')}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        print(msg)

    def open_font_picker(self):
        top = ctk.CTkToplevel(self)
        top.geometry("400x500")
        top.title("選擇字型 (Font Picker)")
        top.attributes("-topmost", True)
        
        # Search
        f_search = ctk.CTkFrame(top, fg_color="transparent")
        f_search.pack(fill="x", padx=10, pady=10)
        entry_search = ctk.CTkEntry(f_search, placeholder_text="搜尋字型...", font=self.font_ui)
        entry_search.pack(fill="x")
        
        scroll = ctk.CTkScrollableFrame(top)
        scroll.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Load Fonts
        all_fonts = sorted(list(set(font.families())))
        all_fonts = [f for f in all_fonts if not f.startswith("@")]
        
        # Prioritize
        common = ["Microsoft JhengHei UI", "Microsoft JhengHei", "Microsoft YaHei", "Arial", "Times New Roman"]
        fonts = [f for f in common if f in all_fonts] + [f for f in all_fonts if f not in common]
        
        self.font_btns = []
        
        def filter_fonts(val=""):
            for btn in self.font_btns: btn.destroy()
            self.font_btns.clear()
            
            for f in fonts:
                if val.lower() in f.lower():
                    btn = ctk.CTkButton(scroll, text=f, font=("Microsoft JhengHei UI", 12), 
                                        fg_color="transparent", border_width=1, border_color="#555", anchor="w",
                                        command=lambda name=f: [self.font_var.set(name), self.btn_font.configure(text=f"🔤 {name}"), self.update_preview(), top.destroy()])
                    btn.pack(fill="x", pady=2)
                    self.font_btns.append(btn)
        
        entry_search.bind("<KeyRelease>", lambda e: filter_fonts(entry_search.get()))
        filter_fonts()

    def get_system_font_path(self, font_name, is_bold=False):
        import winreg
        paths = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
        ]
        
        # Simplify search
        search_key = font_name.lower().replace(" ", "")
        best_val = None
        
        for hkey, subkey in paths:
            try:
                with winreg.OpenKey(hkey, subkey) as key:
                    i = 0
                    while True:
                        try:
                            name, val, _ = winreg.EnumValue(key, i)
                            name_norm = name.lower().replace(" ", "").replace("(truetype)", "").strip()
                            if search_key in name_norm:
                                # Check bold
                                if is_bold and ("bold" in name_norm or "bd" in name_norm):
                                    return self._resolve_font_path(val)
                                if not best_val: best_val = val
                        except OSError: break
                        i += 1
            except: pass
            
        return self._resolve_font_path(best_val) if best_val else None

    def _resolve_font_path(self, val):
        if not val: return None
        if os.path.isabs(val) and os.path.exists(val): return val
        
        # Check standard dirs
        dirs = [
            r"C:\Windows\Fonts",
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "Windows", "Fonts")
        ]
        for d in dirs:
            p = os.path.join(d, val)
            if os.path.exists(p): return p
        return None

    def add_files(self):
        default_dir = os.path.join(self.script_dir, "Outputs", "Downloads")
        if not os.path.exists(default_dir): default_dir = self.script_dir
        
        files = filedialog.askopenfilenames(initialdir=default_dir, filetypes=[("Media", "*.mp4 *.mkv *.mp3 *.wav *.flac *.m4a *.aac *.ogg *.wma *.mov *.avi *.webm *.ts")])
        if files:
            self.no_file_label.pack_forget()
            for f in files:
                if f not in self.file_list:
                    self.file_list.append(f)
                    ctk.CTkLabel(self.scroll_list, text=f"📄 {os.path.basename(f)}", anchor="w", font=self.font_ui).pack(fill="x", padx=10)

    def clear_files(self):
        self.file_list.clear()
        for w in self.scroll_list.winfo_children(): w.destroy()
        self.no_file_label.pack(pady=40)

    def stop_process(self):
        if self.is_processing:
            self.stop_requested = True
            self.log("🛑 正在停止...")
            self.btn_stop.configure(state="disabled")

    def start_thread(self):
        if not self.file_list: return messagebox.showwarning("提示", "請先加入檔案")
        
        self.is_processing = True
        self.stop_requested = False
        self.btn_process.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        # self.btn_add.configure(state="disabled") # Allow adding? No, better safe
        # self.btn_clear.configure(state="disabled")
        self.pbar.configure(mode="indeterminate")
        self.pbar.start()
        
        threading.Thread(target=self.run_process, daemon=True).start()

    def run_process(self):
        try:
            self.log("正在載入 Whisper 模型 (faster-whisper)...")
            from faster_whisper import WhisperModel
            import shutil
            import opencc
            from deep_translator import GoogleTranslator
            
            # Strip description from model name (e.g. "large-v3 (最優)" -> "large-v3")
            model_size = self.model_var.get().split(" ")[0]
            
            # [NEW] 解析運算模式
            import torch
            mode_val = self.compute_mode_var.get()
            
            # 使用安全 CUDA 檢查來決定裝置
            from utils.gpu_utils import safe_check_cuda
            cuda_ok, _cuda_info = safe_check_cuda()
            
            if "Auto" in mode_val:
                self.device = "cuda" if cuda_ok else "cpu"
                self.compute_type = "float16" if self.device == "cuda" else "int8"
            elif "GPU" in mode_val:
                if cuda_ok:
                    self.device = "cuda"
                    if "int8_float16" in mode_val: self.compute_type = "int8_float16"
                    elif "int8" in mode_val: self.compute_type = "int8"
                    elif "float32" in mode_val: self.compute_type = "float32"
                    else: self.compute_type = "float16"
                else:
                    self.log(f"⚠️ 您選擇了 GPU 模式，但 CUDA 無法使用 ({_cuda_info})，自動切換至 CPU...")
                    self.device = "cpu"
                    self.compute_type = "int8"
                    self.gpu_label.configure(text=f"GPU: {_cuda_info} (使用 CPU)", text_color="#FF5252")
            elif "CPU" in mode_val:
                self.device = "cpu"
                self.compute_type = "float32" if "float32" in mode_val else "int8"
            else:
                self.device = "cuda" if cuda_ok else "cpu"
                self.compute_type = "float16" if self.device == "cuda" else "int8"

            try:
                model = WhisperModel(model_size, device=self.device, compute_type=self.compute_type, download_root=self.models_dir)
            except (RuntimeError, Exception) as e:
                err_str = str(e).lower()
                # 捕捉所有 CUDA 相關錯誤：OOM、缺少函式庫、kernel 不相容、驅動問題等
                cuda_errors = ["out of memory", "cublas", "cudnn", "cuda error", "no kernel image",
                               "cuda driver", "insufficient", "not compiled", "cuda runtime",
                               "cuda_error", "cusolver", "cufft", "curand", "nccl"]
                is_cuda_error = any(kw in err_str for kw in cuda_errors)
                
                if is_cuda_error and self.device == "cuda":
                    if "out of memory" in err_str:
                        self.log("❌ 顯示卡記憶體不足 (VRAM OOM)！無法載入模型。")
                    elif "cublas" in err_str or "cudnn" in err_str:
                        self.log("⚠️ 偵測到缺少 NVIDIA 函式庫 (cuBLAS/cuDNN)...")
                    elif "no kernel image" in err_str:
                        self.log("⚠️ 偵測到顯卡架構不相容 (GPU 太新或 CUDA 版本不匹配)...")
                    elif "driver" in err_str or "insufficient" in err_str:
                        self.log("⚠️ 偵測到 CUDA 驅動程式問題...")
                    else:
                        self.log(f"⚠️ 偵測到 CUDA 相關錯誤: {e}")
                    
                    self.log("⚠️ 自動切換至 CPU 模式重試...")
                    
                    # Fallback to CPU
                    try:
                        import gc
                        gc.collect()
                        from utils.gpu_utils import safe_cuda_empty_cache
                        safe_cuda_empty_cache()
                    except: pass
                    
                    self.device = "cpu"
                    self.compute_type = "int8"
                    self.gpu_label.configure(text="Mode: CPU (Fallback)", text_color="orange")
                    model = WhisperModel(model_size, device="cpu", compute_type="int8", download_root=self.models_dir)
                    self.log("✅ CPU 模式接手成功！")
                else:
                    raise e
            
            # Log current device status
            device_name = "GPU (CUDA)" if self.device == "cuda" else "CPU"
            self.log(f"✅ 模型載入成功！目前模式: {device_name}")

            cc = opencc.OpenCC('s2t')
            
            self.pbar.stop()
            self.pbar.configure(mode="determinate")
            total = len(self.file_list)
            
            for i, file_path in enumerate(self.file_list):
                if self.stop_requested: break
                
                filename = os.path.basename(file_path)
                self.log(f"正在處理 ({i+1}/{total}): {filename}")
                self.after(0, lambda v=(i/total): self.update_progress_ui(v))
                
                # Transcribe
                lang_sel = self.lang_var.get()
                lang_map = {
                    "Auto (自動偵測)": None,
                    "Chinese (中文)": "zh",
                    "English (英文)": "en",
                    "Japanese (日文)": "ja",
                    "Korean (韓文)": "ko"
                }
                lang_arg = lang_map.get(lang_sel)
                
                # --- [NEW] Pyannote Speaker Diarization ---
                diarization_result = None
                if self.diarization_var.get() and not self.stop_requested:
                    self.log("... 正在執行 AI 說話者辨識 (這可能需要幾分鐘)")
                    try:
                        from pyannote.audio import Pipeline
                        import torch
                        token_path = os.path.join(self.script_dir, "models", "hf_token.txt")
                        token = open(token_path, "r").read().strip() if os.path.exists(token_path) else None
                        
                        import huggingface_hub.file_download
                        
                        _orig_download = huggingface_hub.file_download.hf_hub_download
                        def _patched_download(*args, **kwargs):
                            if "use_auth_token" in kwargs:
                                kwargs["token"] = kwargs.pop("use_auth_token")
                            return _orig_download(*args, **kwargs)
                            
                        # apply patch to all possible import locations
                        import unittest.mock
                        patcher1 = unittest.mock.patch("huggingface_hub.file_download.hf_hub_download", _patched_download)
                        patcher2 = unittest.mock.patch("huggingface_hub.hf_hub_download", _patched_download)
                        patcher3 = unittest.mock.patch("pyannote.audio.core.pipeline.hf_hub_download", _patched_download)
                        patcher4 = unittest.mock.patch("pyannote.audio.core.model.hf_hub_download", _patched_download)
                        
                        patcher1.start()
                        patcher2.start()
                        try:
                            patcher3.start()
                        except: pass
                        try:
                            patcher4.start()
                        except: pass

                        try:
                            from pyannote.audio.core.task import Specifications, Problem
                            from pyannote.audio.core.task import Resolution # Adding Resolution just in case
                            from pytorch_metric_learning.distances import CosineSimilarity
                            torch.serialization.add_safe_globals([
                                torch.torch_version.TorchVersion,
                                Specifications,
                                Problem,
                                Resolution,
                                CosineSimilarity
                            ])
                        except Exception:
                            pass # Older torch versions might not have this function or need it

                        if token:
                            os.environ["HF_TOKEN"] = token
                            

                        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=token)
                        if self.device == "cuda":
                            # Safe move to GPU if VRAM allows
                            try:
                                pipeline.to(torch.device("cuda"))
                            except Exception as gpu_err:
                                self.log(f"⚠️ Pyannote 無法使用 GPU ({gpu_err})，將使用 CPU 進行辨識...")
                                self.device = "cpu"  # 後續也使用 CPU
                        
                        temp_dir = os.path.join(self.script_dir, "temp")
                        if not os.path.exists(temp_dir): os.makedirs(temp_dir)
                        temp_wav = os.path.join(temp_dir, "temp_diar.wav")
                        
                        # Extract Mono 16kHz audio for pyannote
                        subprocess.run([self.ffmpeg_exe, "-y", "-i", file_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_wav], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        
                        diarization_result = pipeline(temp_wav)
                        
                        try: os.remove(temp_wav)
                        except: pass
                        
                        import gc
                        del pipeline
                        gc.collect()
                        if self.device == "cuda":
                            from utils.gpu_utils import safe_cuda_empty_cache
                            safe_cuda_empty_cache()
                        
                        self.log("✅ 說話者分析完畢")
                    except Exception as de:
                        self.log(f"⚠️ 說話者辨識發生錯誤 (將忽略此步驟): {de}")
                        self.log("⚠️ 提示：您可能需要安裝 Pyannote (pip install pyannote.audio) 或您的 Token 尚未同意 Hugging Face 上的 pyannote 模型授權條款。")
                
                try:
                    self.log("... 正在進行 AI 轉錄 (這可能需要一點時間)")
                    segments_gen, info = model.transcribe(
                        file_path, 
                        language=lang_arg, 
                        beam_size=5, 
                        condition_on_previous_text=False,
                        temperature=0,
                        vad_filter=self.vad_var.get(),
                        vad_parameters=dict(min_silence_duration_ms=500, threshold=0.3)
                    )
                    # [CRITICAL UPDATE] Manual iteration to support STOP
                    segments = []
                    last_log_time = -1
                    total_duration = info.duration
                    for seg in segments_gen:
                        if self.stop_requested:
                            self.log("🛑 停止請求已收到，正在中斷轉錄...")
                            break
                        segments.append(seg)
                        
                        # Print progress every 10 seconds of audio duration
                        if int(seg.end) // 10 > last_log_time:
                            last_log_time = int(seg.end) // 10
                            # format time
                            m, s = divmod(int(seg.end), 60)
                            h, m = divmod(m, 60)
                            percent = min(100, int((seg.end / total_duration) * 100)) if total_duration > 0 else 0
                            self.log(f"  - 處理進度: {h:02d}:{m:02d}:{s:02d} -- {percent}%")
                    
                except RuntimeError as e:
                    if self.stop_requested:
                        self.log("🛑 停止請求已收到，正在中斷...")
                        break

                    if "out of memory" in str(e).lower():
                        self.log("❌ 顯示卡記憶體不足 (VRAM OOM)！")
                        self.log("⚠️ 正在自動切換至 CPU 模式重試 (速度會較慢)...")
                        
                        # Fallback to CPU
                        try:
                            # 1. Release VRAM (Best effort)
                            import gc
                            del model
                            gc.collect()
                            if self.device == "cuda":
                                from utils.gpu_utils import safe_cuda_empty_cache
                                safe_cuda_empty_cache()
                            
                            # 2. Reload Model on CPU
                            model = WhisperModel(model_size, device="cpu", compute_type="int8", download_root=self.models_dir)
                            self.gpu_label.configure(text="Mode: CPU (Fallback)", text_color="orange")
                            
                            # 3. Retry
                            self.log("... 正在使用 CPU 重試轉錄")
                            segments_gen, info = model.transcribe(
                                file_path, 
                                language=lang_arg, 
                                beam_size=5, 
                                condition_on_previous_text=False,
                                temperature=0,
                                vad_filter=self.vad_var.get(),
                                vad_parameters=dict(min_silence_duration_ms=500, threshold=0.3)
                            )
                            # CPU Retry Loop
                            segments = []
                            last_log_time = -1
                            total_duration = info.duration
                            for seg in segments_gen:
                                if self.stop_requested:
                                    self.log("🛑 停止請求已收到，正在中斷轉錄...")
                                    break
                                segments.append(seg)
                                
                                # Print progress every 10 seconds of audio duration
                                if int(seg.end) // 10 > last_log_time:
                                    last_log_time = int(seg.end) // 10
                                    m, s = divmod(int(seg.end), 60)
                                    h, m = divmod(m, 60)
                                    percent = min(100, int((seg.end / total_duration) * 100)) if total_duration > 0 else 0
                                    self.log(f"  - 處理進度: {h:02d}:{m:02d}:{s:02d} -- {percent}%")

                            self.log("✅ CPU 模式接手成功！")
                        except Exception as fallback_e:
                            self.log(f"❌ CPU 切換失敗: {fallback_e}")
                            err_msg = str(fallback_e).lower()
                            if "mkl_malloc" in err_msg or "memoryerror" in err_msg or "alloc" in err_msg:
                                friendly_msg = "您的電腦記憶體不足 (System RAM OOM)，無法載入此大型模型。\n\n建議改用 'medium (中)' 或 'large-v2 (佳)' 模型再試一次。"
                                messagebox.showerror("記憶體不足", friendly_msg)
                                self.log("💡 建議：改用較小的模型 (medium 或 large-v2)")
                            else:
                                messagebox.showerror("嚴重錯誤", f"GPU 記憶體不足且無法切換至 CPU。\n{fallback_e}")
                            return
                    else:
                        raise e
                
                self.log(f"  - 偵測語言: {info.language}")
                
                srt_content = ""
                burn_srt_content = "" # For burning (with style tags)
                vtt_content = "WEBVTT\n\n"
                txt_content = ""
                
                idx = 1
                
                # Translator setup
                mode_sel = self.trans_var.get()
                translator = None
                if "Auto-Translate" in mode_sel and GoogleTranslator:
                    translator = GoogleTranslator(source='auto', target='zh-TW')

                for segment in segments:
                    if self.stop_requested: break
                    
                    start = self.format_time(segment.start)
                    end = self.format_time(segment.end)
                    text = segment.text.strip()
                    
                    final_text = text
                    burn_text = text
                    
                    # Translation Logic
                    if translator and info.language != "zh" and "Auto" in mode_sel:
                        trans_text = ""
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                trans_text = translator.translate(text)
                                # deep-translator sometimes returns scraped error pages instead of raising an exception
                                if trans_text and "Server Error" in trans_text and "Error 50" in trans_text:
                                    raise ValueError("Google Translate Server Error")
                                
                                if self.trans_var.get(): trans_text = cc.convert(trans_text)
                                break
                            except Exception as e:
                                if attempt < max_retries - 1:
                                    import time
                                    time.sleep(2) # Wait 2 seconds before retrying
                                else:
                                    trans_text = "[Translation Failed]"
                                    self.log(f"⚠️ 翻譯失敗 ({start}): {e}")
                            
                        if self.bilingual_var.get():
                            # Chinese Top, Original Bottom
                            final_text = f"{trans_text}\n{text}"
                        else:
                            final_text = trans_text

                    elif "Auto" in mode_sel and info.language == "zh":
                         # Already Chinese
                         if self.trans_var.get():
                             text = cc.convert(text)
                         final_text = text
                    
                    # --- [NEW] Apply Speaker Label ---
                    speaker_label = ""
                    if diarization_result is not None:
                        try:
                            from pyannote.core import Segment
                            whisper_seg = Segment(segment.start, segment.end)
                            intersections = diarization_result.crop(whisper_seg)
                            durations = {}
                            for s, t, spk in intersections.itertracks(yield_label=True):
                                durations[spk] = durations.get(spk, 0) + s.duration
                            if durations:
                                speaker_label = f"[{max(durations.items(), key=lambda x: x[1])[0]}]: "
                        except: pass
                    
                    if speaker_label:
                        final_text = speaker_label + final_text.replace("\n", f"\n{speaker_label}")

                    # SRT Format (Clean)
                    srt_content += f"{idx}\n{start} --> {end}\n{final_text}\n\n"
                    
                    # VTT Format
                    vtt_content += f"{idx}\n{start.replace(',', '.')} --> {end.replace(',', '.')}\n{final_text}\n\n"
                    # TXT Format
                    txt_content += f"{final_text}\n"
                    
                    # Log preview every 10 lines
                    if idx % 10 == 0: 
                        self.log(f"  ... 已生成 {idx} 行字幕")
                    
                    idx += 1  # [FIX] Increment index
                
                # Save SRT (Append Model Name)
                base_name = os.path.splitext(filename)[0]
                
                # [NEW] 動態檔名後綴
                mode_val = self.compute_mode_var.get()
                if "Auto" in mode_val:
                     suffix_str = f"_{self.device}_{self.compute_type}"
                else:
                     clean_mode = mode_val.split(')')[0].replace(' ', '').replace('(', '_').replace(')', '').lower()
                     suffix_str = f"_{clean_mode}"

                model_tag = f"_{model_size}{suffix_str}"
                final_name = f"{base_name}{model_tag}"
                
                srt_path = self.get_unique_path(os.path.join(self.output_dir, final_name + ".srt"))
                with open(srt_path, "w", encoding="utf-8") as f:
                    f.write(srt_content)
                self.log(f"✅ SRT 已儲存: {srt_path}")
                
                if self.gen_vtt_var.get():
                    vtt_path = self.get_unique_path(os.path.join(self.output_dir, final_name + ".vtt"))
                    with open(vtt_path, "w", encoding="utf-8") as f: f.write(vtt_content)
                    
                if self.gen_txt_var.get():
                    txt_path = self.get_unique_path(os.path.join(self.output_dir, final_name + ".txt"))
                    with open(txt_path, "w", encoding="utf-8") as f: f.write(txt_content)
                
                # Burn-in (Optional)
                if self.burn_var.get() and not self.stop_requested:
                    self.burn_subtitle(file_path, srt_path, model_name=model_size)

            self.pbar.set(1.0)
            self.log("🎉 所有任務完成！")
            if not self.stop_requested:
                messagebox.showinfo("完成", "字幕生成完畢！")
                
        except Exception as e:
            err_str = str(e).lower()
            self.log(f"❌ 錯誤: {e}")
            traceback.print_exc()
            
            # Detect memory allocation failures (MKL, system RAM, etc.)
            memory_keywords = ["mkl_malloc", "failed to allocate", "memoryerror", "out of memory",
                               "cannot allocate", "alloc", "memory allocation"]
            if any(kw in err_str for kw in memory_keywords):
                friendly_msg = (
                    "您的電腦記憶體 (RAM) 不足，無法完成此操作。\n\n"
                    "可能的原因：\n"
                    "• 目前選用的 AI 模型太大，超過硬體負荷\n"
                    "• 電腦同時開啟太多程式佔用記憶體\n\n"
                    "建議解決方式：\n"
                    "1. 關閉其他佔用記憶體的程式 (瀏覽器、大型軟體等)\n"
                    "2. 改用較小的模型 (如 medium 或 large-v3-turbo)\n"
                    "3. 如持續發生，請重新啟動程式後再試一次"
                )
                messagebox.showerror("記憶體不足 (RAM)", friendly_msg)
            else:
                messagebox.showerror("錯誤", str(e))
        finally:
            self.is_processing = False
            self.btn_process.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            self.pbar.set(0)

    # --- Helper methods for progress parsing ---
    def escape_ffmpeg_path(self, path: str) -> str:
        """
        Escapes a Windows/Linux path specifically for FFmpeg's subtitles filter.
        Essential for paths containing characters like , ' [ ] etc.
        """
        if not path:
            return ""
            
        # 1. Normalize slashes to forward slashes (FFmpeg prefers these)
        path = path.replace('\\', '/')
        
        # 2. Escape backslashes explicitly (though forward slashes are better, handle them just in case)
        # However, since we just replaced all \ with /, this step might be redundant but safe.
        path = path.replace('\\', '\\\\')
        
        # 3. Escape single quotes (FFmpeg uses single quotes to enclose the whole string)
        # In shlex, a single quote is escaped as '\'' (close quote, escaped quote, open quote)
        # But for FFmpeg filter graph, we need to escape the single quote itself, and also escape the escape character.
        # Actually, for FFmpeg's subtitles filter enclosed in single quotes e.g. subtitles='path'
        # We need to escape single quotes as: \'\'' (which means close quote, escaped single quote, open quote)
        # Standard filter syntax escaping:
        path = path.replace(':', '\\:')
        
        # FFmpeg filter parsing: It parses the string within '' and unescapes it.
        # So inside '', we need to escape `\` and `'`.
        # However, a simpler way that FFmpeg officially recommends for complex paths is:
        # 1. replace \ with /
        # 2. replace : with \: (for Windows drive letters)
        # 3. replace , with \, 
        # 4. replace [ with \[ and ] with \]
        # 5. replace ' with \'
        
        path = path.replace(',', '\\,')
        path = path.replace('[', '\\[')
        path = path.replace(']', '\\]')
        # Handle single quotes by escaping them
        path = path.replace("'", "\\'")
        
        return path

    def get_video_info(self, ffmpeg_path, video_path):
        """ Returns (duration_sec, width, height) """
        duration = 0.0
        width = 1920 # Default
        height = 1080 # Default
        
        try:
            cmd = [ffmpeg_path, "-i", video_path]
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                  universal_newlines=True, encoding='utf-8', errors='ignore',
                                  startupinfo=startupinfo)
            output = result.stderr
            
            # 1. Parse Duration
            match_dur = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", output)
            if match_dur:
                h = int(match_dur.group(1))
                m = int(match_dur.group(2))
                s = float(match_dur.group(3))
                duration = h * 3600 + m * 60 + s
            
            # 2. Parse Resolution (Stream #0:0... Video: ... 1920x1080 ...)
            match_res = re.search(r"Stream #.*Video:.* (\d{3,5})x(\d{3,5})", output)
            if match_res:
                width = int(match_res.group(1))
                height = int(match_res.group(2))
                
        except Exception as e:
            pass
            
        return duration, width, height

    def parse_time_str(self, time_str):
        try:
            parts = time_str.split(':')
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        except: 
            pass
        return 0.0

    def burn_subtitle(self, video_path, srt_path, model_name=None):
        self.log(f"🔥 正在燒錄字幕 (FFmpeg)... 請稍候")
        
        # Get Video Info first (needed for ASS PlayRes and Progress)
        total_duration, vid_width, vid_height = self.get_video_info(self.ffmpeg_exe, video_path)
        next_log_threshold = 10.0
        
        # Determine output filename (with unique suffix to avoid overwrite)
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        if model_name:
            output_name = f"{base_name}_{model_name}_burnt.mp4"
        else:
            output_name = f"{base_name}_burnt.mp4"
            
        output_path = self.get_unique_path(os.path.join(self.output_dir, output_name))
        output_name = os.path.basename(output_path)
        
        # Try converting to ASS for full style control
        try: font_size = int(self.size_var.get())
        except: font_size = 20
        
        # [NEW] Generate ASS file with strict styling
        ass_path = self.convert_srt_to_ass(srt_path, font_size, vid_width, vid_height)
        used_temp_file = None
        
        if ass_path and os.path.exists(ass_path):
            # Use ASS Mode (Robust Styling)
            sub_arg = self.escape_ffmpeg_path(ass_path)
            vf_string = f"subtitles='{sub_arg}'"
            self.log(f"✅ 使用 ASS 格式壓制 (支援雙語縮放)")
            used_temp_file = ass_path
        else:
            # Fallback to SRT Mode (Standard)
            self.log(f"⚠️ ASS 生成失敗，降級使用 SRT 模式")
            
            # Windows Path Fix (Robust)
            srt_arg = self.escape_ffmpeg_path(srt_path)
            
            def hex_to_ass(hex_code):
                if not hex_code or len(hex_code) < 7: return "&H00FFFFFF"
                return f"&H00{hex_code[5:7]}{hex_code[3:5]}{hex_code[1:3]}"

            font_name = self.font_var.get()
            bold = 1 if self.bold_var.get() else 0
            primary_color = hex_to_ass(self.color_var.get())
            
            # Border Style (Simplified for fallback)
            if self.bgbox_var.get():
                border_style = 3 
                back_color = "&H80000000"
                outline_color = back_color
            else:
                border_style = 1
                back_color = "&H80000000"
                outline_color = hex_to_ass(self.border_color_var.get())
            
            style = f"Fontname={font_name},FontSize={font_size},Bold={bold},PrimaryColour={primary_color},OutlineColour={outline_color},BackColour={back_color},BorderStyle={border_style},Outline=1,Shadow=0,Alignment=2,MarginV=20"
            vf_string = f"subtitles='{srt_arg}':force_style='{style}'"

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        cmd = [
            self.ffmpeg_exe, "-y",
            "-i", video_path,
            "-vf", vf_string,
            "-map", "0:v", "-map", "0:a?", # Explicitly map video and audio (if exists)
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-c:a", "aac", # Re-encode audio to AAC to ensure compatibility
            output_path
        ]
        
        self.pbar.configure(mode="determinate")
        self.pbar.set(0)
        
        try:
            # Popen to capture progress
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       universal_newlines=True, encoding='utf-8', 
                                       errors='ignore', startupinfo=startupinfo)
            
            for line in process.stdout:
                if self.stop_requested:
                    process.terminate()
                    break
                    
                if "time=" in line:
                    match = re.search(r"time=(\d{2}:\d{2}:\d{2}\.\d+)", line)
                    if match and total_duration > 0:
                        current_time_str = match.group(1)
                        current_seconds = self.parse_time_str(current_time_str)
                        progress_pct = (current_seconds / total_duration) * 100
                        if progress_pct > 100: progress_pct = 100.0
                        
                        self.after(0, lambda v=(progress_pct / 100): self.update_progress_ui(v))
                        
                        if progress_pct >= next_log_threshold:
                            now_str = datetime.now().strftime('%H:%M')
                            # Helper to format HH:MM:SS
                            def fmt(s):
                                h = int(s // 3600)
                                m = int((s % 3600) // 60)
                                sec = s % 60
                                return f"{h:02}:{m:02}:{sec:06.3f}"
                                
                            total_str = fmt(total_duration)
                            curr_str = fmt(current_seconds)
                            
                            self.log(f"⏳ [{now_str}] 壓制進度: {progress_pct:.0f}% ({curr_str} / {total_str})")
                            next_log_threshold += 10.0
            
            process.wait()
            
            if process.returncode == 0 and not self.stop_requested:
                self.log(f"✅ 燒錄完成: {output_name}")
            elif self.stop_requested:
                self.log("🛑 壓制已中斷")
            else:
                 self.log(f"⚠️ 燒錄失敗 (Exit Code: {process.returncode})")
                 
        except Exception as e:
            self.log(f"⚠️ 燒錄失敗: {e}")
        finally:
            self.pbar.stop()
            self.pbar.configure(mode="determinate")
            self.pbar.set(1.0)
            
            # Cleanup temp file
            if used_temp_file and os.path.exists(used_temp_file):
                try: os.remove(used_temp_file)
                except: pass

    # --- SRT to ASS Conversion (Full Style Control) ---
    def convert_srt_to_ass(self, srt_path, main_size, video_width, video_height):
        """
        Converts SRT to ASS format to strictly enforce styling and font sizes.
        Returns path to generated .ass file.
        """
        try:
            # --- 1. Prepare Primary Styles ---
            font_name = self.font_var.get()
            bold = -1 if self.bold_var.get() else 0
            
            def hex_to_ass_color(hex_code, alpha_hex="00"):
                if not hex_code or len(hex_code) < 7: return f"&H{alpha_hex}FFFFFF"
                # #RRGGBB -> &H[Alpha]BBGGRR
                return f"&H{alpha_hex}{hex_code[5:7]}{hex_code[3:5]}{hex_code[1:3]}"

            pri_color = hex_to_ass_color(self.color_var.get())
            
            # Resolution Scaling (Reference: 432p)
            ref_height = 432.0
            if video_height <= 0: video_height = 720
            scale_factor = video_height / ref_height
            
            real_main_size = int(main_size * scale_factor)
            
            try: outline_w_raw = int(self.outline_var.get())
            except: outline_w_raw = 1
            real_outline_w = int(outline_w_raw * scale_factor)
            if real_outline_w < 1: real_outline_w = 1
            real_margin_v = int(20 * scale_factor)


            use_box_layering = self.bgbox_var.get()
            user_outline_color = hex_to_ass_color(self.border_color_var.get())
            
            bg_hex = self.bg_color_var.get()
            bg_alpha_val = self.bg_alpha_var.get()
            bg_alpha_int = int(255 * (bg_alpha_val / 100))
            bg_alpha_hex = f"{bg_alpha_int:02X}"
            box_fill_color = hex_to_ass_color(bg_hex, bg_alpha_hex) 
            
            # Read character spacing
            try: pri_spacing = int(self.spacing_var.get()) * 3
            except: pri_spacing = 0

            # --- 2. Prepare Secondary Styles ---
            sec_font_name = self.sec_font_var.get()
            sec_bold = -1 if self.sec_bold_var.get() else 0
            sec_pri_color = hex_to_ass_color(self.sec_color_var.get())
            
            try: sec_main_size_raw = int(self.sec_size_var.get())
            except: sec_main_size_raw = 14
            real_sec_size = int(sec_main_size_raw * scale_factor)
            
            try: sec_outline_w_raw = int(self.sec_outline_var.get())
            except: sec_outline_w_raw = 1
            real_sec_outline_w = int(sec_outline_w_raw * scale_factor)
            if real_sec_outline_w < 1: real_sec_outline_w = 1
            
            sec_use_box_layering = self.sec_bgbox_var.get()
            sec_user_outline_color = hex_to_ass_color(self.sec_border_color_var.get())
            
            sec_bg_hex = self.sec_bg_color_var.get()
            sec_bg_alpha_val = self.sec_bg_alpha_var.get()
            sec_bg_alpha_int = int(255 * (sec_bg_alpha_val / 100))
            sec_bg_alpha_hex = f"{sec_bg_alpha_int:02X}"
            sec_box_fill_color = hex_to_ass_color(sec_bg_hex, sec_bg_alpha_hex)
            
            try: sec_spacing = int(self.sec_spacing_var.get()) * 3
            except: sec_spacing = 0
            
            # Line Spacing Spacer (Gap between Main and Secondary)
            spacing_size = int(real_main_size * 0.15) 
            if spacing_size < 2: spacing_size = 2
            
            # --- 3. Build Style Definitions ---
            style_definitions = ""
            
            # Primary Styles
            if use_box_layering:
                box_padding = int(real_outline_w * 1.0) 
                if box_padding < 1: box_padding = 1
                style_definitions += f"Style: PrimaryBoxLayer,{font_name},{real_main_size},&HFF000000,&H000000FF,{box_fill_color},&H00000000,{bold},0,0,0,100,100,{pri_spacing},0,3,{box_padding},0,2,10,10,{real_margin_v},1\n"
                style_definitions += f"Style: PrimaryTextLayer,{font_name},{real_main_size},{pri_color},&H000000FF,{user_outline_color},&H00000000,{bold},0,0,0,100,100,{pri_spacing},0,1,{real_outline_w},0,2,10,10,{real_margin_v},1\n"
            else:
                style_definitions += f"Style: PrimaryDefault,{font_name},{real_main_size},{pri_color},&H000000FF,{user_outline_color},&H00000000,{bold},0,0,0,100,100,{pri_spacing},0,1,{real_outline_w},0,2,10,10,{real_margin_v},1\n"

            # Secondary Styles
            if sec_use_box_layering:
                sec_box_padding = int(real_sec_outline_w * 1.0) 
                if sec_box_padding < 1: sec_box_padding = 1
                style_definitions += f"Style: SecondaryBoxLayer,{sec_font_name},{real_sec_size},&HFF000000,&H000000FF,{sec_box_fill_color},&H00000000,{sec_bold},0,0,0,100,100,{sec_spacing},0,3,{sec_box_padding},0,2,10,10,{real_margin_v},1\n"
                style_definitions += f"Style: SecondaryTextLayer,{sec_font_name},{real_sec_size},{sec_pri_color},&H000000FF,{sec_user_outline_color},&H00000000,{sec_bold},0,0,0,100,100,{sec_spacing},0,1,{real_sec_outline_w},0,2,10,10,{real_margin_v},1\n"
            else:
                style_definitions += f"Style: SecondaryDefault,{sec_font_name},{real_sec_size},{sec_pri_color},&H000000FF,{sec_user_outline_color},&H00000000,{sec_bold},0,0,0,100,100,{sec_spacing},0,1,{real_sec_outline_w},0,2,10,10,{real_margin_v},1\n"

            self.log(f"🔎 [Debug] ASS Scaling Factor={scale_factor:.2f}. PriFont={real_main_size}, SecFont={real_sec_size}")

            # 2. Build ASS Header
            ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style_definitions}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
            ass_events = []
            
            # 3. Read and Parse SRT
            with open(srt_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            blocks = re.split(r'\n\s*\n', content)
            
            for block in blocks:
                if not block.strip(): continue
                lines = block.split('\n')
                if len(lines) >= 3:
                    # Parse Time
                    time_line = lines[1]
                    times = time_line.split(' --> ')
                    if len(times) != 2: continue
                    
                    def srt_time_to_ass(t_str):
                        t_str = t_str.replace(',', '.')
                        parts = t_str.split(':')
                        h = int(parts[0])
                        m = parts[1]
                        s = parts[2] 
                        return f"{h}:{m}:{s[:-1]}" 

                    start_ass = srt_time_to_ass(times[0])
                    end_ass = srt_time_to_ass(times[1])
                    
                    # Helper to get style name
                    def _get_pri_style(is_box): return "PrimaryBoxLayer" if is_box and use_box_layering else ("PrimaryTextLayer" if use_box_layering else "PrimaryDefault")
                    def _get_sec_style(is_box): return "SecondaryBoxLayer" if is_box and sec_use_box_layering else ("SecondaryTextLayer" if sec_use_box_layering else "SecondaryDefault")
                    
                    # Process Text
                    text_lines = lines[2:]
                    
                    if len(text_lines) >= 2:
                        # Bilingual
                        l1 = text_lines[0]
                        l2 = text_lines[1]
                        
                        spacer = f"\\N{{\\fs{spacing_size}}} \\N"
                        
                        # We use \r to reset to a specific style inside the same event line.
                        # Event Style = Primary Style (controls placement)
                        # Text: [Line 1] + \N + \rSecondaryStyle + [Line 2]
                        if use_box_layering or sec_use_box_layering:
                            # If ANY box layering is used, we have to emit Box layer and Text layer separately.
                            # Box Layer (0): Use {\alpha&HFF&} to make text fully transparent but reserve exact geometric space.
                            # This prevents ASS renderers from collapsing the bounding box to the bottom margin.
                            if use_box_layering:
                                box_l1 = l1
                            else:
                                box_l1 = f"{{\\alpha&HFF&}}{l1}"
                                
                            if sec_use_box_layering:
                                box_l2 = f"{{\\r{_get_sec_style(True)}}}{l2}"
                            else:
                                box_l2 = f"{{\\r{_get_sec_style(True)}}}{{\\alpha&HFF&}}{l2}"
                                
                            box_final = f"{box_l1}{spacer}{box_l2}"
                            
                            ass_events.append(f"Dialogue: 0,{start_ass},{end_ass},{_get_pri_style(True)},,0,0,0,,{box_final}")
                            
                            # Text Layer (1)
                            txt_final = f"{l1}{spacer}{{\\r{_get_sec_style(False)}}}{l2}"
                            ass_events.append(f"Dialogue: 1,{start_ass},{end_ass},{_get_pri_style(False)},,0,0,0,,{txt_final}")
                        else:
                            # Single layers for both
                            final_text = f"{l1}{spacer}{{\\r{_get_sec_style(False)}}}{l2}"
                            ass_events.append(f"Dialogue: 0,{start_ass},{end_ass},{_get_pri_style(False)},,0,0,0,,{final_text}")
                    else:
                        # Monolingual (Primary only)
                        final_text = "\\N".join(text_lines)
                        if use_box_layering:
                            ass_events.append(f"Dialogue: 0,{start_ass},{end_ass},{_get_pri_style(True)},,0,0,0,,{final_text}")
                            ass_events.append(f"Dialogue: 1,{start_ass},{end_ass},{_get_pri_style(False)},,0,0,0,,{final_text}")
                        else:
                            ass_events.append(f"Dialogue: 0,{start_ass},{end_ass},{_get_pri_style(False)},,0,0,0,,{final_text}")

            # 4. Write ASS File
            ass_content = ass_header + "\n".join(ass_events)
            ass_path = srt_path.replace(".srt", ".ass")
            
            with open(ass_path, "w", encoding="utf-8") as f:
                f.write(ass_content)
                
            return ass_path

        except Exception as e:
            self.log(f"⚠️ ASS 轉換失敗: {e}")
            import traceback
            traceback.print_exc()
            return None

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

    def format_time(self, seconds):
        hours = math.floor(seconds / 3600)
        seconds %= 3600
        minutes = math.floor(seconds / 60)
        seconds %= 60
        millis = round((seconds - math.floor(seconds)) * 1000)
        seconds = math.floor(seconds)
        return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"

    # --- Manual Tools Implementation ---
    def select_srt(self):
        f = filedialog.askopenfilename(title="選擇字幕檔", initialdir=self.output_dir, filetypes=[("Subtitle", "*.srt")])
        if f:
            self.manual_srt_path = f
            self.log(f"已選擇字幕檔: {os.path.basename(f)}")
            self.btn_burn_manual.configure(state="normal")
            messagebox.showinfo("提示", "已載入字幕檔，現在可以進行【壓制影片】。")

    def open_srt_editor(self):
        target_srt = None
        
        # 1. 優先檢查目前選定的單一檔案
        candidates = []
        if self.file_list:
            for v_path in self.file_list:
                base_name = os.path.splitext(os.path.basename(v_path))[0]
                
                # A. Check source directory
                src_srt = os.path.splitext(v_path)[0] + ".srt"
                if os.path.exists(src_srt):
                    candidates.append(src_srt)
                
                # B. Check Output directory (Outputs/Subtitles)
                out_srt = os.path.join(self.output_dir, base_name + ".srt")
                if os.path.exists(out_srt) and out_srt not in candidates:
                    candidates.append(out_srt)
        
        # 2. 判斷
        if len(candidates) == 1:
            target_srt = candidates[0]
        elif len(candidates) > 1:
            # 選擇視窗
            top = ctk.CTkToplevel(self)
            top.title("選擇字幕")
            top.geometry("400x300")
            # Modal
            top.grab_set()
            
            ctk.CTkLabel(top, text="請選擇要編輯的字幕:", font=self.font_ui).pack(pady=10)
            
            scroll = ctk.CTkScrollableFrame(top)
            scroll.pack(fill="both", expand=True, padx=10, pady=10)
            
            def confirm(p):
                top.destroy()
                self.launch_editor(p)
                
            for p in candidates:
                ctk.CTkButton(scroll, text=os.path.basename(p), command=lambda path=p: confirm(path), font=self.font_ui).pack(fill="x", pady=2)
            return
        elif self.manual_srt_path and os.path.exists(self.manual_srt_path):
             target_srt = self.manual_srt_path

        if target_srt:
            self.launch_editor(target_srt)
        else:
            f = filedialog.askopenfilename(title="選擇 SRT 字幕檔", initialdir=self.output_dir, filetypes=[("Subtitle", "*.srt")])
            if f:
                self.launch_editor(f)
            else:
                messagebox.showwarning("提示", "找不到可編輯的字幕檔案，請先生成或手動選擇。")

    def launch_editor(self, path):
         # Launch modal editor
         editor = SRTEditorWindow(self, path)

    def start_burn_thread(self):
        threading.Thread(target=self.run_burn_process, daemon=True).start()

    def run_burn_process(self):
        # 1. 決定要壓制的影片與字幕
        files_to_process = [] # Tuple (video, srt)
        
        # 模式 A: 列表有檔案
        if self.file_list:
             for v in self.file_list:
                 base_name = os.path.splitext(os.path.basename(v))[0]
                 
                 # 優先找 Outputs/Subtitles
                 out_srt = os.path.join(self.output_dir, base_name + ".srt")
                 src_srt = os.path.splitext(v)[0] + ".srt"
                 
                 if os.path.exists(out_srt):
                     files_to_process.append((v, out_srt))
                 elif os.path.exists(src_srt):
                     files_to_process.append((v, src_srt))
                 elif len(self.file_list) == 1 and self.manual_srt_path:
                     # 單檔 + 手動指定 SRT
                     files_to_process.append((v, self.manual_srt_path))
        
        # 模式 B: 列表無檔案，但有手動指定 SRT (嘗試反查影片)
        elif self.manual_srt_path:
             base = os.path.splitext(self.manual_srt_path)[0]
             for ext in ['.mp4', '.mkv', '.mov', '.avi', '.flv']:
                 if os.path.exists(base + ext):
                     files_to_process.append((base + ext, self.manual_srt_path))
                     break
        
        if not files_to_process:
            messagebox.showwarning("提示", "找不到可壓制的影片與字幕組合。\n請確保影片旁有同名 SRT，或使用【選擇字幕】按鈕。")
            return

        self.btn_burn_manual.configure(state="disabled")
        self.btn_process.configure(state="disabled")
        self.log("🔥 開始手動壓制...")
        
        ffmpeg_path = self.get_ffmpeg_path()
        
        success_count = 0
        total = len(files_to_process)
        
        for video_path, srt_path in files_to_process:
            if self.stop_requested: break
            try:
                self.log(f"🎬 處理中: {os.path.basename(video_path)}")
                # Try to guess model name from SRT filename or use current selection
                model_guess = self.model_var.get().split(" ")[0]

                self.burn_subtitle(video_path, srt_path, model_name=model_guess) 
                success_count += 1
            except Exception as e:
                self.log(f"❌ 壓制失敗: {e}")
        
        self.log(f"✅ 任務結束 (成功: {success_count}/{total})")
        messagebox.showinfo("完成", f"壓制任務結束！\n成功: {success_count}/{total}")
        
        self.btn_burn_manual.configure(state="normal")
        self.btn_process.configure(state="normal")

    def get_ffmpeg_path(self):
         if os.path.exists("ffmpeg.exe"): return os.path.abspath("ffmpeg.exe")
         if os.path.exists("bin/ffmpeg.exe"): return os.path.abspath("bin/ffmpeg.exe")
         sh = shutil.which("ffmpeg")
         if sh: return sh
         return "ffmpeg"

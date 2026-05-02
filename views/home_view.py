import customtkinter as ctk
import os
from PIL import Image

class HomeView(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        # Grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Load Icons
        icons_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "icons")
        def load_img(name, size=24):
            path = os.path.join(icons_dir, f"{name}.png")
            return ctk.CTkImage(light_image=Image.open(path), size=(size, size)) if os.path.exists(path) else None

        img_bulb = load_img("bulb")
        img_warning = load_img("warning")
        img_guide = load_img("guide")
        img_guide = load_img("guide")
        img_hammer = load_img("hammer")
        img_smile = load_img("smile")
        img_discord = load_img("discord", size=24)

        # Main Container
        self.center_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.center_frame.grid(row=0, column=0, sticky="n", pady=15) # Reduced from 40
        
        # Try loading app.ico
        try:
            app_icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.ico")
            img_app = ctk.CTkImage(light_image=Image.open(app_icon_path), size=(96, 96)) if os.path.exists(app_icon_path) else None
        except Exception:
            img_app = None

        # Title Header Frame (Horizontal layout for Icon + Texts)
        self.header_frame = ctk.CTkFrame(self.center_frame, fg_color="transparent")
        self.header_frame.pack(pady=(0, 15))
        
        if img_app:
            self.icon_label = ctk.CTkLabel(self.header_frame, text="", image=img_app)
            self.icon_label.pack(side="left", padx=(0, 20))
            
        self.text_title_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        self.text_title_frame.pack(side="left", fill="y", expand=True)

        # Professional Title
        self.title_label = ctk.CTkLabel(self.text_title_frame, 
                                      text="Studio0808 AI 影音工作站", 
                                      text_color="#E0E0E0", # Light Silver
                                      font=("Microsoft JhengHei UI", 24, "bold"))
        self.title_label.pack(anchor="w", pady=(15, 5))
        
        # Professional Subtitle
        self.subtitle_frame = ctk.CTkFrame(self.text_title_frame, fg_color="transparent")
        self.subtitle_frame.pack(anchor="w")
        
        ctk.CTkLabel(self.subtitle_frame, text="Unprofessional ", text_color="#FF5252", font=("Microsoft JhengHei UI", 16, "bold")).pack(side="left")
        ctk.CTkLabel(self.subtitle_frame, text="Audio & Video Processing Suite", text_color="#00E5FF", font=("Microsoft JhengHei UI", 16, "bold")).pack(side="left")
        
        # Independent Info Block (Nested frame to fix corner rendering bugs)
        self.outer_info_frame = ctk.CTkFrame(self.center_frame, fg_color="#3949AB", corner_radius=15)
        self.outer_info_frame.pack(pady=10, fill="x")
        
        self.info_frame = ctk.CTkFrame(self.outer_info_frame, fg_color="#181A1F", corner_radius=13)
        self.info_frame.pack(padx=2, pady=2, fill="both", expand=True)

        # Inner frame to control exact padding from the border
        self.inner_padding_frame = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        self.inner_padding_frame.pack(padx=20, pady=15, fill="both", expand=True)

        # Helper for line spacing
        def create_text_lines(lines, last_pady=10):
            for i, line in enumerate(lines):
                py = (0, last_pady) if i == len(lines)-1 else (0, 3) # Reduced line height spacing from 5 to 3
                ctk.CTkLabel(self.inner_padding_frame, text=line, text_color="#E0E0E0", font=("Microsoft JhengHei UI", 15), justify="left", anchor="w").pack(fill="x", pady=py)

        # Tech Stack Suggestion
        tech_title = ctk.CTkLabel(self.inner_padding_frame, text=" 核心技術", image=img_hammer, compound="left", text_color="#FFCA28", font=("Microsoft JhengHei UI", 20, "bold"), anchor="w")
        tech_title.pack(fill="x", pady=(0, 10))
        
        create_text_lines([
            "• 本系統採用強大且靈活的 Python 語言架構。視覺與操作介面由 CustomTkinter 打造，提供現代化的深色主題流暢體驗。",
            "• 核心運算深度整合 PyTorch 深度學習框架、FFmpeg 多媒體處理引擎、Pyannote 人聲辨識技術。",
            "• 語音生成與轉換採用了頂尖的 GPT-SoVITS、Edge-TTS 及 RVC (Retrieval-based Voice Conversion) 演算法。",
            "• 人聲分離則導入 Demucs 高保真音訊分離模型，全面打造【非】專業級的影音工作站。"
        ])

        # Hardware Suggestion
        hw_title = ctk.CTkLabel(self.inner_padding_frame, text=" 硬體建議", image=img_bulb, compound="left", text_color="#00E676", font=("Microsoft JhengHei UI", 20, "bold"), anchor="w")
        hw_title.pack(fill="x", pady=(0, 5))
        
        create_text_lines([
            "• 本系統內建模型龐大，強烈建議具備 NVIDIA 獨立顯示卡 (RTX 系列佳)",
            "  以獲得最完美的秒殺級處理速度。",
            "• 若使用 AMD 顯卡、Intel 內顯或 Mac 系統，程式將自動轉由 CPU 運算，",
            "  需較長等待時間，敬請見諒。"
        ])

        # Disclaimer
        disc_title = ctk.CTkLabel(self.inner_padding_frame, text=" 免責聲明", image=img_warning, compound="left", text_color="#FF5252", font=("Microsoft JhengHei UI", 20, "bold"), anchor="w")
        disc_title.pack(fill="x", pady=(0, 5))

        create_text_lines([
            "• 本系統僅供個人學習與研究使用，嚴禁造假詐騙、商業牟利或侵犯著作權。",
            "• 使用者應自行承擔使用衍生之法律責任與風險，本軟體亦不對資料遺失負責。"
        ], last_pady=20)

        # Separator line
        separator = ctk.CTkFrame(self.inner_padding_frame, height=2, fg_color="#3949AB")
        separator.pack(fill="x", pady=(0, 15))

        # Bottom Actions Frame (Now inside the inner frame)
        self.actions_frame = ctk.CTkFrame(self.inner_padding_frame, fg_color="transparent")
        self.actions_frame.pack(pady=5)

        # Open Guide Button
        self.btn_guide = ctk.CTkButton(self.actions_frame, 
                                       text=" 軟體使用手冊", 
                                       image=img_guide, compound="left",
                                       command=self.open_guide,
                                       font=("Microsoft JhengHei UI", 16, "bold"),
                                       fg_color="#F57C00", hover_color="#EF6C00",
                                       height=40, corner_radius=8)
        self.btn_guide.pack(side="left", padx=(0, 30))
        
        # Discord Community Button
        self.btn_discord = ctk.CTkButton(self.actions_frame, 
                                         text=" Discord 交流討論",
                                         image=img_discord, compound="left",
                                         command=self.open_discord,
                                         font=("Microsoft JhengHei UI", 16, "bold"),
                                         fg_color="#5865F2", hover_color="#4752C4", # Discord Blue
                                         height=40, corner_radius=8)
        self.btn_discord.pack(side="left", padx=(0, 15))
        
        # Feedback & Smiley
        self.feedback_frame = ctk.CTkFrame(self.actions_frame, fg_color="transparent")
        self.feedback_frame.pack(side="left")
        
        ctk.CTkLabel(self.feedback_frame, text="(歡迎報錯與建議)", text_color="#FFCA28", font=("Microsoft JhengHei UI", 15, "bold")).pack(side="left", padx=5)
        ctk.CTkLabel(self.feedback_frame, text="", image=img_smile).pack(side="left")

    def open_guide(self):
        import webbrowser
        try:
            webbrowser.open("https://begin0808.github.io/studio0808_video")
        except Exception as e:
            print(f"無法開啟線上說明手冊: {e}")

    def open_discord(self):
        import webbrowser
        try:
            webbrowser.open("https://discord.gg/F7mC37MBtF")
        except Exception as e:
            print(f"無法開啟 Discord: {e}")

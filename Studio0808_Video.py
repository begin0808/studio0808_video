import os
import sys

# [NEW: Pure Python Splash Screen Isolated Subprocess]
if __name__ == "__main__":
    if "--splash-only" in sys.argv:
        # Run splash in a 100% isolated memory space to avoid Tkinter Image Cache Tcl Error
        try:
            import tkinter as tk
            from PIL import Image, ImageTk
            splash_root = tk.Tk()
            splash_root.overrideredirect(True)
            splash_root.attributes('-topmost', True)
            
            base_dir = sys._MEIPASS if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            splash_path = os.path.join(base_dir, "assets", "splash.png")
            
            if os.path.exists(splash_path):
                img = Image.open(splash_path)
                w, h = img.size  # Automatically use the image's original resolution
                
                # Position at center dynamically using the true image dimensions
                sw = splash_root.winfo_screenwidth()
                sh = splash_root.winfo_screenheight()
                x = int((sw - w) / 2)
                y = int((sh - h) / 2)
                splash_root.geometry(f"{w}x{h}+{x}+{y}")
                
                photo = ImageTk.PhotoImage(img)
                lbl = tk.Label(splash_root, image=photo, bg="black")
                lbl.image = photo 
                lbl.pack(fill="both", expand=True)
                
            splash_root.update()
            # Wait until parent process kills this
            splash_root.mainloop()
        except Exception:
            pass
        sys.exit(0)

# Parent Process Splash Launcher
splash_proc = None
if __name__ == "__main__":
    if "--rvc_cli" not in sys.argv and "--splash-only" not in sys.argv:
        try:
            import subprocess
            startupinfo = subprocess.STARTUPINFO()
            if hasattr(subprocess, 'STARTF_USESHOWWINDOW'):
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            # Spawn splash in an invisible console (using CREATE_NO_WINDOW if available)
            flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000) if sys.platform == 'win32' else 0
            # If frozen, sys.executable is your .exe. Otherwise it's python.exe
            cmd = [sys.executable, "--splash-only"] 
            if not getattr(sys, 'frozen', False):
                cmd.insert(1, os.path.abspath(__file__))
            splash_proc = subprocess.Popen(cmd, startupinfo=startupinfo, creationflags=flags)
        except Exception as e:
            print(f"Failed to launch splash process: {e}")

# ============================================================
# [相容性修補] 在所有模組匯入前執行，避免套件版本衝突
# ============================================================

# [修補 1] omegaconf 2.3.0 移除了 _utils.get_ref_type，但 hydra-core 1.0.7 仍需要它
# 這裡重新注入一個等效實作，讓 fairseq -> hydra -> omegaconf 的匯入鏈不會斷掉
try:
    import omegaconf._utils
    if not hasattr(omegaconf._utils, 'get_ref_type'):
        from typing import Any
        def _compat_get_ref_type(cfg, key=None):
            from omegaconf import Container, Node
            if isinstance(cfg, Container) and key is not None:
                node = cfg._get_node(key)
            elif isinstance(cfg, Node):
                node = cfg
            else:
                return Any
            if hasattr(node, '_metadata') and hasattr(node._metadata, 'ref_type'):
                return node._metadata.ref_type
            return Any
        omegaconf._utils.get_ref_type = _compat_get_ref_type
except ImportError:
    pass  # omegaconf 未安裝，不需要修補

# [修補 2] torchaudio 2.11+ 大幅重構：移除 backend 子模組、set_audio_backend 等 API，
# 且 load/save/info 全部改為依賴 torchcodec。
# pyannote.audio 和 speechbrain 內部仍需要這些 API，所以需要全面修補。
try:
    import torchaudio

    # 2a. 補回缺失的函式 API
    if not hasattr(torchaudio, 'set_audio_backend'):
        torchaudio.set_audio_backend = lambda backend=None: None
    if not hasattr(torchaudio, 'get_audio_backend'):
        torchaudio.get_audio_backend = lambda: None
    if not hasattr(torchaudio, 'list_audio_backends'):
        torchaudio.list_audio_backends = lambda: []

    # 2b. 如果 torchaudio.backend 套件不存在，建立完整的假套件結構
    import importlib
    if importlib.util.find_spec('torchaudio.backend') is None:
        import types

        # AudioMetaData 類別（speechbrain.dataio 需要 torchaudio.backend.common.AudioMetaData）
        class _AudioMetaData:
            def __init__(self, sample_rate=0, num_frames=0, num_channels=0,
                         bits_per_sample=0, encoding=None):
                self.sample_rate = sample_rate
                self.num_frames = num_frames
                self.num_channels = num_channels
                self.bits_per_sample = bits_per_sample
                self.encoding = encoding

        fake_common = types.ModuleType('torchaudio.backend.common')
        fake_common.AudioMetaData = _AudioMetaData
        sys.modules['torchaudio.backend.common'] = fake_common

        fake_backend = types.ModuleType('torchaudio.backend')
        fake_backend.__path__ = []
        fake_backend.__package__ = 'torchaudio.backend'
        fake_backend.set_audio_backend = torchaudio.set_audio_backend
        fake_backend.get_audio_backend = torchaudio.get_audio_backend
        fake_backend.list_audio_backends = torchaudio.list_audio_backends
        fake_backend.common = fake_common
        sys.modules['torchaudio.backend'] = fake_backend

    # 2c. 如果 torchcodec 未安裝，torchaudio.load/save/info 會失敗。
    #     用 soundfile 作為 fallback 替代實作。
    _need_soundfile_fallback = False
    try:
        from torchcodec.decoders import AudioDecoder  # noqa: F401
    except ImportError:
        _need_soundfile_fallback = True

    if _need_soundfile_fallback:
        import torch
        import soundfile as sf
        import numpy as np

        _orig_load = getattr(torchaudio, '_orig_load_backup', None)

        def _soundfile_load(uri, frame_offset=0, num_frames=-1, normalize=True,
                            channels_first=True, format=None, buffer_size=4096, backend=None):
            """基於 soundfile 的 torchaudio.load fallback 實作"""
            data, sample_rate = sf.read(uri, start=frame_offset,
                                        stop=(frame_offset + num_frames) if num_frames > 0 else None,
                                        dtype='float32', always_2d=True)
            # soundfile 回傳 (frames, channels)，轉為 torch tensor
            tensor = torch.from_numpy(data).float()
            if channels_first:
                tensor = tensor.t()  # (frames, channels) -> (channels, frames)
            return tensor, sample_rate

        def _soundfile_save(uri, src, sample_rate, channels_first=True, format=None,
                            encoding=None, bits_per_sample=None, buffer_size=4096,
                            backend=None, compression=None):
            """基於 soundfile 的 torchaudio.save fallback 實作"""
            if isinstance(src, torch.Tensor):
                if src.ndim == 1:
                    src = src.unsqueeze(0)
                if channels_first:
                    src = src.t()  # (channels, frames) -> (frames, channels)
                src = src.cpu().numpy()
            sf.write(uri, src, sample_rate)

        def _soundfile_info(uri, format=None, backend=None):
            """基於 soundfile 的 torchaudio.info fallback 實作"""
            info = sf.info(uri)
            meta = _AudioMetaData(
                sample_rate=info.samplerate,
                num_frames=info.frames,
                num_channels=info.channels,
                bits_per_sample=info.subtype_info.split()[-1] if hasattr(info, 'subtype_info') else 16,
                encoding=info.subtype if hasattr(info, 'subtype') else None
            )
            # bits_per_sample 需要是 int
            try:
                meta.bits_per_sample = int(meta.bits_per_sample)
            except (ValueError, TypeError):
                meta.bits_per_sample = 16
            return meta

        # 替換 torchaudio 的函式
        torchaudio.load = _soundfile_load
        torchaudio.save = _soundfile_save
        if not hasattr(torchaudio, 'info'):
            torchaudio.info = _soundfile_info
except ImportError:
    pass  # torchaudio 未安裝，不需要修補

# ============================================================



import customtkinter as ctk
import io

# [NEW: PyInstaller Windowed Mode Fix]
# Mock stdout/stderr if None (prevents flush() errors in Whisper/tqdm)
if sys.stdout is None:
    sys.stdout = io.StringIO()
if sys.stderr is None:
    sys.stderr = io.StringIO()

import subprocess
# [NEW: PyInstaller Windowed Mode Fix]
# Monkey patch subprocess.Popen to universally add CREATE_NO_WINDOW on Windows
if sys.platform == 'win32':
    _original_popen_init = subprocess.Popen.__init__
    def _patched_popen_init(self, *args, **kwargs):
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        _original_popen_init(self, *args, **kwargs)
    subprocess.Popen.__init__ = _patched_popen_init

# Suppress TensorFlow warnings (Cosmetic fix for CUDA 12.4 environments)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

# Prevent OpenMP threads deadlock (fixes faster-whisper freezing on Windows after pyannote)
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

from PIL import Image

# Global FFmpeg Setup
def setup_ffmpeg():
    # Determine script directory
    if getattr(sys, 'frozen', False):
        script_dir = os.path.dirname(sys.executable)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))

    # Possible locations for ffmpeg.exe (e.g. tools/ffmpeg.exe)
    candidates = [
        os.path.join(script_dir, "tools", "ffmpeg.exe"),
        os.path.join(script_dir, "ffmpeg.exe"),
        os.path.join(script_dir, "bin", "ffmpeg.exe"),
        os.path.join(os.getcwd(), "tools", "ffmpeg.exe") 
    ]
    
    found_ffmpeg = None
    for p in candidates:
        if os.path.exists(p):
            found_ffmpeg = p
            break
            
    if found_ffmpeg:
        ffmpeg_dir = os.path.dirname(found_ffmpeg)
        if ffmpeg_dir not in os.environ["PATH"]:
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ["PATH"]
            print(f"[Main] Added FFmpeg to PATH: {ffmpeg_dir}")
        
        # Configure pydub global converter
        try:
            from pydub import AudioSegment
            AudioSegment.converter = found_ffmpeg
        except ImportError:
            pass

setup_ffmpeg()

# Import Views
from views.home_view import HomeView
from views.download_view import DownloadView
from views.audio_view import AudioView
from views.subtitle_view import SubtitleView
from views.rvc_view import RVCView
from views.ktv_view import KTVView
from views.toolbox_view import ToolboxView
from views.tts_view import TTSView
from views.clone_view import CloneView
from views.realtime_vc_view import RealTimeVCView

# Set default theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configure window
        self.title("Studio0808 AI 影音工具站")
        self.geometry(f"{1100}x{750}")
        self.minsize(900, 650)
        
        # 1. Hide window initially to prevent 'empty structural' flash
        self.attributes("-alpha", 0.0)
        
        # 2. Combined initialization function for focus and aesthetics
        def _initialize_window():
            try:
                import ctypes
                # Applying dark title bar
                HWND = ctypes.windll.user32.GetParent(self.winfo_id())
                value = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(HWND, 20, ctypes.byref(value), ctypes.sizeof(value)) # Win11
                ctypes.windll.dwmapi.DwmSetWindowAttribute(HWND, 19, ctypes.byref(value), ctypes.sizeof(value)) # Win10
                
                # Dark background for title bar
                color = ctypes.c_int(0x001F1A18) 
                ctypes.windll.dwmapi.DwmSetWindowAttribute(HWND, 35, ctypes.byref(color), ctypes.sizeof(color))
                
                # White text for title bar
                text_color = ctypes.c_int(0x00FFFFFF)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(HWND, 36, ctypes.byref(text_color), ctypes.sizeof(text_color))

                # Now show maximized and centered
                self.state('zoomed')
                self.attributes("-alpha", 1.0)
                
                # Force to front and capture focus
                self.attributes("-topmost", True)
                self.lift()
                self.focus_force()
                self.after(500, lambda: self.attributes("-topmost", False))
                
            except Exception as e:
                print(f"Window initialization failed: {e}")
                self.attributes("-alpha", 1.0) # Ensure it's visible even if DWM fails
                
        # Run initialization once everything is ready
        self.after(200, _initialize_window)
        
        # Set Application Icon
        # Set Application Icon
        try:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
                self.iconbitmap(default=icon_path) # Critical for Taskbar icon in Tkinter
                self.wm_iconbitmap(icon_path)
        except Exception as e:
            print(f"Warning: Could not load application icon app.ico. Error: {e}")
        
        # Handle close event
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Configure grid layout (1x2)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 1. Navigation Frame (Darker background for depth)
        self.navigation_frame = ctk.CTkFrame(self, width=180, corner_radius=0, fg_color=("gray90", "#181A1F")) # Support both light and dark
        self.navigation_frame.grid(row=0, column=0, sticky="nsew")
        self.navigation_frame.grid_rowconfigure(20, weight=1) # Spacer at bottom
        
        # Menu Font
        try:
            self.menu_font = ctk.CTkFont(family="Microsoft JhengHei UI", size=16, weight="bold")
        except:
            self.menu_font = ctk.CTkFont(size=16, weight="bold")

        # Define buttons data with professional colored icons and distinct hex codes
        self.buttons_info = [
            {"name": "home", "text": " 首頁", "color": "#1E88E5", "icon": "home.png"},       
            {"name": "download", "text": " 影音下載", "color": "#00897B", "icon": "download.png"}, 
            {"name": "audio", "text": " 人聲分離", "color": "#43A047", "icon": "audio.png"},   
            {"name": "ktv", "text": " 錄音合成", "color": "#E53935", "icon": "ktv.png"},  
            {"name": "subtitle", "text": " 生成字幕", "color": "#8E24AA", "icon": "subtitle.png"}, 
            {"name": "tts", "text": " 微軟語音", "color": "#039BE5", "icon": "tts.png"},    
            {"name": "clone", "text": " 聲音複製", "color": "#D81B60", "icon": "clone.png"},  
            {"name": "rvc", "text": " RVC 變聲", "color": "#F4511E", "icon": "rvc.png"},    
            {"name": "realtime_vc", "text": " 即時變聲", "color": "#FF8F00", "icon": "realtime_vc.png"}, 
            {"name": "toolbox", "text": " 影音小工具", "color": "#6D4C41", "icon": "toolbox.png"}    
        ]
        
        # [NEW] Dynamic Lite/Full Version Detection
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        gpt_sovits_path = os.path.join(base_dir, "GPT-SoVITS")
        if not os.path.isdir(gpt_sovits_path):
            # If folder is missing, run in Lite mode (hide Voice Cloning)
            self.buttons_info = [item for item in self.buttons_info if item["name"] != "clone"]
        
        self.nav_buttons = {}
        self.nav_images = {}
        icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icons")
        
        # Create Buttons (Capsule style with real images)
        for i, btn_data in enumerate(self.buttons_info):
            img = None
            icon_path = os.path.join(icons_dir, btn_data["icon"])
            if os.path.exists(icon_path):
                img = ctk.CTkImage(light_image=Image.open(icon_path), size=(22, 22))
                self.nav_images[btn_data["name"]] = img

            btn = ctk.CTkButton(self.navigation_frame, corner_radius=8, height=45, border_spacing=10,
                                text=btn_data["text"],
                                image=img,
                                compound="left",
                                fg_color="transparent",
                                text_color=("gray20", "gray85"),
                                hover_color=("gray70", "#2A2D35"), # Subtle hover
                                anchor="w", 
                                font=self.menu_font,
                                command=lambda name=btn_data["name"]: self.select_frame_by_name(name))
            # Padding to create the capsule look inside the sidebar
            btn.grid(row=i, column=0, sticky="ew", padx=10, pady=(2, 2))
            if i == 0:
                 btn.grid(pady=(15, 2)) # Extra top padding for the first item
            self.nav_buttons[btn_data["name"]] = btn

        # 2. Initialize Views
        self.home_view = HomeView(self, corner_radius=0, fg_color="transparent")
        self.download_view = DownloadView(self, corner_radius=0, fg_color="transparent")
        self.audio_view = AudioView(self, corner_radius=0, fg_color="transparent")
        self.subtitle_view = SubtitleView(self, corner_radius=0, fg_color="transparent")
        self.rvc_view = RVCView(self, corner_radius=0, fg_color="transparent")
        self.realtime_vc_view = RealTimeVCView(self, corner_radius=0, fg_color="transparent")
        self.ktv_view = KTVView(self, corner_radius=0, fg_color="transparent")
        self.toolbox_view = ToolboxView(self, corner_radius=0, fg_color="transparent")
        self.tts_view = TTSView(self, corner_radius=0, fg_color="transparent")
        self.clone_view = CloneView(self, corner_radius=0, fg_color="transparent")
        
        # Initialize current frame tracker
        self.current_frame = None

        # Select default view
        self.select_frame_by_name("home")

        # [NEW] Theme Switch (Top Right)
        self.theme_switch = ctk.CTkOptionMenu(self, values=["深色模式 (Dark)", "淺色模式 (Light)"], 
                                              command=self.change_appearance_mode_event,
                                              font=self.menu_font, dropdown_font=self.menu_font, width=160)
        self.theme_switch.place(relx=0.98, rely=0.02, anchor="ne")
        
        # [NEW] Keyboard Navigation for Sidebar
        self.bind("<Control-Tab>", self.next_tab)
        self.bind("<Control-Shift-Tab>", self.prev_tab)

    def change_appearance_mode_event(self, new_appearance_mode: str):
        if "Dark" in new_appearance_mode or "深色" in new_appearance_mode:
            ctk.set_appearance_mode("Dark")
        else:
            ctk.set_appearance_mode("Light")

    def next_tab(self, event=None):
        names = [btn["name"] for btn in self.buttons_info]
        if self.current_frame in names:
            idx = names.index(self.current_frame)
            next_idx = (idx + 1) % len(names)
            self.select_frame_by_name(names[next_idx])
        return "break"

    def prev_tab(self, event=None):
        names = [btn["name"] for btn in self.buttons_info]
        if self.current_frame in names:
            idx = names.index(self.current_frame)
            prev_idx = (idx - 1) % len(names)
            self.select_frame_by_name(names[prev_idx])
        return "break"

    def select_frame_by_name(self, name):
        # Update button colors
        for btn_name, btn in self.nav_buttons.items():
            if btn_name == name:
                # Active State: Colored background, white text
                target_color = next((item["color"] for item in self.buttons_info if item["name"] == btn_name), "#3949AB")
                btn.configure(fg_color=target_color, text_color=("white", "white"))
            else:
                # Inactive State: Transparent background, muted text
                btn.configure(fg_color="transparent", text_color=("gray20", "gray85"))
            
        # Hide all frames
        for view in [self.home_view, self.download_view, self.audio_view, self.subtitle_view, self.rvc_view, self.realtime_vc_view, self.ktv_view, self.toolbox_view, self.tts_view, self.clone_view]:
             if hasattr(view, "on_leave") and view.winfo_viewable() and self.current_frame == "ktv" and name != "ktv":
                  # Specific check for KTV cleanup or generic on_leave
                  view.on_leave()
             view.grid_forget()

        # Show selected frame
        view_map = {
            "home": self.home_view,
            "download": self.download_view,
            "audio": self.audio_view,
            "subtitle": self.subtitle_view,
            "rvc": self.rvc_view,
            "realtime_vc": self.realtime_vc_view,
            "ktv": self.ktv_view,
            "toolbox": self.toolbox_view,
            "tts": self.tts_view,
            "clone": self.clone_view
        }
        
        if name in view_map:
            view = view_map[name]
            view.grid(row=0, column=1, sticky="nsew")
            if hasattr(view, "on_enter"):
                view.on_enter()
            
        self.current_frame = name

    def on_closing(self):
        # Cleanup tasks before shutdown
        if hasattr(self, "clone_view") and hasattr(self.clone_view, "stop_api_server"):
            try:
                self.clone_view.stop_api_server()
            except Exception as e:
                print(f"Error stopping API on close: {e}")
                
        # Call the original destroy method
        self.destroy()

if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    
    # [NEW: PyInstaller sys.path optimization]
    # Ensure current directory and modules folder are in sys.path for external plugins
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        if exe_dir not in sys.path:
            sys.path.insert(0, exe_dir)
        
        modules_dir = os.path.join(exe_dir, "modules")
        if os.path.exists(modules_dir) and modules_dir not in sys.path:
            sys.path.insert(0, modules_dir)

    # Handle RVC CLI arg if frozen (to avoid multiple GUI instances)
    if "--rvc_cli" in sys.argv:
        # Import directly to avoid namespace issues when frozen
        try:
            import rvc_cli
            rvc_main = rvc_cli.main
        except ImportError:
            # Fallback to modules.rvc_cli
            from modules.rvc_cli import main as rvc_main
            
        # Remove our flag from argv before passing to rvc_cli
        sys.argv.remove("--rvc_cli")
        rvc_main()
    else:
        # [NEW: Close Isolated Splash Process]
        if splash_proc:
            try:
                splash_proc.terminate()
            except:
                pass
                
        # Set Windows App ID to separate taskbar icon from generic python.exe
        try:
            import ctypes
            myappid = 'studio0808.video.app.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        app = App()
        app.mainloop()

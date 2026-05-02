import os
import sys
import time
import threading
import queue
import numpy as np
import torch
import sounddevice as sd
import traceback
import signal
import librosa
import scipy.signal as signal_proc
import torch
import logging

# RTX 5060 Compatibility Fix: Disable unstable SDPA kernels for real-time engine
try:
    if torch.cuda.is_available():
        try:
            torch.backends.cuda.enable_flash_sdp(False)
            torch.backends.cuda.enable_mem_efficient_sdp(False)
            torch.backends.cuda.enable_math_sdp(True)
        except:
            pass
except:
    pass

# Ensure we can import RVC modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# Ensure absolute paths for model loading
os.environ["rmvpe_root"] = current_dir
os.environ["hubert_root"] = current_dir

try:
    import faiss
    _orig_read_index = faiss.read_index
    
    def patched_read_index(path, *args, **kwargs):
        # Always use short path for faiss.read_index on Windows
        if sys.platform == "win32":
            # 1. Try short path first
            short_path = get_short_path_name(path)
            
            # 2. Strong Shadow File mechanism if path still contains non-ASCII
            import re
            if any(ord(c) > 127 for c in short_path):
                import tempfile
                import shutil
                tmp_dir = tempfile.gettempdir()
                shadow_path = os.path.join(tmp_dir, f"rvc_idx_{hash(path) & 0xFFFFFFFF}.index")
                
                # Check if we need to sync/copy (only if destination doesn't exist or is older)
                if not os.path.exists(shadow_path) or os.path.getmtime(path) > os.path.getmtime(shadow_path):
                    try:
                        # Try symbolic link first (faster, needs admin or specific win setting)
                        if hasattr(os, 'symlink'):
                             os.symlink(path, shadow_path)
                        else:
                             shutil.copy2(path, shadow_path)
                    except:
                        # Fallback to hard copy if symlink fails
                        shutil.copy2(path, shadow_path)
                
                # print(f"[Shadow-File] Original: {path} -> Shadow: {shadow_path}")
                return _orig_read_index(shadow_path, *args, **kwargs)
                
            return _orig_read_index(short_path, *args, **kwargs)
        return _orig_read_index(path, *args, **kwargs)
    faiss.read_index = patched_read_index
except ImportError:
    pass
except Exception as e:
    print(f"Warning: Failed to patch faiss: {e}")

# Silence torchfcpe noise
class FCPEFilter(logging.Filter):
    def filter(self, record):
        return "torchfcpe" not in record.name and "min value" not in record.getMessage()

logging.getLogger().addFilter(FCPEFilter())
logging.getLogger("torchfcpe").setLevel(logging.ERROR)

try:
    try:
        import infer.modules.vc.utils as vc_utils
        from configs.config import Config
        from infer.modules.vc.modules import VC
    except ImportError:
        import modules.infer.modules.vc.utils as vc_utils
        from modules.configs.config import Config
        from modules.infer.modules.vc.modules import VC
        
    # vc_utils.load_hubert is now handled internally in utils.py
    HAS_RVC_LIBS = True
except Exception as e:
    print(f"Warning: RVC modules not found. Real-time VC will not work. ({type(e).__name__}: {e})")
    VC = None
    class Config:
        def __init__(self):
            self.device = "cpu"
            self.is_half = False

def fast_resample(audio, orig_sr, target_sr):
    """
    使用 scipy.signal.resample_poly 進行高速重取樣，比 librosa 快得多。
    """
    if orig_sr == target_sr:
        return audio
    
    # 計算最大公約數以簡化比例
    import numpy as np
    gcd = np.gcd(orig_sr, target_sr)
    up = target_sr // gcd
    down = orig_sr // gcd
    
    return signal_proc.resample_poly(audio, up, down)

def get_short_path_name(long_name):
    """
    獲取 Windows 短路徑 (8.3 格式)，用於解決 Faiss 等組件不支援中文路徑的問題。
    """
    if sys.platform != "win32":
        return long_name
    try:
        # Normalize path separators and use absolute path
        long_name = os.path.abspath(os.path.normpath(long_name))
        if not os.path.exists(long_name):
            return long_name

        import ctypes
        from ctypes import wintypes
        _GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
        _GetShortPathNameW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        _GetShortPathNameW.restype = wintypes.DWORD
        
        # Get required buffer size
        output_buf_size = _GetShortPathNameW(long_name, None, 0)
        if output_buf_size == 0:
            return long_name
            
        output_buf = ctypes.create_unicode_buffer(output_buf_size)
        needed = _GetShortPathNameW(long_name, output_buf, output_buf_size)
        
        if needed > 0 and needed < output_buf_size:
            return output_buf.value
        return long_name
    except:
        return long_name

class RealTimeRVCEngine:
    def __init__(self):
        self.config = Config()
        # 使用安全 CUDA 檢查來決定裝置
        try:
            root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sys.path.insert(0, root_dir)
            from utils.gpu_utils import safe_check_cuda
            cuda_ok, _ = safe_check_cuda()
        except Exception:
            cuda_ok = torch.cuda.is_available()
        
        self.config.device = "cuda" if cuda_ok else "cpu"
        self.config.is_half = True if cuda_ok else False
        
        self.vc = None
        self.hubert_model = None
        self.tgt_sr = 40000 # Default, will update on model load
        
        self.running = False
        self.thread = None
        
        # Audio Config
        self.input_device = None
        self.output_device = None
        self.chunk_size = 4096 # Samples per chunk (latency vs stability)
        self.block_time = 0.2 # 200ms approx for 40k
        self.samplerate = 40000 
        
        # RVC Params
        self.pitch = 0
        self.f0_method = "fcpe"
        self.index_path = None
        self.index_rate = 0.75
        self.filter_radius = 3
        self.rms_mix_rate = 0.25
        self.protect = 0.33
        
        # Audio Queues
        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()
        
        # Gain & VAD
        self.input_gain = 1.0
        self.output_gain = 1.0
        self.threshold = -40 # dB
        self.silence_delay = 0.5 
        self.silence_count = 0.0 
        
        self.use_rnnoise = False
        
        # Audio Processing Buffers
        self.fade_samples = 880 # ~20ms
        self.prev_out = None
        
        # Recording
        self.record_audio = False
        self.audio_buffer = []
        self.output_dir = None

    def load_model(self, model_path, index_path=None):
        try:
            if self.vc is None:
                self.vc = VC(self.config)
            
            # Pre-process paths to short names for Windows compatibility
            # Pre-process paths to short names for Windows compatibility
            if sys.platform == "win32":
                print(f"[RealTimeRVC] Original Model Path: {model_path}")
                model_path = get_short_path_name(model_path)
                print(f"[RealTimeRVC] Shortened Model Path: {model_path}")
                if index_path:
                    print(f"[RealTimeRVC] Original Index Path: {index_path}")
                    index_path = get_short_path_name(index_path)
                    print(f"[RealTimeRVC] Shortened Index Path: {index_path}")

            model_dir = os.path.dirname(model_path)
            os.environ["weight_root"] = model_dir
            os.environ["index_root"] = model_dir
            os.environ["rmvpe_root"] = current_dir
            
            filename = os.path.basename(model_path)
            self.vc.get_vc(filename)
            self.tgt_sr = self.vc.tgt_sr
            
            if self.vc.hubert_model is None:
                print(f"[RealTimeRVC] Loading Hubert model...")
                self.vc.hubert_model = vc_utils.load_hubert(self.config)
            
            self.index_path = index_path
            print(f"[RealTimeRVC] Loaded model: {filename}, SR: {self.tgt_sr}")
            return True
        except Exception as e:
            print(f"[RealTimeRVC] Error loading model: {e}")
            traceback.print_exc()
            return False

    def start(self, input_idx, output_idx, chunk_duration=0.3, record_audio=False, output_dir=None):
        if self.running:
            self.stop()
            
        self.input_device = input_idx
        self.output_device = output_idx
        self.block_time = chunk_duration
        self.record_audio = record_audio
        self.output_dir = output_dir
        self.audio_buffer = []
        
        # chunk_duration in seconds. 0.3s = 300ms.
        # RVC 40k -> 12000 samples.
        # We need to ensure we match RVC's expected inputs logic or standard raw audio.
        # vc_single expects raw audio path usually. 
        # But we want to pass memory buffer.
        # vc.vc_single calls `get_f0` which takes audio numpy array.
        # Wait, `vc_single` takes path?
        # Let's check `vc.vc_single` signature in `rvc_cli.py`:
        # input_audio_path=args.input
        
        # I need to modify or bypass `vc_single` to accept numpy array directly.
        # `VC.vc_single` (in `infer/modules/vc/modules.py`) calls `get_f0`.
        # I should check if I can pass array.
        # If not, I might need to write a temp file (too slow) or modify `VC`.
        # OR, I can copy the `pipeline` logic.
        
        # Let's assume for now I'll write to RAM disk (if on Linux) or just use `vc.pipeline` directly if I can.
        # Validating `VC` structure... `vc.pipeline` object exists.
        # logic: `self.pipeline = Pipeline(self.tgt_sr, config)`
        # `self.pipeline.pipeline(...)`
        
        self.running = True
        self.thread = threading.Thread(target=self._processing_loop)
        self.thread.start()
        print(f"[RealTimeRVC] Started audio loop. In: {input_idx}, Out: {output_idx}, Chunk: {self.block_time}s")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        
        # Clear queues
        with self.input_queue.mutex:
            self.input_queue.queue.clear()
        with self.output_queue.mutex:
            self.output_queue.queue.clear()
            
        saved_path = None
        if self.record_audio and len(self.audio_buffer) > 0 and self.output_dir:
            try:
                import soundfile as sf
                import datetime
                
                # Concatenate all chunks and write to WAV
                full_audio = np.concatenate(self.audio_buffer)
                
                # Generate timestamp filename
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"rvc_record_{timestamp}.wav"
                
                if not os.path.exists(self.output_dir):
                    os.makedirs(self.output_dir)
                    
                saved_path = os.path.join(self.output_dir, filename)
                sf.write(saved_path, full_audio, self.tgt_sr)
                print(f"[RealTimeRVC] Audio saved to {saved_path}")
            except Exception as e:
                print(f"[RealTimeRVC] Error saving audio: {e}")
            finally:
                self.audio_buffer = [] # Clear memory
                
        print("[RealTimeRVC] Stopped.")
        return saved_path

    def _processing_loop(self):
        try:
            fs = self.tgt_sr # RVC Target Sample Rate
            # Query device info for best compatibility (Mirror RecordingAssistant logic)
            in_info = sd.query_devices(self.input_device, 'input')
            out_info = sd.query_devices(self.output_device, 'output')
            
            in_fs = int(in_info['default_samplerate'])
            in_channels = min(2, in_info['max_input_channels'])
            if in_channels <= 0: in_channels = 1
            
            out_fs = int(out_info['default_samplerate'])
            out_channels = min(2, out_info['max_output_channels'])
            if out_channels <= 0: out_channels = 1
            
            in_block = int(in_fs * self.block_time)
            out_block = int(out_fs * self.block_time)
            
            print(f"[RealTimeRVC] Hardware Init:")
            print(f"   In: {in_info['name']} | {in_fs}Hz | {in_channels}ch")
            print(f"   Out: {out_info['name']} | {out_fs}Hz | {out_channels}ch")
            print(f"   Model SR: {fs}Hz | Chunk: {self.block_time}s")

            # Separate input/output streams
            with sd.InputStream(device=self.input_device, samplerate=in_fs, 
                                blocksize=in_block, dtype='float32', channels=in_channels) as in_stream, \
                 sd.OutputStream(device=self.output_device, samplerate=out_fs, 
                                 blocksize=out_block, dtype='float32', channels=out_channels) as out_stream:
                
                print(f"[RealTimeRVC] Robust Loop Started.")
                while self.running:
                    # 1. Catch up to latest chunk (Lag Prevention)
                    while in_stream.read_available > in_block * 1.5:
                         in_stream.read(in_block)
                    
                    indata, overflow = in_stream.read(in_block)
                    if overflow: print("[RealTimeRVC] Input overflow")
                    
                    # 2. Pre-process: To Mono (average channels)
                    if in_channels > 1:
                        indata_mono = np.mean(indata, axis=1)
                    else:
                        indata_mono = indata.flatten()
                    
                    # 3. Resample: Hardware SR -> RVC SR (e.g. 40k)
                    audio_rvc = fast_resample(indata_mono, in_fs, fs)
                    
                    # 4. RVC Inference
                    out_rvc = self._process_audio(audio_rvc, fs)
                    
                    # 5. Resample: RVC SR -> Output SR
                    out_hw_mono = fast_resample(out_rvc.flatten(), fs, out_fs)
                    
                    # 6. Post-process: To Output Channels (Ensure 2D for sounddevice)
                    if out_channels > 1:
                        # Stack to (frames, 2)
                        out_hw = np.stack([out_hw_mono, out_hw_mono], axis=1)
                    else:
                        # Reshape to (frames, 1)
                        out_hw = out_hw_mono.reshape(-1, 1)
                    
                    # 7. Playback
                    out_stream.write(out_hw.astype('float32'))

        except Exception as e:
            print(f"[RealTimeRVC] Loop error: {e}")
            traceback.print_exc()
            self.running = False

    def _process_audio(self, indata, fs):
        """Pure RVC inference (No VAD/Crossfade) to trace echoes."""
        if self.vc and self.vc.pipeline:
            audio_data = indata.flatten() * self.input_gain
            
            # Simple Threshold (No hangover)
            rms = np.sqrt(np.mean(audio_data**2) + 1e-9)
            db = 20 * np.log10(rms)
            if db < self.threshold:
                return np.zeros_like(audio_data).reshape(-1, 1)
                
            try:
                audio_16k = fast_resample(audio_data, fs, 16000)
                wav_opt = self.vc.pipeline.pipeline(
                    self.vc.hubert_model, self.vc.net_g, 0,
                    audio_16k, "buffer", [0,0,0],
                    self.pitch, self.f0_method, self.index_path, self.index_rate,
                    self.vc.if_f0, self.filter_radius, self.tgt_sr, 0,
                    self.rms_mix_rate, self.vc.version, self.protect, None
                )
                
                # Resample back
                if self.tgt_sr != fs:
                    outdata = fast_resample(wav_opt, self.tgt_sr, fs)
                else:
                    outdata = wav_opt
                
                # Match length (Pure crop/pad)
                target_len = len(audio_data)
                if len(outdata) > target_len:
                    outdata = outdata[:target_len]
                elif len(outdata) < target_len:
                    outdata = np.pad(outdata, (0, target_len - len(outdata)))

                # Scale & Gain
                if outdata.dtype == np.int16:
                    outdata = outdata.astype(np.float32) / 32768.0
                outdata = outdata * self.output_gain
                
                return outdata.reshape(-1, 1)
                
            except Exception as ex:
                print(f"[RealTimeRVC] Inference error: {ex}")
                return audio_data.reshape(-1, 1)
        else:
            return indata.flatten().reshape(-1, 1)

    def _run_stream_loop(self, stream, fs, frames_needed):
        """Blocking read/write loop for a combined bidirectional sd.Stream."""
        while self.running:
            if stream.closed:
                break
            indata, overflow = stream.read(frames_needed)
            if overflow:
                print("Input overflow")
            stream.write(self._process_audio(indata, fs).astype('float32'))

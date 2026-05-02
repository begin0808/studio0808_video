import os
import sys
import ctypes

# [相容性修補] omegaconf 2.3.0 移除了 _utils.get_ref_type，但 hydra-core 1.0.7 仍需要它
# 這裡重新注入等效實作，讓 fairseq -> hydra -> omegaconf 的匯入鏈不會斷掉
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
    pass

# Force UTF-8 for console output to avoid UnicodeEncodeError in Windows CMD
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

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

import traceback
import argparse
import logging
import warnings

# Monkey Patch Faiss to support Chinese paths on Windows
try:
    import faiss
    _orig_read_index = faiss.read_index
    def patched_read_index(path, *args, **kwargs):
        # Always use short path for faiss.read_index on Windows
        if sys.platform == "win32":
            # 1. Try short path first
            short_path = get_short_path_name(path)
            
            # 2. Strong Shadow File mechanism if path still contains non-ASCII
            if any(ord(c) > 127 for c in short_path):
                import tempfile
                import shutil
                tmp_dir = tempfile.gettempdir()
                shadow_path = os.path.join(tmp_dir, f"rvc_cli_idx_{hash(path) & 0xFFFFFFFF}.index")
                
                if not os.path.exists(shadow_path) or os.path.getmtime(path) > os.path.getmtime(shadow_path):
                    try:
                        if hasattr(os, 'symlink'):
                             os.symlink(path, shadow_path)
                        else:
                             shutil.copy2(path, shadow_path)
                    except:
                        shutil.copy2(path, shadow_path)
                return _orig_read_index(shadow_path, *args, **kwargs)
                
            return _orig_read_index(short_path, *args, **kwargs)
        return _orig_read_index(path, *args, **kwargs)
    faiss.read_index = patched_read_index
except ImportError:
    pass
except Exception as e:
    print(f"Warning: Failed to patch faiss: {e}")


# Pytorch Memory Config
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

print(f"[DEBUG] RVC CLI Starting... (Process {os.getpid()})", flush=True)

# Suppress warnings
warnings.filterwarnings("ignore")
logging.getLogger("numba").setLevel(logging.WARNING)
logging.getLogger("markdown_it").setLevel(logging.WARNING)

# Add current directory to sys.path (High Priority)
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Add parent directory as well to allow 'from modules.xxx' if needed
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Add FFmpeg to PATH (located in ../tools relative to this script)
if getattr(sys, 'frozen', False):
    root_dir = os.path.dirname(sys.executable)
else:
    root_dir = os.path.dirname(current_dir)

ffmpeg_dir = os.path.join(root_dir, "tools")
if os.path.exists(ffmpeg_dir):
    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ["PATH"]
    print(f"[DEBUG] Added to PATH: {ffmpeg_dir}")

# --- Environment Setup (CRITICAL for RVC V2) ---
# Ensure absolute paths for model loading in both local and bundled environments
os.environ["rmvpe_root"] = current_dir # rmvpe.pt is located in modules/
os.environ["hubert_root"] = current_dir # hubert_base.pt is located in modules/
os.environ["weight_root"] = ""         # Will be set dynamically or passed
os.environ["index_root"] = ""          # Will be set dynamically

# Helper to debug imports
def debug_imports():
    print(f"[DEBUG] Current sys.path: {sys.path}")
    print(f"[DEBUG] Current Directory: {os.getcwd()}")
    print(f"[DEBUG] Looking for infer in: {os.path.join(current_dir, 'infer')}")
    if os.path.exists(os.path.join(current_dir, 'infer')):
        print(f"[DEBUG] 'infer' folder found.")
    else:
        print(f"[DEBUG] 'infer' folder NOT found in {current_dir}")

try:
    # Use absolute import logic to avoid conflict with standard packages
    import importlib.util

    def dynamic_import(module_name, path):
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    # Load modules one by one from local directory
    # Note: infer.lib and other subdirs already have __init__.py now
    try:
        import infer.modules.vc.utils as vc_utils
        from configs.config import Config
        from infer.modules.vc.modules import VC
    except ImportError:
        # Fallback for complex packaging
        import modules.infer.modules.vc.utils as vc_utils
        from modules.configs.config import Config
        from modules.infer.modules.vc.modules import VC
        
# vc_utils.load_hubert is now handled internally in utils.py
    HAS_RVC_LIBS = True
    MISSING_LIB_MSG = ""
except Exception as e:
    HAS_RVC_LIBS = False
    debug_imports()
    MISSING_LIB_MSG = f"{str(e)}"


def run_inference(args):
    if not HAS_RVC_LIBS:
        print(f"ERROR: Missing RVC libraries. {MISSING_LIB_MSG}")
        sys.exit(1)

    print(f"[RVC] Initializing...")
    
    # Set model root envs based on args
    model_dir = os.path.dirname(args.model)
    os.environ["weight_root"] = model_dir
    os.environ["index_root"] = model_dir

    # Mock argv for Config() to avoid parsing our custom args
    _argv = sys.argv
    sys.argv = [sys.argv[0]]
    try:
        config = Config()
    finally:
        sys.argv = _argv

    config.device = args.device if args.device else config.device
    config.is_half = args.is_half
    
    # Force cpu if requested? Config handles it based on device string
    
    # 3. Initialize VC
    print(f"[RVC] Loading VC Pipeline...")
    vc = VC(config)
    
    # 4. Get VC (Load Model)
    print(f"[RVC] Loading Model: {os.path.basename(args.model)}...")
    sid = os.path.basename(args.model) # filename only
    
    # VC.get_vc expects sid (filename) and looks in weight_root
    try:
        vc.get_vc(sid)
    except Exception as e:
        print(f"ERROR: Failed to load model '{sid}': {e}")
        sys.exit(1)
    
    # 5. Inference
    print(f"[RVC] Transforming audio...")
    
    try:
        # Using vc_single
        info, opt = vc.vc_single(
            sid=0, # Not used in vc_single logic usually, or just mapping
            input_audio_path=args.input,
            f0_up_key=args.pitch,
            f0_file=None,
            f0_method=args.f0,
            file_index=args.index,
            file_index2="",
            index_rate=args.index_rate,
            filter_radius=args.filter_radius,
            resample_sr=0,
            rms_mix_rate=args.rms_mix_rate,
            protect=args.protect
        )
    except (RuntimeError, Exception) as e:
        err_str = str(e).lower()
        cuda_keywords = ["out of memory", "cuda error", "no kernel image", "cuda driver",
                         "insufficient", "cublas", "cudnn", "not compiled", "cuda runtime",
                         "cuda_error", "cusolver", "cufft", "curand"]
        is_cuda_error = any(kw in err_str for kw in cuda_keywords)
        
        if is_cuda_error and "cuda" in str(config.device).lower():
            if "out of memory" in err_str:
                print(f"[WARNING] CUDA Out of Memory. Switching to CPU for this inference...")
            else:
                print(f"[WARNING] CUDA Error detected ({e}). Switching to CPU...")
            print(f"[WARNING] CPU inference will be slower but more stable.")
            
            # Clear Cache
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except: pass
            
            # Switch config to CPU
            config.device = "cpu"
            config.is_half = False # CPU doesn't support half well usually
            
            # Re-init VC on CPU
            vc = VC(config)
            vc.get_vc(sid)
            
            info, opt = vc.vc_single(
                sid=0,
                input_audio_path=args.input,
                f0_up_key=args.pitch,
                f0_file=None,
                f0_method=args.f0,
                file_index=args.index,
                file_index2="",
                index_rate=args.index_rate,
                filter_radius=args.filter_radius,
                resample_sr=0,
                rms_mix_rate=args.rms_mix_rate,
                protect=args.protect
            )
        else:
            raise e
    
    if "Success" in info:
        print(f"[RVC] {info}")
        tgt_sr, audio_opt = opt
        
        # 6. Save Output
        import scipy.io.wavfile as wavfile
        print(f"[RVC] Saving to: {args.output}")
        wavfile.write(args.output, tgt_sr, audio_opt)
        print(f"[RVC] Success.")
    else:
        print(f"[RVC] Error during inference: {info}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--pitch", type=float, default=0)
    parser.add_argument("--f0", default="rmvpe")
    parser.add_argument("--index", default="")
    parser.add_argument("--index_rate", type=float, default=0.75)
    parser.add_argument("--filter_radius", type=int, default=3)
    parser.add_argument("--rms_mix_rate", type=float, default=0.25)
    parser.add_argument("--protect", type=float, default=0.33)
    
    # Advanced / System args - Auto-detect CUDA availability
    # Use safe check to determine default device
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from utils.gpu_utils import safe_check_cuda
        _cuda_ok, _ = safe_check_cuda()
        default_device = "cuda:0" if _cuda_ok else "cpu"
    except Exception:
        default_device = "cuda:0" if torch.cuda.is_available() else "cpu"
    
    parser.add_argument("--device", default=default_device) # Auto-detected
    parser.add_argument("--is_half", action="store_true")
    
    args = parser.parse_args()
    
    # Pre-process paths to short names for Windows compatibility with non-ASCII characters
    if sys.platform == "win32":
        print(f"[DEBUG] Converting paths to short names for compatibility...")
        args.model = get_short_path_name(args.model)
        args.input = get_short_path_name(args.input)
        args.output = get_short_path_name(args.output)
        if args.index:
            args.index = get_short_path_name(args.index)
        print(f"[DEBUG] Short Model Path: {args.model}")
        print(f"[DEBUG] Short Index Path: {args.index}")

    run_inference(args)

if __name__ == "__main__":
    main()

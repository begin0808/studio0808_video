import os
import sys
import subprocess
import shutil

def build_app():
    print("========================================")
    print("  Studio0808 PyInstaller Build Script   ")
    print("========================================")

    # 1. Determine paths
    current_dir = os.path.dirname(os.path.abspath(__file__))
    main_script = os.path.join(current_dir, "Studio0808_Video.py")
    
    if not os.path.exists(main_script):
        print(f"錯誤: 找不到主程式 {main_script}")
        sys.exit(1)

    # 2. Define directories to exclude (these will be copied over manually later)
    # We don't need to tell PyInstaller to exclude them if we don't 'import' them or add them via --add-data,
    # but we should ensure they aren't accidentally included if any module tries to grab the whole folder.
    # The main strategy is: Do NOT use --add-data for these large folders.
    large_dirs = ["models", "tools", "GPT-SoVITS"]
    
    # 3. Define data to include (assets, icons)
    # Format for Windows: "source_path;destination_folder"
    datas = [
        (os.path.join(current_dir, "assets"), "assets"),
        (os.path.join(current_dir, "app.ico"), "."),
        (os.path.join(current_dir, "button_text_preview.txt"), "."),
        (os.path.join(current_dir, "buttons_all.txt"), "."),
        (os.path.join(current_dir, "voices.txt"), "."),
        (os.path.join(current_dir, "voices_zh.txt"), "."),
        (os.path.join(current_dir, "zh_list.txt"), "."),
        (os.path.join(current_dir, "zh_voices.txt"), "."),
        (os.path.join(current_dir, "zh_voices_direct.txt"), ".")
    ]

    data_args = []
    for src, dst in datas:
        if os.path.exists(src):
            data_args.extend(["--add-data", f"{src};{dst}"])
        else:
            print(f"警告: 找不到靜態資源 {src}，將跳過。")

    # 4. Construct PyInstaller command
    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",           # Overwrite output directory without asking
        "--onedir",              # Create a one-folder bundle containing an executable
        "--windowed",            # Do not provide a console window for standard i/o
        "--collect-data", "demucs", # [NEW] Prevent files.txt error
        "--copy-metadata", "audio-separator", # [NEW] Prevent VR De-Reverb NoneType version error
        "--collect-data", "audio_separator", # [NEW] Prevent models-scores.json error
        "--collect-submodules", "audio_separator", # [NEW] Prevent missing architectures error
        "--collect-submodules", "scipy", # [NEW] Prevent scipy._lib.array_api_compat error
        "--collect-all", "samplerate", # [NEW] Prevent module 'samplerate' has no attribute 'resample'
        "--collect-all", "fairseq",    # [NEW] Fix dynamic import path error (WinError 3)
        "--collect-all", "ffmpeg",     # [NEW] Ensure ffmpeg-python wrapper is collected
        "--collect-all", "av",         # [NEW] Ensure PyAV and its DLLs are collected
        "--collect-all", "faiss",      # [NEW] Ensure faiss DLLs are collected
        "--collect-all", "onnxruntime", # [NEW] Ensure onnxruntime DLLs are collected
        "--collect-all", "soundfile",  # [NEW] Ensure libsndfile DLL is collected
        "--collect-all", "torch",      # [NEW] Ensure torch submodules and DLLs are collected
        "--collect-all", "librosa",    # [NEW] Ensure librosa and its decoratings are collected
        "--collect-all", "parselmouth", # [NEW] Fix missing parselmouth for PM f0 estimation
        "--collect-all", "pyworld",     # [NEW] Fix missing pyworld for Harvest f0 estimation
        "--collect-all", "torchcrepe",  # [NEW] Fix missing torchcrepe for Crepe f0 estimation
        "--collect-all", "torchfcpe",   # [NEW] Fix missing torchfcpe for FCPE f0 estimation
        "--collect-data", "lightning_fabric", # [NEW] Fix speaker diarization (version.info missing)
        "--collect-all", "pyannote.audio",    # [NEW] Fix missing pyannote.audio.pipelines
        "--collect-all", "speechbrain",       # [NEW] Fix potential speechbrain missing modules
        "--icon", os.path.join(current_dir, "app.ico"),
        "--manifest", os.path.join(current_dir, "app.manifest"),
        "--name", "Studio0808"
    ]
    
    # Add data arguments
    pyinstaller_cmd.extend(data_args)

    # Add hidden imports if necessary (e.g., dynamically loaded modules)
    hidden_imports = [
        "PIL._tkinter_finder",
        "customtkinter",
        "torchaudio",
        "torchvision",
        "pydub",
        "audio_separator",
        "audio_separator.separator",
        "audio_separator.separator.architectures",
        "onnx",
        "onnxruntime",
        "onnx2torch",
        "julius",
        "diffq",
        "einops",
        "ml_collections",
        "yaml",
        "samplerate",
        "omegaconf",
        "fairseq"
    ]
    for imp in hidden_imports:
        pyinstaller_cmd.extend(["--hidden-import", imp])

    # Target script
    pyinstaller_cmd.append(main_script)

    print("\n[1/3] 執行 PyInstaller 打包主程式...")
    print("指令: " + " ".join(pyinstaller_cmd))
    print("清除先前的編譯快取 (強迫重新分析)...")
    shutil.rmtree(os.path.join(current_dir, "build", "Studio0808"), ignore_errors=True)
    
    try:
        # [NEW] 將專案根目錄加入 PYTHONPATH 讓 PyInstaller 的獨立程序能吃到 sitecustomize.py 進行相容性修補
        env = os.environ.copy()
        env["PYTHONPATH"] = current_dir + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run(pyinstaller_cmd, env=env, check=True)
        print("PyInstaller 打包完成！")
    except subprocess.CalledProcessError as e:
        print(f"打包失敗，錯誤代碼: {e.returncode}")
        sys.exit(1)

    # 5. Copy essential external directories to dist
    dist_dir = os.path.join(current_dir, "dist", "Studio0808")
    print(f"\n[2/3] 複製必備外部資料夾至 {dist_dir} ...")
    
    if not os.path.exists(dist_dir):
        os.makedirs(dist_dir)
        
    external_dirs = ["models", "tools", "modules", "GPT-SoVITS"]
    
    for folder_name in external_dirs:
        src_folder = os.path.join(current_dir, folder_name)
        dst_folder = os.path.join(dist_dir, folder_name)
        
        if os.path.exists(src_folder):
            print(f"-> 複製資料夾: {folder_name} ...", end="", flush=True)
            try:
                shutil.copytree(src_folder, dst_folder, dirs_exist_ok=True)
                print(" [成功]")
            except Exception as e:
                print(f" [失敗: {e}]")
        else:
            print(f"-> 找不到資料夾: {folder_name}，已跳過。")

    # 6. Create Empty Folders (Outputs, temp)
    # temp 資料夾用途：
    # 1. 簡易剪輯時存放分割的暫時片段與 concat.txt
    # 2. RVC 處理中文路徑時產生的影子檔案 (Shadow Files)
    # 3. 預覽影片時產生的暫時音軌波形檔
    print(f"-> 建立應用程式執行所需資料夾...", end="", flush=True)
    for folder in ["Outputs", "temp"]:
        path = os.path.join(dist_dir, folder)
        if not os.path.exists(path):
            os.makedirs(path)
    print(" [成功]")

    print("\n[3/3] 打包流程結束！")
    print(f"完成！結構已與需求對齊 (包含 _internal, models, tools, modules, GPT-SoVITS, Outputs, temp)")
    print(f"主程式位置: {os.path.join(dist_dir, 'Studio0808.exe')}")

if __name__ == "__main__":
    build_app()

# Updated by AI Assistant for audio-separator dependencies

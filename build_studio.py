import os
import sys
import subprocess
import shutil
import stat

def force_rmtree(dir_path):
    def remove_readonly(func, path, excinfo):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            pass
    if os.path.exists(dir_path):
        shutil.rmtree(dir_path, onerror=remove_readonly)

def build_app():
    print("========================================")
    print("  Studio0808 PyInstaller Build Script   ")
    print("========================================")

    # [NEW] Version and Build Type Prompts
    version = input("請輸入本次發布版本號 (例如 1.0.1，直接 Enter 則預設為今日日期): ").strip()
    if not version:
        import datetime
        version = datetime.datetime.now().strftime("%Y%m%d")
        
    build_type = input("請選擇打包模式 [1] 完整版 (包含所有模型) [2] 更新包 (僅主程式與 _internal): ").strip()
    is_patch = (build_type == "2")
    
    app_folder_name = f"Studio0808_v{version}"
    print(f"\n準備打包發布目錄: dist\\{app_folder_name} ({'更新包模式' if is_patch else '完整版模式'})\n")

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
        "--exclude-module", "torch.distributed",
        "--exclude-module", "tensorboard",
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
        "--collect-data", "faster_whisper",    # [NEW] Fix silero_vad_v6.onnx file missing error
        "--collect-all", "pyannote.audio",    # [NEW] Fix missing pyannote.audio.pipelines
        "--collect-all", "speechbrain",       # [NEW] Fix potential speechbrain missing modules
        "--distpath", os.path.join(current_dir, "build_output"), # [NEW] 輸出到暫存目錄避免動到原本的 dist
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
    print("清除先前的編譯與輸出快取 (強迫重新分析，避免權限錯誤)...")
    force_rmtree(os.path.join(current_dir, "build", "Studio0808"))
    force_rmtree(os.path.join(current_dir, "build_output")) # 只清理暫存輸出，不動 dist\Studio0808
    
    try:
        # [NEW] 將專案根目錄加入 PYTHONPATH 讓 PyInstaller 的獨立程序能吃到 sitecustomize.py 進行相容性修補
        env = os.environ.copy()
        env["PYTHONPATH"] = current_dir + os.pathsep + env.get("PYTHONPATH", "")
        subprocess.run(pyinstaller_cmd, env=env, check=True)
        print("PyInstaller 打包完成！")
    except subprocess.CalledProcessError as e:
        print(f"打包失敗，錯誤代碼: {e.returncode}")
        sys.exit(1)

    # 5. Rename output folder to include version
    pyinstaller_output_dir = os.path.join(current_dir, "build_output", "Studio0808")
    dist_dir_target = os.path.join(current_dir, "dist", app_folder_name)
    
    print("\n[2/3] 整理輸出目錄...")
    if os.path.exists(dist_dir_target):
        force_rmtree(dist_dir_target)
        
    if os.path.exists(pyinstaller_output_dir):
        # 確保 dist 目錄存在
        if not os.path.exists(os.path.join(current_dir, "dist")):
            os.makedirs(os.path.join(current_dir, "dist"))
        # 將打包結果從 build_output 移動到 dist/Studio0808_vXXX
        os.rename(pyinstaller_output_dir, dist_dir_target)
        force_rmtree(os.path.join(current_dir, "build_output")) # 刪除暫存資料夾
        
    dist_dir = dist_dir_target
    
    if is_patch:
        print(f"\n=> 目前為「更新包模式」，已跳過複製大型模型！")
        print(f"=> 您只需要將 {dist_dir} 內的 Studio0808.exe 與 _internal 資料夾打包發布即可。")
    else:
        print(f"\n=> 複製必備外部資料夾至 {dist_dir} ...")
        external_dirs = ["models", "tools", "modules", "GPT-SoVITS"]
        
        for folder_name in external_dirs:
            src_folder = os.path.join(current_dir, folder_name)
            dst_folder = os.path.join(dist_dir, folder_name)
            
            if os.path.exists(src_folder):
                print(f"-> 複製資料夾: {folder_name} ...", end="", flush=True)
                try:
                    shutil.copytree(src_folder, dst_folder, dirs_exist_ok=True, ignore=shutil.ignore_patterns('.git', '__pycache__'))
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

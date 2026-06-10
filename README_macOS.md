# 🍎 Studio0808 AI 影音工具站 - macOS 開發與打包指引

本文件提供給具備 Python 開發經驗的 macOS 開發者，說明如何從原始碼執行、測試並打包本專案。

---

## ⚙️ 準備工作

在開始之前，您的 Mac 需要安裝以下環境與工具：

1. **Xcode Command Line Tools** (編譯 C++ 相關依賴庫，如 `fairseq` 必備)：
   ```bash
   xcode-select --install
   ```

2. **Homebrew** (用來安裝系統級的套件)：
   如果不曾安裝，請先至 [brew.sh](https://brew.sh/) 安裝。接著在終端機安裝 `ffmpeg` 與其他工具：
   ```bash
   brew install ffmpeg yt-dlp deno
   ```

3. **Python 3.10** (建議使用此版本以確保庫的相容性)。

---

## 🛠️ 環境配置與執行

1. **複製專案並建立虛擬環境**：
   ```bash
   git clone https://github.com/begin0808/studio0808_video.git
   cd studio0808_video
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **安裝 Python 依賴套件**：
   由於 `requirements.txt` 中包含 Windows CUDA 的 PyTorch 安裝來源限制，在 macOS 上請分步安裝：
   ```bash
   # 安裝適用於 Mac (支援 Apple Silicon MPS 加速) 的 PyTorch 與 Torchaudio
   pip install torch torchaudio

   # 安裝其餘依賴套件
   pip install -r requirements.txt
   ```
   > ⚠️ **提示**：安裝 `fairseq` 時需要編譯，請確保已成功安裝 Xcode Command Line Tools。

3. **補齊模型檔案 (Models)**：
   本 GitHub 儲存庫為了保持輕量，排除大型模型。請按照以下步驟補齊：
   - 下載 Windows 的「完整版 ZIP 壓縮包」並解壓縮。
   - 將解壓縮後的整個 `models/` 資料夾複製到專案根目錄下。
   - 將 `modules/` 內缺少的 RVC 核心模型（如 `hubert_base.pt`、`rmvpe.pt`）複製到專案的 `modules/` 資料夾中。
   - 若要測試聲音複製，請將 `GPT-SoVITS/` 資料夾也複製過來。
   - 複製 `modules/configs/config.json.example` 並重新命名為 `config.json`。

4. **執行主程式**：
   ```bash
   python Studio0808_Video.py
   ```

---

## ⚠️ macOS 執行注意事項與代碼適配

由於本專案主要基於 Windows 開發，在 macOS 上直接執行時，需要注意並手動修改以下幾點相容性設定：

### 1. `os.startfile` 崩潰問題
macOS 的 Python 沒有內建 `os.startfile`（此為 Windows 專有 API）。當點擊介面中的「開啟輸出資料夾」時會導致程式崩潰。
**💡 解決方案**：
可在主程式 `Studio0808_Video.py` 最上方（或在載入任何 view 之前）加入以下動態修補代碼：
```python
import sys
import os
if sys.platform == 'darwin' and not hasattr(os, 'startfile'):
    import subprocess
    os.startfile = lambda path: subprocess.run(['open', path])
```

### 2. 外部工具與執行檔路徑 (.exe)
專案內部分代碼（如 `download_view.py`、`toolbox_view.py`）硬編碼了 `ffmpeg.exe`、`yt-dlp.exe` 等檔名。
**💡 解決方案**：
- 在 macOS 上無須使用 `tools/` 資料夾內的 `.exe` 檔案。
- 開發者需要適度修改對應 view 檔案（如 `views/download_view.py`），當檢測到系統為 macOS (`sys.platform == 'darwin'`) 時，將執行檔路徑指引至系統的 `ffmpeg` 與 `yt-dlp` 命令。

---

## 📦 macOS 打包說明 (PyInstaller)

當您在 Mac 本地端測試無誤後，可以使用 PyInstaller 打包成獨立的 `.app` 應用程式：

1. **安裝 PyInstaller**：
   ```bash
   pip install pyinstaller
   ```

2. **注意路徑分隔符號**：
   Windows 上的 `--add-data` 參數使用分號 `;` 作為分隔，在 macOS 上必須修改為冒號 `:`。

3. **打包指令範例**：
   在終端機中執行以下指令進行打包：
   ```bash
   pyinstaller --noconfirm --onedir --windowed \
     --add-data "assets:assets" \
     --add-data "app.ico:." \
     --add-data "button_text_preview.txt:." \
     --add-data "buttons_all.txt:." \
     --add-data "voices.txt:." \
     --add-data "voices_zh.txt:." \
     --add-data "zh_list.txt:." \
     --add-data "zh_voices.txt:." \
     --add-data "zh_voices_direct.txt:." \
     --exclude-module torch.distributed \
     --exclude-module tensorboard \
     --collect-data demucs \
     --copy-metadata audio-separator \
     --collect-data audio_separator \
     --collect-submodules audio_separator \
     --collect-submodules scipy \
     --collect-all samplerate \
     --collect-all fairseq \
     --collect-all ffmpeg \
     --collect-all av \
     --collect-all faiss \
     --collect-all onnxruntime \
     --collect-all soundfile \
     --collect-all torch \
     --collect-all librosa \
     --collect-all parselmouth \
     --collect-all pyworld \
     --collect-all torchcrepe \
     --collect-all torchfcpe \
     --collect-data lightning_fabric \
     --collect-data faster_whisper \
     --collect-all pyannote.audio \
     --collect-all speechbrain \
     --hidden-import PIL._tkinter_finder \
     --hidden-import customtkinter \
     --hidden-import torchaudio \
     --hidden-import torchvision \
     --hidden-import pydub \
     --hidden-import audio_separator \
     --hidden-import audio_separator.separator \
     --hidden-import audio_separator.separator.architectures \
     --hidden-import onnx \
     --hidden-import onnxruntime \
     --hidden-import onnx2torch \
     --hidden-import julius \
     --hidden-import diffq \
     --hidden-import einops \
     --hidden-import ml_collections \
     --hidden-import yaml \
     --hidden-import samplerate \
     --hidden-import omegaconf \
     --hidden-import fairseq \
     Studio0808_Video.py
   ```

4. **輸出檔案**：
   打包完成後，可在專案目錄下的 `dist/` 資料夾中找到 macOS 專屬的雙擊可執行應用程式包 `Studio0808.app` 與二進位執行檔。

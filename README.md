# 🎬 Studio0808 AI Video & Audio Workstation

**Unprofessional Audio & Video Processing Suite**

English | [繁體中文](README.zh-TW.md)

A free, offline, and ready-to-use AI audio & video workstation developed by a single person.

[![Download](https://img.shields.io/badge/Download-Full%20Version-blue?style=for-the-badge&logo=googledrive)](https://drive.google.com/file/d/15ZfQhFUGVTCoKxLwNDMinNuGALd3HiYC/view?usp=sharing)
[![Download](https://img.shields.io/badge/Download-Medium%20Version-green?style=for-the-badge&logo=googledrive)](https://drive.google.com/file/d/1WQ4ha5JsA9Tjs8Z6oN7BpP26cZFimnOv/view?usp=sharing)
[![Discord](https://img.shields.io/badge/Discord-Join%20Community-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/F7mC37MBtF)
[![Docs](https://img.shields.io/badge/Documentation-Online-orange?style=for-the-badge&logo=readthedocs)](https://begin0808.github.io/studio0808_video/)

---

## 📸 Screenshots

<p align="center">
  <img src="docs/images/home_view.png" alt="Studio0808 Screenshot" width="800">
</p>

---

## ✨ Features Overview

### 🎯 9 Core Features

| Feature | Description | Core Technology |
|------|------|---------|
| 🎬 **Video/Audio Downloader** | One-click download of videos from 1000+ platforms, supports lossless 4K | yt-dlp + FFmpeg |
| 🎤 **Vocal & Accompaniment Separation** | AI separates vocals, drums, bass, and accompaniment | Meta Demucs + MDX-Net |
| 🎵 **KTV Recording & Synthesis** | Load accompaniment for real-time singing, automatic mixing | WASAPI + AI Noise Reduction |
| 📝 **AI Subtitle Generation** | Auto transcription + translation + bilingual subtitles + hardburning | OpenAI Whisper + Pyannote |
| 🗣️ **Microsoft TTS** | Free AI neural network voice synthesis, multi-language, multi-character | Microsoft Edge-TTS |
| 🧬 **Voice Cloning** | Mimic voice tone and intonation with just 3~10 seconds of audio sample | GPT-SoVITS |
| 🔄 **RVC Voice Changer Inference** | AI cover generation, replacing vocal timbre while preserving emotion | RVC |
| 🎙️ **RVC Real-time Voice Changer** | Real-time voice changing from microphone, supports VB-Cable routing | RVC Real-time |
| 🏋️ **RVC Model Training** | Free training of your own custom voice models via Google Colab | Applio RVC |

### 🛠️ 7 Essential Audio & Video Tools

| Tool | Description |
|------|------|
| 🎙️ Recording Assistant | Lightweight recording + real-time waveform display + AI noise reduction |
| 🔄 Universal Format Converter | High-speed lossless conversion between video/audio formats |
| 🎵 Audio Extractor | Extract high-quality stereo audio tracks from video files |
| ✂️ Lossless Cutter | Quick cutting without re-encoding, zero loss in quality |
| 🔗 Lossless Merger | One-click merge of video and audio tracks, supports mixing |
| 📦 Intelligent Video Compressor | FFmpeg CRF encoding, compresses file size with no perceptual visual loss |
| 🤫 Auto Silence Cut | AI detects silent segments and clips out pauses automatically |

---

## 💻 System Requirements

| Item | Recommended Spec |
|------|---------|
| Operating System | Windows 10/11 (64-bit) |
| Graphics Card | **NVIDIA RTX Series** (Highly Recommended) |
| RAM | 8GB or more |
| Disk Space | Full Version: ~38GB / Medium Version: ~25GB |

> ⚠️ Currently only Windows is officially supported. You can run it without an NVIDIA GPU (it automatically falls back to CPU mode), but the performance will be slower.

---

## 📦 Version Differences

| Item | Full Version (~38GB) | Medium Version (~25GB) |
|------|---------------|---------------|
| Voice Cloning (GPT-SoVITS) | ✅ | ❌ |
| All Other Features | ✅ | ✅ |
| Upgrade Path | Simply replace `Studio0808.exe` | Simply replace `Studio0808.exe` |

---

## 📥 Download

- **Full Version** (Includes Voice Cloning): [Google Drive Download](https://drive.google.com/file/d/15ZfQhFUGVTCoKxLwNDMinNuGALd3HiYC/view?usp=sharing)
- **Full Version Backup Link**: [Google Drive Backup](https://drive.google.com/file/d/11MaSf_Gz0MjQ0X8js2NCxmmgkgb9JyOW/view?usp=sharing)
- **Medium Version** (No Voice Cloning): [Google Drive Download](https://drive.google.com/file/d/1WQ4ha5JsA9Tjs8Z6oN7BpP26cZFimnOv/view?usp=sharing)

After downloading, extract the ZIP file and run `Studio0808.exe` directly. **No installation required**.

---

## 📖 Online Documentation

Complete feature explanation and usage guide: [https://begin0808.github.io/studio0808_video/](https://begin0808.github.io/studio0808_video/)

Bilingual version (Traditional Chinese & English) is available.

---

## ⚙️ Core Technologies

| Technology | Purpose |
|------|------|
| PyTorch v2.6.0+cu124 | Core AI computation engine (RTX 50 series ready) |
| FFmpeg | Video/audio encoding, decoding, merging, and cutting |
| Demucs (htdemucs) | Meta vocal separation model |
| faster-whisper | AI speech-to-text transcription and subtitle generation |
| Pyannote | Speaker diarization |
| GPT-SoVITS | Voice cloning and text-to-speech synthesis |
| RVC | Retrieval-based Voice Conversion (voice changing) |
| Edge-TTS | Microsoft cloud-based speech synthesis |
| yt-dlp | Video and audio streaming downloader |
| Torchcrepe | High-precision pitch estimation |
| CustomTkinter | Modern GUI framework |

---

## 🛠️ Developer & Open Source Guide

This GitHub repository contains the complete Python source code. To keep the repository lightweight, **large model weights and external binary tools are not included** (excluded in `.gitignore`).

### 💻 Windows Development Environment
If you want to run from source or package the program on Windows, please follow these steps to download the necessary binaries:

1. Download the latest **Full Version ZIP** from the download section above and extract it.
2. Copy the following items from the extracted folder directly into your cloned repository folder:
   - `models/` (contains all AI model weights)
   - `tools/` (contains executables like ffmpeg, yt-dlp, etc.)
   - `modules/hubert_base.pt` and `modules/rmvpe.pt` (RVC core models)
   - `GPT-SoVITS/` (the complete GPT-SoVITS environment)
3. Copy `modules/configs/config.json.example` and rename it to `config.json`.
4. Install dependencies: `pip install -r requirements.txt`
5. Run the main application: `python Studio0808_Video.py`

### 🍎 macOS Development Environment & Packaging
If you are a macOS user with Python development experience, this project supports porting, running, and packaging on macOS. Please refer to the standalone guide for detailed environment configuration and instructions:
👉 **[macOS Development, Testing & Packaging Guide (README_macOS.md)](README_macOS.md)**

---

## 💬 Community & Support

- **Discord**: [Join the Community](https://discord.gg/F7mC37MBtF)
- For questions, bug reports, or feature requests, feel free to start a conversation in our Discord!

---

## ☕ Support the Project

Studio0808 is a **completely free** suite with no trials, no feature limitations, and no ads.

If you find it helpful, feel free to buy the developer a coffee:

- **LINE ID**: `begin0808` (Jia-En Li)
- Supports LINE Pay and TWQR transfers

---

## ⚠️ Disclaimer

- This software is for personal learning, research, and academic exchange only.
- Commercial copyright infringement, voice cloning for fraud, or spreading misinformation is strictly prohibited.
- Users assume full legal responsibility for their own actions.

---

## 📄 License

The documentation website (`docs`) is hosted via GitHub Pages.
The software application itself is released independently as a free desktop application.

---

<p align="center">
  <strong>© 2026 Studio0808 Team. All rights reserved.</strong><br>
  Made with ❤️ in Taiwan
</p>

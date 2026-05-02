import requests
import os
import json

# Global Constants (Corrected to project structure)
GPT_MODEL_PATH = r"GPT-SoVITS\GPT_SoVITS\pretrained_models\s1bert25hz-2kh-longer-epoch=68e-step=50232.ckpt"
SOVITS_MODEL_PATH = r"GPT-SoVITS\GPT_SoVITS\pretrained_models\s2G488k.pth"

class GPTSovitsClient:
    def __init__(self, api_url="http://127.0.0.1:9880", logger=None):
        self.api_url = api_url.strip().rstrip("/")
        self.logger = logger
        # Debug
        print(f"GPT-SoVITS Client Init: {self.api_url}")
        
    def log(self, msg):
        if self.logger:
            self.logger.log(msg)
        else:
            print(f"[GPT-Client] {msg}")

    def init_models(self, gpt_path=None, sovits_path=None):
        """Forces the API to load the correct V2ProPlus/V3 models."""
        gpt_path = gpt_path or GPT_MODEL_PATH
        sovits_path = sovits_path or SOVITS_MODEL_PATH
        
        import sys # Ensure sys is available inside method if used there, or better, already imported at top
        
        # If paths are relative, make them absolute based on project root
        if not os.path.isabs(gpt_path) or not os.path.isabs(sovits_path):
            if getattr(sys, 'frozen', False):
                # If packaged by PyInstaller, sys.executable is the EXE location (dist/Studio0808)
                script_dir = os.path.dirname(sys.executable)
            else:
                # If running from source, assume project root is parent of modules/
                script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
            if not os.path.isabs(gpt_path):
                gpt_path = os.path.join(script_dir, gpt_path)
            if not os.path.isabs(sovits_path):
                sovits_path = os.path.join(script_dir, sovits_path)

        try:
            self.log("🔄 正在初始化 / 載入 GPT-SoVITS 模型...")
            
            # Use consolidated /set_model endpoint
            url = f"{self.api_url}/set_model"
            payload = {
                "gpt_model_path": gpt_path,
                "sovits_model_path": sovits_path
            }
            resp = requests.post(url, json=payload, timeout=20)
            
            if resp.status_code == 200:
                self.log(f"✅ 模型切換完成！")
                return True
            else:
                try:
                    err_msg = resp.json().get("message", "Unknown error")
                except:
                    err_msg = resp.text[:200]
                self.log(f"⚠️ 模型切換回傳異常: {resp.status_code} - {err_msg}")
                return False
        except Exception as e:
            print(f"⚠️ 模型載入失敗: {e}")
            return False

    def check_connection(self):
        try:
            print(f"Checking connection to: {self.api_url} ...")
            # Minimal check using GET /
            resp = requests.get(self.api_url, timeout=5)
            # 400 is fine if it means the endpoint exists but needs params
            return resp.status_code in [200, 400] 
        except Exception as e:
            print(f"API Check Failed: {e}")
            return False

    def infer(self, ref_audio_path, ref_text, ref_lang, target_text, target_lang, output_path, speed=1.0, top_p=1.0, temperature=1.0):
        # Better Mapping for GPT-SoVITS V2/V2ProPlus
        # "all_zh" is much more stable than "zh" for pure Chinese input.
        mapping = {
            "zh": "all_zh",
            "en": "en",
            "ja": "all_ja",
            "zh-TW": "all_zh", "zh-CN": "all_zh",
            "en-US": "en", "ja-JP": "all_ja"
        }
        
        t_lang = mapping.get(target_lang, "all_zh")
        p_lang = mapping.get(ref_lang, "all_zh")
        
        # Build Payload matching api.py handle() arguments
        payload = {
            "refer_wav_path": ref_audio_path,
            "prompt_text": ref_text,
            "prompt_language": p_lang,
            "text": target_text,
            "text_language": t_lang,
            "speed": speed,
            "top_p": top_p, 
            "temperature": temperature,
            "top_k": 20, # Increased for better variety
            "cut_punc": "，。？！.,!?;:…", # Enable auto-splitting to prevent EOS/hallucination on long text
            "inp_refs": [],
            "sample_steps": 32,
            "if_sr": False
        }
        
        url = self.api_url + "/"
        try:
            self.log(f"⏳ 正在生成音訊 (文字長度: {len(target_text)})...")
            # Increase timeout for complex generation
            resp = requests.post(url, json=payload, timeout=600)
            
            if resp.status_code == 200:
                c_type = resp.headers.get("Content-Type", "")
                if resp.content.startswith(b"RIFF") or "audio/" in c_type:
                    with open(output_path, "wb") as f:
                        f.write(resp.content)
                    return True, "OK"
                else:
                    return False, "API returned non-audio content"
            else:
                try:
                    err = resp.json().get("message", "Unknown error")
                except:
                    err = resp.text[:200]
                return False, f"API Error {resp.status_code}: {err}"

        except Exception as e:
            return False, f"Connection Error: {str(e)}"

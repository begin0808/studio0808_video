import os
import shutil
import subprocess
import sys

def install_rvc_core():
    # Target directory: modules/
    target_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Define source (Official RVC v2)
    repo_url = "https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git"
    temp_dir = os.path.join(target_dir, "temp_rvc_clone")
    
    print(f"🚀 開始下載 RVC 核心檔案...")
    print(f"來源: {repo_url}")
    
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
        
    try:
        # Clone repo
        subprocess.run(["git", "clone", "--depth", "1", repo_url, temp_dir], check=True)
        
        # Copy required files (RVC V2 Structure)
        
        # 1. configs folder
        configs_target = os.path.join(target_dir, "configs")
        if not os.path.exists(configs_target):
            src = os.path.join(temp_dir, "configs")
            if os.path.exists(src):
                shutil.copytree(src, configs_target)
                print(f"✅ 已安裝 configs/ 資料夾")
        
        # 2. infer folder (contains lib, modules, etc.)
        infer_target = os.path.join(target_dir, "infer")
        if not os.path.exists(infer_target):
            src = os.path.join(temp_dir, "infer")
            if os.path.exists(src):
                shutil.copytree(src, infer_target)
                print(f"✅ 已安裝 infer/ 資料夾")

        # 3. Download hubert_base.pt (New request)
        hubert_url = "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/hubert_base.pt"
        hubert_path = os.path.join(target_dir, "hubert_base.pt")
        
        if not os.path.exists(hubert_path):
            print(f"⬇️ 正在下載 Hubert 模型 (這可能需要一點時間)...")
            try:
                import urllib.request
                # Add User-Agent to avoid 403 Forbidden from HuggingFace
                req = urllib.request.Request(hubert_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as response, open(hubert_path, 'wb') as out_file:
                    shutil.copyfileobj(response, out_file)
                print(f"✅ 已下載 hubert_base.pt")
            except Exception as e:
                print(f"⚠️ 下載 Hubert 失敗: {e}\n請手動下載: {hubert_url}")
        else:
            print(f"ℹ️ hubert_base.pt 已存在，跳過。")
            
        # 4. Download rmvpe.pt (Optional but recommended)
        rmvpe_url = "https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/main/rmvpe.pt"
        rmvpe_path = os.path.join(target_dir, "rmvpe.pt")
        if not os.path.exists(rmvpe_path):
             print(f"⬇️ 正在下載 RMVPE 模型...")
             try:
                import urllib.request
                req = urllib.request.Request(rmvpe_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as response, open(rmvpe_path, 'wb') as out_file:
                    shutil.copyfileobj(response, out_file)
                print(f"✅ 已下載 rmvpe.pt")
             except: pass

        print("🎉 RVC 核心檔案 (含 Hubert/RMVPE) 安裝完成！")
        
    except Exception as e:
        print(f"❌ 安裝失敗: {e}")
        print("請確認您已安裝 git (https://git-scm.com/)")
    finally:
        # Cleanup
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except:
                print(f"⚠️ 無法刪除暫存檔: {temp_dir} (可能被佔用)")

if __name__ == "__main__":
    install_rvc_core()

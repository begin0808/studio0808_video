"""
GPU 安全偵測工具
用於驗證 CUDA 是否真的能正常運作，而非只靠 torch.cuda.is_available()。
解決：有 NVIDIA 顯卡但沒裝 CUDA、AMD 顯卡、內建顯卡等情況下程式當掉的問題。
"""


def safe_check_cuda():
    """
    安全檢查 CUDA 是否真正可用。
    不只檢查 torch.cuda.is_available()，還會實際跑一個小型 CUDA 運算驗證。

    Returns:
        tuple: (is_available: bool, info: str)
            - (True, gpu_name)  如果 CUDA 可正常使用
            - (False, reason)   如果不行，附帶原因說明
    """
    try:
        import torch
    except ImportError:
        return False, "PyTorch 未安裝"

    if not torch.cuda.is_available():
        return False, "CUDA 未安裝或 PyTorch 無 CUDA 支援"

    try:
        # 實際在 GPU 上跑一個小型運算，驗證 CUDA runtime 是否正常
        test_tensor = torch.zeros(1, device="cuda")
        result = test_tensor + 1  # 觸發實際的 CUDA kernel
        del result, test_tensor
        torch.cuda.empty_cache()

        gpu_name = torch.cuda.get_device_name(0)
        return True, gpu_name

    except RuntimeError as e:
        err_str = str(e).lower()
        if "no kernel image" in err_str:
            reason = "顯卡架構不相容 (GPU 太新或 CUDA 版本不匹配)"
        elif "insufficient" in err_str or "driver" in err_str:
            reason = "CUDA 驅動程式版本不足"
        elif "out of memory" in err_str:
            reason = "GPU 記憶體不足"
        elif "not compiled" in err_str or "no cuda" in err_str:
            reason = "PyTorch 未帶 CUDA 支援編譯"
        else:
            reason = f"CUDA 初始化失敗: {e}"
        return False, reason

    except Exception as e:
        return False, f"GPU 偵測異常: {e}"


def safe_cuda_empty_cache():
    """
    安全地清空 CUDA 快取。即使在沒有 CUDA 的環境也不會出錯。
    """
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

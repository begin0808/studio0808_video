import sys

# [Patch 1] omegaconf get_ref_type
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
except Exception:
    pass

# [Patch 2] torchaudio backend & soundfile fallback
try:
    import torchaudio
    if not hasattr(torchaudio, 'set_audio_backend'):
        torchaudio.set_audio_backend = lambda backend=None: None
    if not hasattr(torchaudio, 'get_audio_backend'):
        torchaudio.get_audio_backend = lambda: None
    if not hasattr(torchaudio, 'list_audio_backends'):
        torchaudio.list_audio_backends = lambda: []

    import importlib
    if importlib.util.find_spec('torchaudio.backend') is None:
        import types

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

    try:
        from torchcodec.decoders import AudioDecoder
    except ImportError:
        import torch
        import soundfile as sf
        import numpy as np

        def _soundfile_load(uri, frame_offset=0, num_frames=-1, normalize=True,
                            channels_first=True, format=None, buffer_size=4096, backend=None):
            data, sample_rate = sf.read(uri, start=frame_offset,
                                        stop=(frame_offset + num_frames) if num_frames > 0 else None,
                                        dtype='float32', always_2d=True)
            tensor = torch.from_numpy(data).float()
            if channels_first:
                tensor = tensor.t()
            return tensor, sample_rate

        def _soundfile_save(uri, src, sample_rate, channels_first=True, format=None,
                            encoding=None, bits_per_sample=None, buffer_size=4096,
                            backend=None, compression=None):
            if isinstance(src, torch.Tensor):
                if src.ndim == 1:
                    src = src.unsqueeze(0)
                if channels_first:
                    src = src.t()
                src = src.cpu().numpy()
            sf.write(uri, src, sample_rate)

        def _soundfile_info(uri, format=None, backend=None):
            info = sf.info(uri)
            meta = _AudioMetaData(
                sample_rate=info.samplerate,
                num_frames=info.frames,
                num_channels=info.channels,
                bits_per_sample=info.subtype_info.split()[-1] if hasattr(info, 'subtype_info') else 16,
                encoding=info.subtype if hasattr(info, 'subtype') else None
            )
            try:
                meta.bits_per_sample = int(meta.bits_per_sample)
            except:
                meta.bits_per_sample = 16
            return meta

        torchaudio.load = _soundfile_load
        torchaudio.save = _soundfile_save
        if not hasattr(torchaudio, 'info'):
            torchaudio.info = _soundfile_info
except Exception:
    pass

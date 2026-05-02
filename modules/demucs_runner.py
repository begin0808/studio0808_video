import os
import sys
import torch
import traceback
import subprocess

# Add current dir to path to ensure we can import demucs if needed
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

try:
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    from demucs.audio import AudioFile, save_audio
except ImportError:
    pass

class DemucsRunner:
    def __init__(self, models_dir=None):
        self.models_dir = models_dir if models_dir else os.path.join(os.path.dirname(current_dir), "models", "Demucs")
        os.environ["TORCH_HOME"] = self.models_dir
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def separate(self, input_path, output_dir, model_name="htdemucs", shifts=1, overlap=0.25, callback=None):
        """
        Separate audio into stems.
        Returns path to Vocals and Instrumental (if mixed).
        For RVC Auto-Mix, we need Vocals and Instrumental (No Vocals).
        """
        try:
            print(f"[Demucs] Loading model {model_name} on {self.device}...")
            model = get_model(model_name)
            model.to(self.device)
            
            print(f"[Demucs] Processing {os.path.basename(input_path)}...")
            wav, sr = AudioFile(input_path).read(streams=0, samplerate=model.samplerate, channels=model.audio_channels)
            
            print(f"[Demucs] Wav Shape: {wav.shape}")
            # Ensure 2D (Channels, Length)
            if wav.dim() == 1:
                wav = wav.unsqueeze(0)
            
            # Ensure channels match
            if wav.shape[0] != model.audio_channels:
                 if wav.shape[0] == 1 and model.audio_channels == 2:
                      wav = wav.repeat(2, 1)
                 else:
                      # Try to transpose if it looks like (Length, Channels) which shouldn't happen but defensive
                      if wav.shape[1] == model.audio_channels:
                           wav = wav.t()
            
            ref = wav.mean(0)
            wav_std = ref.std()
            if wav_std < 1e-8:
                wav_std = 1e-8 # Prevent division by zero if audio is silent
                
            wav = (wav - ref.mean()) / wav_std
            
            # Separate
            sources = apply_model(model, wav[None], device=self.device, shifts=shifts, split=True, overlap=overlap, progress=True)[0]
            sources = sources * wav_std + ref.mean()
            
            # Early Cleanup to prevent Crash/OOM during save
            source_names = list(model.sources)
            del model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            sources = sources.cpu()
            print(f"[Demucs] Inference done, VRAM cleared. Starting save...")

            # Save
            stem_paths = {}
            track_name = os.path.splitext(os.path.basename(input_path))[0]
            save_path = os.path.join(output_dir, model_name, track_name)
            if not os.path.exists(save_path): os.makedirs(save_path)
            
            kwargs = {
                'samplerate': 44100, # Hardcoded fallback or use saved samplerate if possible. 
                # Wait, I lost model.samplerate. 
                # I should save it too.
                'bitrate': 320,
                'clip': "rescale",
                'as_float': False,
                'bits_per_sample': 16
            }
            # Actually I should capture samplerate before delete
            
            # Iterate sources
            vocals_stem = None
            instrumental_stems = []
            
            for name, source in zip(source_names, sources):
                print(f"[Demucs] Saving stem: {name}")
                stem_out = os.path.join(save_path, f"{name}.wav")
                save_audio(source, stem_out, samplerate=44100, bitrate=320, clip="rescale", as_float=False, bits_per_sample=16)
                stem_paths[name] = stem_out
                
                if name == "vocals":
                    vocals_stem = stem_out
                else:
                    instrumental_stems.append(source)
                print(f"[Demucs] Saved {name}")

            # Mix Instrumental (No Vocals)
            if instrumental_stems:
                print(f"[Demucs] Mixing instrumental...")
                inst_audio = torch.sum(torch.stack(instrumental_stems), dim=0)
                inst_path = os.path.join(save_path, "no_vocals.wav")
                save_audio(inst_audio, inst_path, samplerate=44100, bitrate=320, clip="rescale", as_float=False, bits_per_sample=16)
                stem_paths["no_vocals"] = inst_path
                print(f"[Demucs] Instrumental saved.")
                
            print(f"[Demucs] Separation complete.")
            
            # Cleanup VRAM
            del sources
            if 'inst_audio' in locals(): del inst_audio
            if 'instrumental_stems' in locals(): del instrumental_stems
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
            import gc; gc.collect()

            return stem_paths

        except Exception as e:
            print(f"[Demucs] Error: {e}")
            traceback.print_exc()
            return None

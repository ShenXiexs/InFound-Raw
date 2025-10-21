import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
from faster_whisper import WhisperModel

# model = WhisperModel("small", device="cpu", compute_type="int8", num_workers=2, download_root=r"C:\TK\part2\models")

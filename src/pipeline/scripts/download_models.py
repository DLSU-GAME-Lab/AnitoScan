import sys
from pathlib import Path

from huggingface_hub import hf_hub_download

# DIRECTORY RESOLUTION
MODELS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_LIST = [
    {
        "repo": "facebook/sam3.1",
        "filename": "sam3.1_multiplex.pt",
        "subfolder": "segmentation",
    },
    {
        "repo": "naver/mast3r",
        "filename": "model.safetensors",
        "subfolder": "reconstruction",
    },
]


def download_all():
    print("[*] Checking model weights...")
    for model in MODEL_LIST:
        dest_path = MODELS_DIR / model["subfolder"] / model["filename"]

        if not dest_path.exists():
            print(
                f"[!] {model['filename']} not found. Downloading from Hugging Face..."
            )
            try:
                downloaded_path = hf_hub_download(
                    repo_id=model["repo"],
                    filename=model["filename"],
                    local_dir=str(MODELS_DIR / model["subfolder"]),
                )
                print(f"[*] Downloaded to {downloaded_path}")
            except Exception as e:
                print(f"[!] Network Error: Could not reach Hugging Face. {e}")
                sys.exit(1)  # Tell C++ engine that download failed
        else:
            print(f"[*] {model['filename']} is already present.")


if __name__ == "__main__":
    download_all()

import os
from pathlib import Path
from remove_background import remove_background  # Import your function
import torch

def process_folder(input_dir, output_dir, model_size="t"):
    # Paths
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # File collection
    valid_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.bmp')
    print(f"Starting batch process in: {input_path}")
    image_files = [f for f in input_path.iterdir() if f.suffix.lower() in valid_extensions]
    if not image_files:
        print("No valid images found in the input folder.")
        return

    # Main loop
    for img_file in image_files:
        target_file = output_path / f"{img_file.stem}_transparent.png"
        
        # Skip if already processed before
        if target_file.exists():
            print(f"Skipping: {img_file.name} (Output already exists)")
            continue
        
        print(f"Processing: {img_file.name}...")
        
        try:
            success = remove_background(
                input_path=str(img_file),
                output_path=str(target_file),
                model_size=model_size
            )
            if success:
                print(f"Done: {target_file.name}")
            else:
                print(f"Skipped: {img_file.name} (No object found)")
        except Exception as e:
            print(f"Error processing {img_file.name}: {e}")

    print("-" * 30)
    print(f"Batch complete! Check your results in: {output_dir}")

if __name__ == "__main__":
    # GPU Verification
    if not torch.cuda.is_available():
        print("Warning: GPU acceleration not supported. Running on CPU.")
    else:
        print(f"GPU acceleration active: {torch.cuda.get_device_name(0)}")

    INPUT_FOLDER = "test"
    OUTPUT_FOLDER = "out/transparent"
    
    process_folder(INPUT_FOLDER, OUTPUT_FOLDER, model_size="s")
import cv2
import numpy as np
from ultralytics import SAM
import os
import torch

def remove_background(input_path, output_path, model_size="s"):
    """
    Removes the background from an image using SAM 2 and saves as a PNG.
    
    Args:
        input_path (str): Path to the source image.
        output_path (str): Path to save the transparent PNG.
        model_size (str): 't', 's', 'b', or 'l' (Tiny, Small, Base, Large).
    """
    model = SAM(f"sam2_{model_size}.pt")

    # Determine device: 'cuda' for NVIDIA GPU, 'mps' for Mac M-series, 'cpu' otherwise
    # Todo : study how to use GPU for mac
    device = 'cuda' if torch.cuda.is_available() else 'cpu'

    # Main
    results = model.predict(source=input_path, conf=0.25, device=device)

    if not results[0].masks:
        print(f"No objects detected in {input_path}")
        return False

    # Convert mask from boolean to float32 or uint8
    mask = results[0].masks.data[0].cpu().numpy().astype(np.float32) 

    # 4. Load Image and Resize Mask
    img = cv2.imread(input_path)
    if img is None:
        raise FileNotFoundError(f"Could not load image at {input_path}")
    h, w = img.shape[:2]
    mask_resized = cv2.resize(mask, (w, h))

    # Create Alpha Channel
    mask_255 = (mask_resized * 255).astype(np.uint8)

    # Create BGRA Image
    bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = cv2.bitwise_not(mask_255)

    # Export
    cv2.imwrite(output_path, bgra)
    return True

# Example Usage
if __name__ == "__main__":
    success = remove_background(
        input_path="portrait.jpg", 
        output_path="portrait_no_bg.png",
        model_size="s"
    )
    if success:
        print("Image saved successfully with transparency.")
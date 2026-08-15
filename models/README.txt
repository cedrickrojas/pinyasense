# AgriPinya Models Directory

Place your trained PyTorch models here.

## Expected Model Format

- **File name**: `pineapple_disease_model.pt` (default)
- **Framework**: PyTorch
- **Input**: 640x640 RGB images
- **Output**: 5 classes
  - Class 0: Heart Rot
  - Class 1: Fruit Rot
  - Class 2: Yellow Spot
  - Class 3: Pink Disease
  - Class 4: Healthy

## Training Your Own Model

If you want to train your own model:

1. Collect pineapple disease images
2. Label them according to the 5 classes above
3. Train using PyTorch with ResNet, EfficientNet, or similar architecture
4. Save the trained model as `.pt` file
5. Place it in this directory
6. Update the model path in `disease_detector.py` if needed

## Fallback

If no model is found, the system will automatically use rule-based detection using color analysis, which still provides reasonable accuracy for most common diseases.

## Pre-trained Models

You can download pre-trained models from:
- (Add link to your model repository)
- (Add link to research paper if applicable)

# YOLOv8 Pineapple Disease Detection - Complete Workflow Guide

## 📋 Overview

This guide walks you through training and deploying a YOLOv8 object detection model for pineapple disease detection in AgriPinya.

**What is YOLOv8?**
- **YOLO** = You Only Look Once (object detection algorithm)
- **v8** = Version 8 (latest from Ultralytics)
- Can detect multiple diseases in one image
- Faster and more accurate than classification models
- Returns bounding boxes around affected regions

---

## 🚀 Quick Start (5 minutes)

### 1. Prerequisites
```bash
# Install dependencies
pip install ultralytics opencv-python pyyaml numpy

# Verify installation
python -c "from ultralytics import YOLO; print('✅ YOLOv8 installed')"
```

### 2. Check Your Dataset
```bash
# Show dataset guide
python scripts/prepare_yolov8_dataset.py

# Validate your data.yaml
python scripts/prepare_yolov8_dataset.py /path/to/data.yaml --validate
```

### 3. Train Model (Pick one)
```bash
# Quick training (30-60 min on GPU)
python scripts/train_yolov8.py /path/to/data.yaml

# High-speed nano model (15-30 min)
python scripts/train_yolov8.py /path/to/data.yaml --model-size n

# Best accuracy (1-3 hours)
python scripts/train_yolov8.py /path/to/data.yaml --model-size l
```

### 4. Test Detection
```bash
# Single image
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt test_image.jpg

# Visualize results
python scripts/test_yolov8_inference.py visualize models/pineapple_yolov8s_latest.pt test_image.jpg --output result.jpg

# Model info
python scripts/test_yolov8_inference.py info models/pineapple_yolov8s_latest.pt
```

---

## 📁 Dataset Structure Required

Your YOLOv8 dataset should follow this structure:

```
dataset_yolov8/
├── data.yaml               # Configuration file
├── train/
│   ├── images/            # Training images (.jpg, .png)
│   └── labels/            # YOLO format labels (.txt)
├── val/
│   ├── images/
│   └── labels/
└── test/
    ├── images/
    └── labels/
```

### data.yaml Format
```yaml
path: /absolute/path/to/dataset_yolov8
train: train/images
val: val/images
test: test/images

nc: 6  # Number of classes
names:
  0: CrownRot
  1: FruitFasciation
  2: FruitRot
  3: MealybugWilt
  4: MultipleCrown
  5: Healthy
```

### YOLO Label Format
Each image must have a corresponding `.txt` file with the same name:
```
# image.jpg → image.txt
class_id x_center y_center width height
class_id x_center y_center width height
...

# Example:
0 0.5 0.5 0.3 0.4    # CrownRot centered at (0.5, 0.5)
2 0.2 0.8 0.15 0.2   # FruitRot
```

Coordinates are **normalized to 0-1** (relative to image dimensions).

---

## 🔧 Detailed Workflow

### Step 1: Prepare Dataset

```bash
# If your dataset is in a different format:
python scripts/prepare_yolov8_dataset.py /path/to/raw/dataset --output dataset_yolov8

# This will:
# ✅ Copy data.yaml
# ✅ Copy train/val/test splits
# ✅ Organize images and labels
# ✅ Validate structure
```

### Step 2: Configure Training

Edit training parameters in `train_yolov8.py` or use command-line arguments:

```bash
python scripts/train_yolov8.py data.yaml \
  --model-size s \           # small model
  --epochs 100 \             # training epochs
  --batch-size 16 \          # images per batch
  --imgsz 640 \              # image resolution
  --device 0 \               # GPU device (0=first GPU, CPU=cpu)
  --patience 20 \            # early stopping patience
  --lr0 0.01 \               # initial learning rate
  --lrf 0.01 \               # final learning rate
  --momentum 0.937 \         # SGD momentum
  --weight-decay 0.0005      # L2 regularization
```

### Step 3: Monitor Training

During training, you'll see:
```
      Epoch  GPU_mem   box_loss   cls_loss   dfl_loss     Instances       Size
    1/100      2.3G      1.234      2.145      0.987            256        640
    2/100      2.3G      1.120      2.034      0.876            256        640
    ...
   100/100      2.3G      0.450      0.234      0.187            256        640

Training complete! Best weights saved: runs/detect/train/weights/best.pt
```

**Metrics to watch:**
- `box_loss`: Bounding box prediction accuracy (↓ better)
- `cls_loss`: Disease classification accuracy (↓ better)
- `dfl_loss`: Distribution focal loss (↓ better)

### Step 4: Model Output

After training, models are saved to:
```
runs/detect/train/
├── weights/
│   ├── best.pt          # Best validation performance
│   └── last.pt          # Last epoch
├── results.csv          # Training metrics
└── confusion_matrix.png # Debug visualization
```

Once you copy the deployable weights to `models/`, move the full old training run into `archive/training/runs/` if you want the main workspace to stay clean.

**Automatic copy to AgriPinya models:**
```bash
cp runs/detect/train/weights/best.pt models/pineapple_yolov8s_best.pt
cp runs/detect/train/weights/best.pt models/pineapple_yolov8s_latest.pt
```

### Step 5: Evaluate Model

```bash
# Get metrics
python scripts/train_yolov8.py data.yaml --mode validate --model-size s

# Expected metrics:
# - mAP50: Mean Average Precision at IoU=0.5 (≥0.7 is good)
# - mAP50-95: More strict metric (≥0.5 is good)
# - Precision: True positives / all detections
# - Recall: True positives / all ground truths
```

### Step 6: Test on Images

```bash
# Single image detection
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt test_image.jpg

# Output:
# ✅ CrownRot: 0.92
# ✅ FruitRot: 0.87

# Visualize with bounding boxes
python scripts/test_yolov8_inference.py visualize models/pineapple_yolov8s_latest.pt test_image.jpg \
  --output visualization.jpg

# Batch testing
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt /path/to/test/images \
  --output results.json
```

### Step 7: Deploy in AgriPinya

The model is automatically detected! Just:

1. **Copy to models directory:**
   ```bash
   cp models/pineapple_yolov8s_best.pt models/pineapple_yolov8n_latest.pt
   ```

2. **Disease detection automatically uses it:**
   - `disease_detector.py` checks for YOLOv8 models
   - If found, uses it as primary detection method
   - Falls back to CNN if needed

3. **Upload image to AgriPinya:**
   - Flask app receives image
   - Automatically uses YOLOv8 for detection
   - Returns disease predictions with confidence

---

## 📊 Model Selection Guide

Choose model based on your needs:

| Model | Speed | Accuracy | Memory | Use Case |
|-------|-------|----------|--------|----------|
| Nano (n) | ⚡⚡⚡ Fast | ⭐⭐ | ~2GB | Mobile/Edge devices |
| Small (s) | ⚡⚡ Fast | ⭐⭐⭐ | ~3GB | **Recommended** |
| Medium (m) | ⚡ Balanced | ⭐⭐⭐⭐ | ~5GB | High accuracy |
| Large (l) | 🐢 Slow | ⭐⭐⭐⭐⭐ | ~8GB | Production |
| XLarge (x) | 🐢🐢 Slow | ⭐⭐⭐⭐⭐ | ~12GB | Maximum accuracy |

**Recommendation:** Start with `small` (s) model for balanced speed/accuracy.

---

## ⚙️ Training Hyperparameters Explained

```python
# Image preprocessor
imgsz=640          # Input image resolution (larger = more detail, slower)
                   # Options: 320, 416, 512, 640, 1024

# Training strategy
epochs=100         # Number of training passes (more = longer training)
batch_size=16      # Images per batch (larger = faster, more memory)
patience=20        # Early stopping (stop if no improvement for N epochs)

# Learning rate
lr0=0.01           # Initial learning rate (larger = faster learning, less stable)
lrf=0.01           # Final learning rate (at last epoch)
                   # Typical: lr0=0.01, lrf=0.01 (constant)

# Regularization
weight_decay=0.0005  # L2 penalty (prevents overfitting)
dropout=0.0        # Random neuron deactivation (0-1)
                   # Higher = more regularization

# Augmentation
hsv_h=0.015        # HSV-Hue augmentation
hsv_s=0.7          # HSV-Saturation augmentation
hsv_v=0.4          # HSV-Value (brightness) augmentation
degrees=10         # Random rotation ±N degrees
translate=0.1      # Random translation (10% of image)
scale=0.5          # Random scale (0.5 = 50%-150%)
flipud=0.5         # Flip up-down probability
fliplr=0.5         # Flip left-right probability
mosaic=1.0         # Mosaic augmentation (combine 4 images)
```

---

## 🐛 Troubleshooting

### Problem: CUDA Out of Memory
```bash
# Reduce batch size
python scripts/train_yolov8.py data.yaml --batch-size 8

# Reduce image size
python scripts/train_yolov8.py data.yaml --imgsz 416

# Use smaller model
python scripts/train_yolov8.py data.yaml --model-size n
```

### Problem: Poor Accuracy
**Cause:** Small dataset or low quality data
```bash
# Add more training epochs
python scripts/train_yolov8.py data.yaml --epochs 200

# Use larger model
python scripts/train_yolov8.py data.yaml --model-size l

# Improve data quality:
# - More images per class
# - Varied lighting, angles, distances
# - Clear disease symptoms
```

### Problem: Overfitting (Low validation accuracy)
**Cause:** Model too large for dataset or poor regularization
```bash
# Use smaller model
python scripts/train_yolov8.py data.yaml --model-size n

# Increase regularization
python scripts/train_yolov8.py data.yaml --weight-decay 0.001

# More aggressive augmentation
python scripts/train_yolov8.py data.yaml --scale 0.8 --translate 0.2
```

### Problem: Model not loading in AgriPinya
```bash
# Check model exists
ls -lh models/pineapple_yolov8*.pt

# Verify model format
python scripts/test_yolov8_inference.py info models/pineapple_yolov8s_latest.pt

# Check disease_detector.py recognizes it
grep -A5 "self.model_type" disease_detector.py
```

---

## 📈 Expected Performance

With good training data (~50-100 images per class):

```
Metrics at 100 epochs:
  mAP50: 0.85-0.95    ← Good object detection
  mAP50-95: 0.65-0.80 ← Strict evaluation
  Precision: 0.90+    ← Low false positives
  Recall: 0.85+       ← Catches most diseases
  
Speed (on GPU):
  Inference: ~10-50ms per image
  Throughput: 20-100 images/second
```

---

## 🔄 Iterative Improvement Workflow

1. **Train baseline model:**
   ```bash
   python scripts/train_yolov8.py data.yaml --model-size s
   ```

2. **Evaluate metrics:**
   - Check mAP50, mAP50-95
   - Review confusion matrix
   - Test on real farm images

3. **Identify weaknesses:**
   - Which diseases have low accuracy?
   - False positive/negative patterns?
   - Which images fail?

4. **Improve data:**
   - Add more images of weak classes
   - Collect diverse examples
   - Improve annotation quality

5. **Retrain:**
   ```bash
   python scripts/train_yolov8.py data.yaml --epochs 150 --model-size m
   ```

6. **Compare models:**
   ```bash
   python scripts/test_yolov8_inference.py compare \
     models/pineapple_yolov8s_v1.pt \
     models/pineapple_yolov8m_v2.pt \
     test_image.jpg
   ```

7. **Deploy winner:**
   ```bash
   cp models/pineapple_yolov8m_v2.pt models/pineapple_yolov8_latest.pt
   ```

---

## 📚 Additional Resources

**Online Documentation:**
- YOLOv8 Official: https://docs.ultralytics.com
- Training Guide: https://docs.ultralytics.com/modes/train/
- Detection Guide: https://docs.ultralytics.com/modes/predict/

**Dataset Preparation:**
- Roboflow: https://roboflow.com (Dataset management)
- Label Studio: https://labelstud.io (Image labeling tool)
- CVAT: https://cvat.ai (Annotation platform)

**YOLOv8 Community:**
- GitHub: https://github.com/ultralytics/ultralytics
- Forum: https://github.com/ultralytics/ultralytics/discussions
- Issues: https://github.com/ultralytics/ultralytics/issues

---

## ✅ Checklist for Production Deployment

- [ ] Dataset has 50+ images per class
- [ ] Train/val/test splits are balanced
- [ ] mAP50 > 0.7, mAP50-95 > 0.5
- [ ] Model tested on diverse farm images
- [ ] Model file copied to `models/` directory
- [ ] Naming follows: `pineapple_yolov8{size}_latest.pt`
- [ ] Firebase integration (optional) configured
- [ ] Sensor data collection validated
- [ ] Flask app tested end-to-end
- [ ] Production metrics logged and monitored

---

## 🎯 Next Steps

1. **Prepare your dataset:** Ensure it's in YOLOv8 format
2. **Train model:** `python scripts/train_yolov8.py data.yaml`
3. **Evaluate:** Test on sample images
4. **Deploy:** Copy model to `models/` directory
5. **Integrate Firebase:** (Optional) Set up cloud database
6. **Monitor production:** Track accuracy and performance

---

**Questions? Check train_yolov8.py or test_yolov8_inference.py for detailed documentation!**

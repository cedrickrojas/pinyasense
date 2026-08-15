# 🍍 YOLOv8 Pineapple Disease Detection - Tools & Setup

Complete YOLOv8 object detection training and deployment infrastructure for AgriPinya.

---

## 📦 What You Get

This package includes everything needed to:
1. ✅ **Prepare** YOLOv8 datasets for training
2. ✅ **Train** custom disease detection models  
3. ✅ **Test** models on real farm images
4. ✅ **Deploy** to AgriPinya for automatic detection
5. ✅ **Monitor** detection performance

---

## 🎯 Quick Start (3 Steps)

### 1️⃣ Check Setup
```bash
python yolov8_quickstart.py --check
```
Verifies all dependencies are installed.

### 2️⃣ Prepare Dataset
```bash
python yolov8_quickstart.py --setup /path/to/pineapple-disease-dataset
```
Organizes your YOLOv8 dataset into proper structure.

### 3️⃣ Train Model
```bash
python yolov8_quickstart.py --train dataset_yolov8/data.yaml --size s --epochs 100
```
Trains a new detection model (60 min on GPU).

**That's it!** Model is automatically ready for AgriPinya.

---

## 📚 Available Tools

### 1. **yolov8_quickstart.py** - Automated Workflow
Fast-track setup script for common tasks.

**Usage:**
```bash
# Check dependencies
python yolov8_quickstart.py --check

# Setup dataset
python yolov8_quickstart.py --setup /path/to/dataset

# Train model
python yolov8_quickstart.py --train data.yaml --size s

# Test on image
python yolov8_quickstart.py --test test_image.jpg --train data.yaml

# Full workflow (all steps)
python yolov8_quickstart.py --full /path/to/dataset
```

**Options:**
```
--check              Check if dependencies are installed
--setup PATH         Setup dataset from path
--train YAML         Train model on data.yaml
--size {n,s,m,l,x}   Model size (nano to xlarge)
--epochs N           Training epochs (default: 100)
--batch-size N       Batch size (default: 16)
--test IMAGE         Test on image after training
--deploy PATH        Deploy model to models/ directory
--full PATH          Complete workflow: setup + train + deploy
```

---

### 2. **prepare_yolov8_dataset.py** - Dataset Preparation
Organize and validate YOLOv8 datasets.

**Usage:**
```bash
# Show help & guide
python scripts/prepare_yolov8_dataset.py

# Setup dataset from raw folder
python scripts/prepare_yolov8_dataset.py /path/to/raw/dataset --output dataset_yolov8

# Validate existing data.yaml
python scripts/prepare_yolov8_dataset.py dataset_yolov8/data.yaml --validate
```

**What it does:**
- ✅ Copies images and labels
- ✅ Validates YAML structure
- ✅ Checks train/val/test splits
- ✅ Counts images per class
- ✅ Verifies label format

**Output:**
```
dataset_yolov8/
├── data.yaml
├── train/images/ (training images)
├── train/labels/ (YOLO format)
├── val/images/
├── val/labels/
└── test/images/
```

---

### 3. **train_yolov8.py** - Full Training Pipeline
Complete model training with advanced options.

**Usage:**
```bash
# Basic (use defaults)
python scripts/train_yolov8.py data.yaml

# Custom configuration
python scripts/train_yolov8.py data.yaml \
  --model-size m \
  --epochs 150 \
  --batch-size 32 \
  --imgsz 640 \
  --device 0 \
  --patience 30
```

**Features:**
- 🚀 Fast training with GPU acceleration
- ⚙️ Customizable hyperparameters
- 📊 Real-time metrics display
- 🛑 Early stopping (prevents overfitting)
- 💾 Multi-format export (PyTorch, ONNX, TFLite)
- 📈 Comprehensive logging

**Output:**
```
runs/detect/train/
├── weights/
│   ├── best.pt      (best model)
│   └── last.pt      (final model)
├── results.csv      (training metrics)
└── confusion_matrix.png  (debug viz)
```

For a cleaner workspace, archive that whole run after copying the best weight into `models/`.

**Model Sizes:**
- `n` - Nano: Fast, 2GB memory (⭐ Fastest)
- `s` - Small: Balanced, 3GB memory (⭐⭐ **Recommended**)
- `m` - Medium: Accurate, 5GB memory (⭐⭐⭐)
- `l` - Large: Very accurate, 8GB memory (⭐⭐⭐⭐)
- `x` - XLarge: Best accuracy, 12GB memory (⭐⭐⭐⭐⭐)

---

### 4. **test_yolov8_inference.py** - Model Testing & Inference
Test trained models and visualize detections.

**Usage:**
```bash
# Single image detection
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt image.jpg

# Visualize with bounding boxes
python scripts/test_yolov8_inference.py visualize models/pineapple_yolov8s_latest.pt image.jpg \
  --output result.jpg

# Batch detection (directory)
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt /path/to/images \
  --output results.json

# Model information
python scripts/test_yolov8_inference.py info models/pineapple_yolov8s_latest.pt

# Confidence threshold
python scripts/test_yolov8_inference.py detect model.pt image.jpg --conf 0.6
```

**Commands:**
- `detect` - Run disease detection on image(s)
- `visualize` - Draw bounding boxes on image
- `info` - Show model configuration

**Output:**
```
✅ CrownRot: 92%
✅ FruitRot: 87%
📊 Summary: 2 regions detected
```

---

### 5. **YOLOV8_WORKFLOW_GUIDE.md** - Complete Documentation
Comprehensive guide with:
- 📋 Dataset format requirements
- 🔧 Parameter explanations
- ⚙️ Hyperparameter tuning
- 🐛 Troubleshooting
- 📈 Performance metrics
- 🔄 Iterative improvement
- ✅ Production checklist

---

## 🔄 Complete Workflow

### Step-by-Step Guide

#### **Phase 1: Preparation** (10 min)
```bash
# 1. Check system is ready
python yolov8_quickstart.py --check

# 2. Prepare dataset
python yolov8_quickstart.py --setup /path/to/Pineapple-Disease.v1i.yolov8
```

#### **Phase 2: Training** (30-120 min depending on GPU)
```bash
# 3. Train model (pick based on your hardware)
# Fast version (GPU: 30-60 min)
python yolov8_quickstart.py --train dataset_yolov8/data.yaml --size n

# Recommended (GPU: 60 min, CPU: 2-3 hours)
python yolov8_quickstart.py --train dataset_yolov8/data.yaml --size s

# High accuracy (GPU: 120 min, CPU: 4-6 hours)  
python yolov8_quickstart.py --train dataset_yolov8/data.yaml --size m
```

**During training, watch for:**
- `box_loss` ↓ going down
- `cls_loss` ↓ going down  
- Validation improving

#### **Phase 3: Evaluation** (5 min)
```bash
# 4. Test on sample images
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt test_image.jpg

# 5. Visualize detections
python scripts/test_yolov8_inference.py visualize models/pineapple_yolov8s_latest.pt test_image.jpg \
  --output result.jpg
```

#### **Phase 4: Deployment** (Automatic! ✅)
Model is already in `models/` directory and ready to use:
- Upload images to AgriPinya web interface
- Automatic detection using YOLOv8
- Results show detected diseases with confidence

---

## 📊 Dataset Requirements

Your YOLOv8 dataset must have this structure:

```
dataset_yolov8/
├── data.yaml                # Configuration file
├── train/
│   ├── images/             # Training images
│   └── labels/             # YOLO format labels
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

nc: 6  # Number of disease classes
names:
  0: CrownRot
  1: FruitFasciation
  2: FruitRot
  3: MealybugWilt
  4: MultipleCrown
  5: Healthy
```

### YOLO Label Format
Each image has a `.txt` file with same name:
```
# image.jpg → image.txt
class_id x_center y_center width height
class_id x_center y_center width height
```

Coordinates are **normalized to 0-1** (relative to image size).

---

## ⚙️ Configuration & Customization

### Training Hyperparameters

```python
# Image settings
--imgsz 640           # Input resolution (320-1024)
--batch-size 16       # Images per batch (8, 16, 32, 64)

# Training duration  
--epochs 100          # Training passes (50-200)
--patience 20         # Early stopping threshold (10-30)

# Learning rate
--lr0 0.01            # Initial learning rate
--lrf 0.01            # Final learning rate

# Regularization
--weight-decay 0.0005 # L2 penalty
--dropout 0.0         # Neural dropout
```

### Model Selection Matrix

| Task | Speed | Accuracy | Memory | Model |
|------|-------|----------|--------|-------|
| **Mobile/Edge** | ⚡⚡⚡ | ⭐⭐ | 2GB | nano (n) |
| **Balanced** | ⚡⚡ | ⭐⭐⭐ | 3GB | **small (s)** ✅ |
| **High Accuracy** | ⚡ | ⭐⭐⭐⭐ | 5GB | medium (m) |
| **Production** | 🐢 | ⭐⭐⭐⭐⭐ | 8GB | large (l) |

---

## 🐛 Troubleshooting

### Installation Issues
```bash
# Install YOLOv8
pip install ultralytics

# Install all dependencies
pip install ultralytics torch torchvision opencv-python pyyaml numpy

# Verify installation
python -c "from ultralytics import YOLO; print('✅ YOLOv8 ready')"
```

### GPU/Memory Issues
```bash
# Reduce batch size
python scripts/train_yolov8.py data.yaml --batch-size 8

# Reduce image resolution
python scripts/train_yolov8.py data.yaml --imgsz 416

# Use smaller model
python scripts/train_yolov8.py data.yaml --model-size n
```

### Poor Accuracy
```bash
# Increase training epochs
python scripts/train_yolov8.py data.yaml --epochs 200

# Use larger model
python scripts/train_yolov8.py data.yaml --model-size l

# Larger batch size
python scripts/train_yolov8.py data.yaml --batch-size 32
```

### Model Not Detected by AgriPinya
```bash
# Check model exists
ls -lh models/pineapple_yolov8*.pt

# Verify YOLOv8 format
python scripts/test_yolov8_inference.py info models/pineapple_yolov8s_latest.pt

# Check disease_detector.py recognizes it
grep "yolov8" disease_detector.py
```

---

## 📈 Performance Expectations

With ~50-100 images per disease class:

```
Training Results (100 epochs):
✅ mAP50:     0.85-0.95  (object detection accuracy)
✅ mAP50-95:  0.65-0.80  (strict evaluation)
✅ Precision: 0.90+      (false positive rate)
✅ Recall:    0.85+      (detection rate)

Inference Performance (on GPU):
⚡ Speed: 10-50ms per image
🚀 Throughput: 20-100 images/second
💾 Model size: 6-200MB
```

---

## 🎯 Integration with AgriPinya

### Auto-Detection Flow
```
1. User uploads image → Flask app
2. disease_detector.py checks for YOLOv8 model
3. If found → Uses YOLOv8 for detection (object detection)
4. If not found → Falls back to CNN classification
5. Returns: Disease name + Confidence + Bounding box
6. Firebase (optional): Stores detection result
7. Web UI: Shows image with detected regions
```

### Model Naming Convention
The system auto-detects YOLOv8 models by name:
- `pineapple_yolov8n_*.pt` - Nano model
- `pineapple_yolov8s_*.pt` - Small model  
- `pineapple_yolov8m_*.pt` - Medium model
- `pineapple_yolov8l_*.pt` - Large model

**Recommended:** Train small model (`s`) for best balance.

---

## 📚 Resources & Documentation

**Complete Guides:**
- 📖 [YOLOV8_WORKFLOW_GUIDE.md](YOLOV8_WORKFLOW_GUIDE.md) - Comprehensive guide
- 🚀 [train_yolov8.py](train_yolov8.py) - Training script with docstrings
- 🧪 [test_yolov8_inference.py](test_yolov8_inference.py) - Testing utilities
- ⚙️ [prepare_yolov8_dataset.py](prepare_yolov8_dataset.py) - Dataset setup

**External Resources:**
- 🌐 [YOLOv8 Official Documentation](https://docs.ultralytics.com)
- 📊 [Roboflow Dataset Platform](https://roboflow.com)
- 🏷️ [Label Studio - Annotation Tool](https://labelstud.io)

---

## ✅ Checklist for Production Deployment

Before going live:

- [ ] Dataset has 50+ images per disease class
- [ ] Train/val/test splits balanced
- [ ] Training converged (metrics stable)
- [ ] mAP50 > 0.7, mAP50-95 > 0.5
- [ ] Tested on diverse farm images
- [ ] Model saved to `models/pineapple_yolov8_latest.pt`
- [ ] Health check: Inference works on test images
- [ ] Integration: Works with AgriPinya web interface
- [ ] Monitoring: Performance tracked over time
- [ ] Backup: Model backed up to safe location

---

## 🎯 Quick Commands

```bash
# One-liner full workflow
python yolov8_quickstart.py --full /path/to/dataset

# Train recommended model
python scripts/train_yolov8.py data.yaml

# Test trained model
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt test_image.jpg

# Show help
python scripts/prepare_yolov8_dataset.py
python scripts/train_yolov8.py --help
python scripts/test_yolov8_inference.py detect --help
```

---

## 📞 Support

**Common Issues:**
1. "Module not found" → Run `pip install ultralytics`
2. "CUDA out of memory" → Reduce batch size or image resolution
3. "Low accuracy" → Add more training data or epochs
4. "Model not detected" → Check name matches pattern in disease_detector.py

**Files to Check:**
- `disease_detector.py` - Detection engine
- `.env` - Configuration
- `models/` - Trained models location
- `requirements.txt` - Dependencies

---

## 🚀 Next Steps

1. **Prepare dataset:** Ensure it's in YOLOv8 format
2. **Check setup:** `python yolov8_quickstart.py --check`
3. **Setup dataset:** `python yolov8_quickstart.py --setup /path/to/dataset`
4. **Train model:** `python yolov8_quickstart.py --train data.yaml`
5. **Test detection:** Use test_yolov8_inference.py
6. **Deploy:** Model automatically ready in models/ directory

---

**Happy farming! 🌾** Your YOLOv8 model will help detect pineapple diseases early and improve crop health!

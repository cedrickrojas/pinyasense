# 🍍 YOLOv8 AgriPinya - Getting Started Guide

Welcome to AgriPinya's YOLOv8 object detection training system!

This guide will get you up and running in **5 minutes**.

---

## 🚀 Quick Start (Choose Your Path)

### ⚡ Path A: Fastest - 3 Commands
```bash
# 1. Check your system (1 min)
python scripts/setup_diagnostics.py

# 2. Prepare your dataset (2 min)
python yolov8_quickstart.py --setup /path/to/pineapple-disease-dataset

# 3. Train your model (30-120 min depending on GPU)
python yolov8_quickstart.py --train data/data.yaml

# That's it! ✅ Model is ready in models/ directory
```

### 🎯 Path B: Full Workflow - 1 Command
```bash
# Everything in one go
python yolov8_quickstart.py --full /path/to/pineapple-disease-dataset

# Done! ✅
```

### 📚 Path C: Learn Everything First
- Read [`YOLOV8_WORKFLOW_GUIDE.md`](YOLOV8_WORKFLOW_GUIDE.md) (30 min)
- Then follow manual commands

---

## 📋 What Do I Need?

### Must Have ✅
- [ ] Python 3.8 or higher
- [ ] Your YOLOv8 pineapple disease dataset (Pineapple-Disease.v1i.yolov8 format)
- [ ] GPU recommended (training 5-10x faster) or CPU (works, slower)

### Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Test installation
python scripts/setup_diagnostics.py
```

---

## 🎯 Step-by-Step Training

### Step 1: Verify System (2 minutes)
```bash
python scripts/setup_diagnostics.py
```

**What it checks:**
- ✅ Python version (need 3.8+)
- ✅ GPU/CUDA availability
- ✅ All required packages
- ✅ Directory structure
- ✅ YOLOv8 tools installed

**Output:** Green ✅ = All good, Red ❌ = Fix issues

---

### Step 2: Prepare Dataset (5 minutes)
```bash
python yolov8_quickstart.py --setup /path/to/Pineapple-Disease.v1i.yolov8
```

**What it does:**
- ✅ Copies your dataset to `dataset_yolov8/` folder
- ✅ Organizes train/val/test splits
- ✅ Validates structure
- ✅ Counts images per disease class

**Output:**
```
✅ Copied data.yaml
✅ Copied train/images
✅ Copied train/labels
✅ Copied val/images
✅ Copied val/labels
✅ Dataset setup complete!
```

---

### Step 3: Train Your Model (30-120 minutes)
```bash
# Basic training (recommended)
python yolov8_quickstart.py --train dataset_yolov8/data.yaml

# Or customize
python yolov8_quickstart.py --train dataset_yolov8/data.yaml \
  --size s \        # small model (good balance)
  --epochs 100 \    # training passes
  --batch-size 16   # images per step
```

**During training, watch for:**
- box_loss ↓ (getting better)
- cls_loss ↓ (getting better)
- No GPU memory errors
- Validation improving

**Expected time:**
- GPU: 30-120 minutes (depending on model size + GPU)
- CPU: 2-6 hours

**Output:**
```
Training complete!
Best model: runs/detect/train/weights/best.pt
Metrics: mAP50=0.85, mAP50-95=0.72
```

After deployment, move older run folders into `archive/training/` so the main workspace stays clean.

---

### Step 4: Test Your Model (5 minutes)
```bash
# Test on single image
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt test_image.jpg

# Visualize results
python scripts/test_yolov8_inference.py visualize models/pineapple_yolov8s_latest.pt test_image.jpg \
  --output result_with_boxes.jpg

# Test on folder of images  
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt /path/to/test/images
```

**Expected output:**
```
✅ CrownRot: 92%
✅ FruitRot: 87%
📊 Summary: 2 regions detected
```

---

### Step 5: Deploy to AgriPinya (1 minute)
```bash
# Model is already in the right place! ✅
ls -lh models/pineapple_yolov8s_latest.pt

# Start AgriPinya
python app.py

# Open browser
open http://localhost:5000
```

Upload images → Automatic detection with YOLOv8 ✅

---

## 🎓 Learning Resources

### For Quick Commands
📕 **[YOLOV8_QUICK_REFERENCE.md](YOLOV8_QUICK_REFERENCE.md)**
- One-page cheat sheet
- Common operations
- Quick fixes
- Print-friendly

### For Complete Understanding  
📘 **[YOLOV8_WORKFLOW_GUIDE.md](YOLOV8_WORKFLOW_GUIDE.md)**
- Dataset format requirements
- All training options
- Hyperparameter tuning
- Troubleshooting guide
- Performance metrics

### For Tools Reference
📗 **[YOLOV8_TOOLS_README.md](YOLOV8_TOOLS_README.md)**
- All 5 tools explained
- Usage examples
- Platform integration
- Configuration options

### Technical Details
📙 **[YOLOV8_IMPLEMENTATION_COMPLETE.md](YOLOV8_IMPLEMENTATION_COMPLETE.md)**
- Architecture details
- Integration flow
- File organization
- Success metrics

---

## 🎯 Available Tools

### 1. **yolov8_quickstart.py** ⭐ (USE THIS FIRST!)
Automated tool for common tasks
```bash
python yolov8_quickstart.py --check              # Dependencies
python yolov8_quickstart.py --setup /path        # Dataset setup
python yolov8_quickstart.py --train data.yaml    # Train model
python yolov8_quickstart.py --full /path         # Everything
```

### 2. **train_yolov8.py**
Full training control with advanced options
```bash
python scripts/train_yolov8.py data.yaml --model-size m --epochs 150
```

### 3. **test_yolov8_inference.py**
Testing and inference utilities
```bash
python scripts/test_yolov8_inference.py detect model.pt image.jpg
python scripts/test_yolov8_inference.py visualize model.pt image.jpg --output out.jpg
```

### 4. **prepare_yolov8_dataset.py**
Dataset preparation and validation
```bash
python scripts/prepare_yolov8_dataset.py /path/to/dataset --output dataset_yolov8
```

### 5. **setup_diagnostics.py**
System health check
```bash
python scripts/setup_diagnostics.py
```

---

## 🎨 Choosing Model Size

| Size | Speed | Memory | Best For |
|------|-------|--------|----------|
| **nano (n)** | ⚡⚡⚡ fastest | 2GB | Testing |
| **small (s)** | ⚡⚡ fast | 3GB | **👈 START HERE** |
| **medium (m)** | ⚡ balanced | 5GB | Production |
| **large (l)** | 🐢 slow | 8GB | Max accuracy |

**Recommendation:** Use `small (s)` for best balance.

---

## ⚠️ Common Issues

### "ModuleNotFoundError: ultralytics"
```bash
pip install ultralytics
```

### "CUDA out of memory"
```bash
python yolov8_quickstart.py --train data.yaml --batch-size 8
```

### "data.yaml not found"
```bash
python yolov8_quickstart.py --setup /path/to/dataset
```

### "Poor detection accuracy"
```bash
# Train longer
python yolov8_quickstart.py --train data.yaml --epochs 200

# Use larger model
python yolov8_quickstart.py --train data.yaml --size m
```

→ See [YOLOV8_WORKFLOW_GUIDE.md](YOLOV8_WORKFLOW_GUIDE.md#-troubleshooting) for more

---

## 📊 Expected Results

After training on good dataset:

```
Model Size: small (s)
Training Time: 60 minutes (GPU)
Results:
  ✅ mAP50: 0.85-0.95        (object detection)
  ✅ mAP50-95: 0.65-0.80     (strict metric)
  ✅ Precision: 0.90+        (low false positives)
  ✅ Recall: 0.85+           (detects most diseases)
  
Inference Speed:
  🚀 30ms per image on GPU
  ⏱️ 500ms per image on CPU
```

---

## 🔄 Complete Workflow Diagram

```
Start
  ↓
python scripts/setup_diagnostics.py
  ├─ Check dependencies ✅
  ├─ Check GPU ✅
  └─ Show next steps
  ↓
python yolov8_quickstart.py --setup /path/to/dataset
  ├─ Copy images
  ├─ Copy labels  
  └─ Validate structure
  ↓
python yolov8_quickstart.py --train data.yaml
  ├─ Load dataset (30s)
  ├─ Download model (1m)
  ├─ Train loop (60-120m) [watch this!]
  ├─ Save best model
  └─ Generate metrics
  ↓
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt test.jpg
  ├─ Load model
  ├─ Run inference
  └─ Show results ✅
  ↓
python app.py
  ├─ Start Flask server
  ├─ Model loads automatically
  └─ Ready for production ✅
  ↓
Done! 🎉
```

---

## 🚀 Next Steps

Pick your path:

### Path 1: Get Started Now (Recommended ⭐)
```bash
# 1. Check system
python scripts/setup_diagnostics.py

# 2. Setup & train
python yolov8_quickstart.py --full /path/to/dataset
```

### Path 2: Learn First
1. Read [`YOLOV8_WORKFLOW_GUIDE.md`](YOLOV8_WORKFLOW_GUIDE.md)
2. Run training scripts manually
3. Explore options and parameters

### Path 3: Manual Control
```bash
# Dataset
python scripts/prepare_yolov8_dataset.py /path/to/dataset

# Training with full options
python scripts/train_yolov8.py data.yaml \
  --model-size m \
  --epochs 150 \
  --batch-size 32 \
  --imgsz 640
```

---

## 💡 Pro Tips

1. **Start small**: Use nano (n) model to test pipeline
2. **Monitor GPU**: Run `nvidia-smi` in another terminal
3. **Save checkpoints**: Models save every epoch automatically
4. **Keep backups**: Copy best.pt after training
5. **Test incrementally**: Train, test, improve
6. **Read logs**: Watch for overfitting (val_loss > train_loss)

---

## 📞 Getting Help

**Check these resources:**
1. [`YOLOV8_QUICK_REFERENCE.md`](YOLOV8_QUICK_REFERENCE.md) - Quick commands
2. [`YOLOV8_WORKFLOW_GUIDE.md`](YOLOV8_WORKFLOW_GUIDE.md) - Deep dive
3. Run `python scripts/setup_diagnostics.py` - System check
4. Error message → Search in WORKFLOW_GUIDE.md

---

## ✅ Checklist

Before training:
- [ ] Python 3.8+ installed
- [ ] Dataset in YOLOv8 format
- [ ] `pip install -r requirements.txt` completed
- [ ] `python scripts/setup_diagnostics.py` shows all green ✅
- [ ] GPU available (optional but recommended)

After training:
- [ ] Model saved: `models/pineapple_yolov8s_latest.pt`
- [ ] Test works: `python scripts/test_yolov8_inference.py detect ...`
- [ ] AgriPinya runs: `python app.py`
- [ ] Detection works in web interface

---

## 🎉 You're Ready!

Start with:
```bash
python scripts/setup_diagnostics.py
```

Or jump right in:
```bash
python yolov8_quickstart.py --full /path/to/dataset
```

**Questions?** See the documentation files or check the code comments.

---

**Happy farming with YOLOv8 disease detection! 🌾🍍**

Next file to read: [`YOLOV8_WORKFLOW_GUIDE.md`](YOLOV8_WORKFLOW_GUIDE.md)

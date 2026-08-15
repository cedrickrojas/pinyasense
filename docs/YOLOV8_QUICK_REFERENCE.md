# 🍍 YOLOv8 AgriPinya - Quick Reference Cheat Sheet

## ⚡ One-Minute Quickstart
```bash
# 1. Check everything is installed
python yolov8_quickstart.py --check

# 2. Prepare dataset
python yolov8_quickstart.py --setup /path/to/dataset

# 3. Train model (pick one)
# Fast (20-30 min)
python yolov8_quickstart.py --train data.yaml --size n
# Recommended (60 min) ⭐
python yolov8_quickstart.py --train data.yaml --size s
# Best quality (120 min)
python yolov8_quickstart.py --train data.yaml --size m

# 4. Done! Use in AgriPinya ✅
```

---

## 🎯 Common Tasks

### Prepare Dataset
```bash
python yolov8_quickstart.py --setup /path/to/Pineapple-Disease.v1i.yolov8
python scripts/prepare_yolov8_dataset.py /path/to/dataset --output dataset_yolov8
```

### Train Model
```bash
# Automatic (recommended)
python yolov8_quickstart.py --train data.yaml

# Manual (full control)
python scripts/train_yolov8.py data.yaml \
  --model-size s \
  --epochs 100 \
  --batch-size 16 \
  --imgsz 640
```

### Test Detection (Single Image)
```bash
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt image.jpg
```

### Visualize Results
```bash
python scripts/test_yolov8_inference.py visualize models/pineapple_yolov8s_latest.pt image.jpg \
  --output result.jpg
```

### Batch Testing (Multiple Images)
```bash
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt /path/to/images \
  --output results.json
```

### Model Information
```bash
python scripts/test_yolov8_inference.py info models/pineapple_yolov8s_latest.pt
```

---

## 📊 Model Sizes

| Size | Speed | Accuracy | Memory | When to Use |
|------|-------|----------|--------|---|
| **n** (nano) | ⚡⚡⚡ Fastest | ⭐⭐ | 2GB | Testing, mobile |
| **s** (small) | ⚡⚡ Fast | ⭐⭐⭐ | 3GB | **RECOMMENDED** ✅ |
| **m** (medium) | ⚡ Medium | ⭐⭐⭐⭐ | 5GB | High accuracy |
| **l** (large) | 🐢 Slow | ⭐⭐⭐⭐⭐ | 8GB | Maximum quality |
| **x** (xlarge) | 🐢🐢 Slowest | ⭐⭐⭐⭐⭐ | 12GB | Best accuracy |

**Start with `s` (small)** - best balance of speed and accuracy.

---

## ⚙️ Training Parameters

```bash
# Image settings
--imgsz 640           # Resolution: 320, 416, 512, 640, 1024
--batch-size 16       # Per-step images: 8, 16, 32, 64

# Training control
--epochs 100          # Full passes through data (50-200)
--patience 20         # Early stop after N epochs (10-30)

# Learning rates
--lr0 0.01            # Initial: faster learning
--lrf 0.01            # Final: continue learning

# Regularization (prevent overfitting)
--weight-decay 0.0005 # L2 penalty (0.0001-0.001)
```

### Quick Parameter Adjustments

**Problem: GPU Out of Memory**
```bash
--batch-size 8  (reduce from 16)
--imgsz 416     (reduce from 640)
```

**Problem: Need Higher Accuracy**
```bash
--epochs 150    (increase from 100)
--model-size l  (use larger model)
```

**Problem: Overfitting (validation worse than training)**
```bash
--weight-decay 0.001  (increase regularization)
--batch-size 32       (increase batch size)
```

---

## 📁 File Locations

```
models/                           # All trained models
├── pineapple_yolov8n_latest.pt  # Deployed models
├── pineapple_yolov8s_latest.pt  # (auto-detected by AgriPinya)
└── pineapple_yolov8_training.pt # Others

archive/training/runs/detect/     # Archived training outputs from old runs
├── weights/
│   ├── best.pt                   # Best model ⭐
│   └── last.pt                   # Final epoch
├── results.csv                   # Metrics
└── confusion_matrix.png          # Visualization

dataset_yolov8/                   # Training data
├── data.yaml
├── train/images, train/labels
├── val/images, val/labels
└── test/images, test/labels

archive/results/                  # Archived detection result JSON files
archive/uploads/                  # Archived test media and uploads
```

---

## 📈 Monitoring Training

**What to watch during training:**
```
       Epoch  GPU_mem   box_loss   cls_loss   dfl_loss
    1/100      2.3G      1.234      2.145      0.987
    50/100      2.3G      0.550      0.456      0.234  ← Getting better ✅
   100/100      2.3G      0.450      0.234      0.187  ← Converged ✅
```

**Good signs:**
- ✅ Losses decreasing each epoch
- ✅ Metrics stable after epoch 50
- ✅ No GPU memory growth

**Bad signs:**
- ❌ Losses increasing
- ❌ GPU memory running out
- ❌ Validation loss worse than training (overfitting)

---

## 🚨 Error Quick Fixes

| Error | Solution |
|-------|----------|
| `ModuleNotFoundError: ultralytics` | `pip install ultralytics` |
| `CUDA out of memory` | `--batch-size 8` or `--imgsz 416` |
| `data.yaml not found` | Check path, run from correct directory |
| `No module YAML` | `pip install pyyaml` |
| `Poor detection accuracy` | Add more training data, increase epochs |
| `Model not detected by AgriPinya` | Check name: `pineapple_yolov8s_latest.pt` |

---

## 🔄 Full Training Workflow

```
┌─────────────────────────────────────────────┐
│ 1. Prepare Dataset                          │
│    python yolov8_quickstart.py --setup ...  │
└──────────────┬──────────────────────────────┘
               ↓
┌─────────────────────────────────────────────┐
│ 2. Train Model                              │
│    python yolov8_quickstart.py --train ...  │
│    (30-120 minutes)                         │
└──────────────┬──────────────────────────────┘
               ↓
┌─────────────────────────────────────────────┐
│ 3. Test Detection                           │
│    python scripts/test_yolov8_inference.py detect..│
└──────────────┬──────────────────────────────┘
               ↓
┌─────────────────────────────────────────────┐
│ 4. Deploy ✅ (Automatic!)                    │
│    Model ready in models/ directory          │
│    Upload images to AgriPinya                │
└─────────────────────────────────────────────┘
```

---

## 💡 Pro Tips

1. **Start small**: Use `--size n` to test pipeline quickly
2. **Verify data**: Always validate `data.yaml` before training
3. **Monitor GPU**: Watch `nvidia-smi` during training
4. **Save checkpoints**: Training saves every epoch automatically
5. **Test first**: Try detection before using in production
6. **Keep backups**: Copy best.pt to models/ directory

---

## 🎯 Success Metrics

| Metric | Target | What It Means |
|--------|--------|---|
| **mAP50** | >0.7 | Object detection accuracy |
| **mAP50-95** | >0.5 | Strict evaluation score |
| **Precision** | >0.85 | Few false positives |
| **Recall** | >0.80 | Catches most diseases |

---

## 📖 Detailed Docs

- 📘 Full workflow: `YOLOV8_WORKFLOW_GUIDE.md`
- 📗 All tools: `YOLOV8_TOOLS_README.md`
- 📙 Training parameters: `train_yolov8.py --help`
- 📕 Test options: `test_yolov8_inference.py --help`

---

## 🚀 Next Steps

```bash
# 1. Check system
python yolov8_quickstart.py --check

# 2. Setup your dataset
python yolov8_quickstart.py --setup /path/to/pineapple-disease

# 3. Train (choose based on GPU)
# Option A: Fast (30 min)
python yolov8_quickstart.py --train data.yaml --size n

# Option B: Recommended (60 min) ⭐
python yolov8_quickstart.py --train data.yaml --size s

# Option C: High quality (120 min)
python yolov8_quickstart.py --train data.yaml --size m

# 4. Test on image
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt test_image.jpg

# 5. Deploy to AgriPinya ✅ 
# (Already done! Model in models/ directory)
```

---

**🎉 That's it! Your YOLOv8 model is ready to detect pineapple diseases!**

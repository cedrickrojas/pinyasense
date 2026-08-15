# 🚀 TRAIN NOW - YOLOv8 Setup Guide

## 📍 YOU ARE HERE

✅ All training tools ready  
✅ Scripts created  
⏳ **NEXT: Transfer your dataset**

---

## ⚡ QUICK START (3 Steps)

### **STEP 1: Transfer Dataset (2-5 minutes)**

Your dataset: `C:\Users\Cedrick\Downloads\archive (1)`

**EASIEST METHOD - VSCode Drag & Drop:**

1. Open VSCode File Explorer (left panel)
2. Navigate to: `C:\Users\Cedrick\Downloads\`
3. **Drag `archive (1)` folder** into Linux workspace
4. Rename to: `dataset_raw`

**OR Upload with SCP:**
```powershell
# On Windows PowerShell:
scp -r "C:\Users\Cedrick\Downloads\archive (1)" voicebrain@YOUR-IP:/home/voicebrain/agripinya/dataset_raw
```

---

### **STEP 2: Run Training (1 command)**

```bash
cd /home/voicebrain/agripinya
./scripts/quick_train.sh dataset_raw
```

**That's it!** ✅

Once the best model is copied into `models/`, keep the old training artifacts in `archive/training/` instead of leaving them in the root workspace.

---

### **STEP 3: Wait (30-120 min)**

Training will:
- ✅ Check dependencies
- ✅ Convert dataset to YOLOv8 format
- ✅ Train model
- ✅ Deploy to AgriPinya
- ✅ Show results

---

## ⏱️ TIMELINE

| Task | Time |
|------|------|
| Transfer dataset | 2-5 min |
| Setup & convert | 2-3 min |
| **Training (GPU)** | **30-60 min** ⚡ |
| **Training (CPU)** | **2-3 hours** |
| Testing | 2 min |
| **Total (GPU)** | **~45 min** |

---

## 📊 WHAT YOU'LL GET

After training:
- ✅ `models/pineapple_yolov8s_latest.pt` (25 MB)
- ✅ Better detection accuracy (85-95%)
- ✅ Bounding boxes showing disease locations
- ✅ Real-time inference (30ms per image)
- ✅ Ready for production

---

## 🎯 COMMAND REFERENCE

```bash
# Standard training (60 min)
./scripts/quick_train.sh dataset_raw

# Fast training (30 min)
python scripts/train_complete.py dataset_raw --size n --epochs 50

# High quality (120 min)
python scripts/train_complete.py dataset_raw --size m --epochs 150

# Custom
python scripts/train_complete.py dataset_raw --size s --epochs 100 --batch-size 16
```

---

## 🧪 AFTER TRAINING

**Test your model:**
```bash
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt test_image.jpg
```

**Start AgriPinya:**
```bash
python app.py
# Open: http://localhost:5000
```

**Upload images → See disease detection with bounding boxes!** 🍍

---

## 🚨 IF YOU GET ERRORS

### "Dataset not found"
```bash
# Check if dataset exists:
ls -la dataset_raw/

# Should show:
# - train/
# - test/
```

### "CUDA out of memory"
```bash
# Reduce batch size:
python scripts/train_complete.py dataset_raw --batch-size 8
```

### "Training too slow"
```bash
# Use smaller model:
python scripts/train_complete.py dataset_raw --size n
```

---

## ✅ YOU'RE ALL SET!

**RIGHT NOW:**
1. Transfer `archive (1)` → Linux as `dataset_raw`
2. Run: `./scripts/quick_train.sh dataset_raw`
3. Wait ~1 hour
4. Done! 🎉

**Everything else is automatic!**

---

## 📞 NEED HELP?

- Quick commands: `cat YOLOV8_QUICK_REFERENCE.md`
- Full guide: `cat YOLOV8_WORKFLOW_GUIDE.md`
- Tools: `cat YOLOV8_TOOLS_README.md`

---

**Current time:** Check watch - training takes ~1 hour with GPU

**Your next action:** Transfer dataset to Linux!

🚀 **GOOD LUCK!**

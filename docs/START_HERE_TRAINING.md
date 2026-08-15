# 🍍 Complete ML Training Setup - Start Here!

## ⚡ FASTEST WAY - Just 3 Steps!

### **Step 1: Transfer Your Dataset to Linux** (5 min)

You have the dataset on Windows. Transfer it to Linux using **one of these methods:**

#### Option A: Using SSH (Fastest)
```bash
# On Windows PowerShell:
scp -r "C:\Users\Cedrick\Downloads\archive (1)" voicebrain@<linux-ip>:/home/voicebrain/agripinya/dataset_raw
```

Replace `<linux-ip>` with your Linux server IP.

#### Option B: Copy & Paste via VSCode
1. Open the extracted archive folder in VSCode
2. Use File Explorer to select all files
3. Copy to Linux workspace in VSCode

#### Option C: Upload via Web
1. Zip the archive folder
2. Upload to Linux using any file transfer method
3. Unzip on Linux

---

### **Step 2: Verify Dataset on Linux** (1 min)

Once transferred, check:
```bash
# List dataset structure
ls -lh ~/agripinya/dataset_raw/

# Should show:
# - train/
# - test/
# - (other files)
```

---

### **Step 3: Run Complete Training** (1 min)

```bash
cd /home/voicebrain/agripinya

# ONE COMMAND - Does Everything!
python scripts/train_complete.py ~/agripinya/dataset_raw --epochs 100
```

**That's it!** The script will:
- ✅ Check all dependencies
- ✅ Convert your dataset to YOLOv8 format
- ✅ Create configuration file
- ✅ Train the model
- ✅ Deploy to AgriPinya
- ✅ Show results

After training, archive the old run folder under `archive/training/` if you do not need to inspect the full training artifacts again.

**Training time:** 
- GPU: 30-120 min ⚡
- CPU: 2-6 hours

---

## 🎯 Training Customization

Make training faster or more accurate:

### **Fast Training (20-30 min)**
```bash
python scripts/train_complete.py dataset_raw --size n --epochs 50
```

### **Balanced (60 min) - Recommended ⭐**
```bash
python scripts/train_complete.py dataset_raw --size s --epochs 100
```

### **High Quality (120 min)**
```bash
python scripts/train_complete.py dataset_raw --size m --epochs 150
```

### **Maximum (200+ min)**
```bash
python scripts/train_complete.py dataset_raw --size l --epochs 200 --batch-size 32
```

---

## 📊 What Happens During Training

You'll see:
```
      Epoch  GPU_mem   box_loss   cls_loss   dfl_loss
    1/100      2.3G      1.234      2.145      0.987
   10/100      2.3G      0.850      1.456      0.567
   50/100      2.3G      0.450      0.456      0.234  ← Getting better!
  100/100      2.3G      0.350      0.234      0.187  ← Done!

Results:
  mAP50: 0.85
  mAP50-95: 0.72
  Precision: 0.92
  Recall: 0.88
```

---

## ✅ When Training Completes

You'll see:
```
🎉 TRAINING COMPLETE!

✅ All steps completed successfully!

📊 Summary:
   1. ✅ Dependencies checked
   2. ✅ Dataset converted to YOLOv8 format
   3. ✅ Configuration created
   4. ✅ Dataset validated
   5. ✅ Model trained
   6. ✅ Model deployed

🚀 Next Steps:
   1. Test model
   2. Use in AgriPinya
   3. Upload images for detection
```

---

## 🧪 Test Your Trained Model

After training completes:

```bash
# Test on single image
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt test_image.jpg

# Visualize with boxes
python scripts/test_yolov8_inference.py visualize models/pineapple_yolov8s_latest.pt test_image.jpg \
  --output result.jpg

# Check model info
python scripts/test_yolov8_inference.py info models/pineapple_yolov8s_latest.pt
```

---

## 🌐 Use in AgriPinya Web Interface

After training:

```bash
# Start AgriPinya
python app.py

# Open in browser
http://localhost:5000
```

Then:
1. Upload pineapple images
2. Model automatically detects diseases
3. See results with confidence scores

---

## 🚨 Troubleshooting

### "dataset_raw not found"
```bash
# Check your extracted dataset path
ls -lh /path/to/your/dataset/
```

### "CUDA out of memory"
```bash
python scripts/train_complete.py dataset_raw --batch-size 8 --size n
```

### "Training too slow"
```bash
# Use smaller model
python scripts/train_complete.py dataset_raw --size n
```

### "Low accuracy"
```bash
# Train longer
python scripts/train_complete.py dataset_raw --epochs 200
```

---

## 📝 Step-by-Step Complete Example

### **FULL EXAMPLE**

```bash
# 1. Activate environment
source /home/voicebrain/agripinya/venv/bin/activate

# 2. Go to project directory
cd /home/voicebrain/agripinya

# 3. Transfer dataset (on Windows PowerShell first)
# scp -r "C:\Users\Cedrick\Downloads\archive (1)" voicebrain@192.168.1.100:/home/voicebrain/agripinya/dataset_raw

# 4. Train (on Linux)
python scripts/train_complete.py dataset_raw --size s --epochs 100

# 5. Wait for training to complete...

# 6. Test model
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt test_image.jpg

# 7. Start AgriPinya
python app.py

# 8. Open browser: http://localhost:5000
```

---

## 📚 Command Reference

```bash
# Show help
python scripts/train_complete.py --help

# Quick check
python scripts/setup_diagnostics.py

# Test only
python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt image.jpg

# Full training
python scripts/train_complete.py dataset_raw --size s --epochs 100 --batch-size 16
```

---

## 🎉 That's It!

Your complete ML training pipeline is ready:

1. **Transfer dataset** to Linux
2. **Run one command:** `python scripts/train_complete.py dataset_raw`
3. **Wait** for training (30 min - 2 hours)
4. **Test** with test_yolov8_inference.py
5. **Deploy** in AgriPinya web interface

---

**Ready to train? Here's your next command:**

```bash
python scripts/train_complete.py dataset_raw --size s --epochs 100
```

**Or if you need the absolute minimal way:**

```bash
python scripts/train_complete.py dataset_raw
```

This uses default settings: small model, 100 epochs, balanced settings. 🚀

---

Questions? Check:
- `YOLOV8_QUICK_REFERENCE.md` - Quick commands
- `YOLOV8_WORKFLOW_GUIDE.md` - Detailed info
- `YOLOV8_TOOLS_README.md` - Tool reference

**Let's train your model! 🍍🚀**

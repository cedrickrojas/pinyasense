# AgriPinya Model Training & Firebase Integration

Complete guide para sa model training at Firebase integration ng AgriPinya system.

## 📚 Files Added

### 1. `train_model.py` - Model Training Script
Comprehensive Python script para mag-train ng custom pineapple disease detection model.

**Features:**
- ✅ Automatic dataset validation
- ✅ Image preprocessing at augmentation
- ✅ Pre-trained model support (EfficientNet, ResNet, MobileNet)
- ✅ Transfer learning para sa faster training
- ✅ Real-time progress tracking
- ✅ Automatic best model selection
- ✅ Detailed evaluation metrics

**Usage:**
```bash
# Basic training (default: EfficientNetB0, 50 epochs)
python scripts/train_model.py /path/to/dataset

# Advanced options
python scripts/train_model.py /path/to/dataset \
  --model-type efficientnet \
  --image-size 256 \
  --batch-size 32 \
  --epochs 100 \
  --output-dir ./models
```

### 2. `firebase_manager.py` - Firebase Integration Module
Complete Firebase Realtime Database integration with local fallback.

**Features:**
- ✅ Save/retrieve detection results
- ✅ Store sensor data
- ✅ User profile management
- ✅ Statistics aggregation
- ✅ Data export functionality
- ✅ Local storage fallback when offline
- ✅ Error handling at logging

**Usage:**
```python
from core.firebase_manager import FirebaseManager

# Initialize with config file
fm = FirebaseManager('firebase_config.json')

# Or with environment variables
fm = FirebaseManager()

# Save detection result
result = {
    'disease': 'Heart Rot',
    'confidence': 0.95,
    'timestamp': '2026-03-04_120000'
}
fm.save_detection_result(result, user_id='user123')

# Get detection history
results = fm.get_detection_results(user_id='user123', limit=50)

# Get statistics
stats = fm.aggregate_statistics(user_id='user123')
```

### 3. `firebase_setup.py` - Firebase Setup Guide & Testing
Interactive guide at testing script para sa Firebase configuration.

**Usage:**
```bash
# Print setup guide
python scripts/firebase_setup.py

# Test Firebase connection
python scripts/firebase_setup.py --test
```

### 4. `TRAINING_GUIDE.py` - Training Documentation
Comprehensive guide with step-by-step instructions (runnable as script).

**Usage:**
```bash
python TRAINING_GUIDE.py
```

## 🚀 Quick Start

### Model Training

1. **Prepare Dataset:**
```
dataset/
  ├── Heart Rot/
  │   ├── image1.jpg
  │   └── ...
  ├── Fruit Rot/
  │   └── ...
  ├── Yellow Spot/
  │   └── ...
  ├── Pink Disease/
  │   └── ...
  └── Healthy/
      └── ...
```

2. **Install Dependencies:**
```bash
pip install -r requirements.txt
```

3. **Train Model:**
```bash
python scripts/train_model.py ./dataset
```

4. **Update Model Path:**
Edit `disease_detector.py` at update model path:
```python
model_path = 'models/pineapple_disease_model_latest.h5'
```

5. **Restart Application:**
```bash
pkill -f "python app.py"
python app.py
```

### Firebase Integration

1. **Create Firebase Project:**
   - Go to https://console.firebase.google.com
   - Create new project
   - Enable Realtime Database

2. **Get Service Account Key:**
   - Go to Project Settings → Service Accounts
   - Generate new private key → Save as `serviceAccountKey.json`

3. **Configure .env:**
```bash
cp .env.example .env
# Edit .env with your Firebase credentials
```

```env
FIREBASE_SERVICE_ACCOUNT_KEY=./serviceAccountKey.json
FIREBASE_DATABASE_URL=https://your-project.firebaseio.com
ENABLE_FIREBASE=true
```

4. **Test Connection:**
```bash
python scripts/firebase_setup.py --test
```

5. **Integrate in app.py:**
```python
from core.firebase_manager import FirebaseManager

fm = FirebaseManager()

# Save detection results
fm.save_detection_result(result, user_id=email)

# Get user statistics
stats = fm.aggregate_statistics(user_id=email)
```

## 📊 Dataset Requirements

**Minimum:**
- 20 images per disease class
- Total: 100 images (5 classes × 20)

**Recommended:**
- 50-100 images per disease class
- Total: 250-500 images
- Different angles, lighting, conditions
- Mix of actual farm photos

**Best:**
- 100+ images per class
- Total: 500+ images
- Professional photography
- Annotated metadata

## 🎯 Training Tips

### For Quick Test:
```bash
python scripts/train_model.py ./dataset --epochs 20 --batch-size 16
```
Time: 5-10 minutes

### For Production Model:
```bash
python scripts/train_model.py ./dataset \
  --model-type efficientnet \
  --image-size 256 \
  --epochs 100 \
  --batch-size 32
```
Time: 30-60 minutes
Expected Accuracy: 90-95%

### For Mobile/Edge Deployment:
```bash
python scripts/train_model.py ./dataset --model-type mobile
```
Smaller model, faster inference

## 📈 Model Performance

**Accuracy Goals:**
- Overall: >90%
- Per-class: >85%
- Confidence: >0.80 average

**If Accuracy is Low:**
1. Add more training data (50+ images per class)
2. Ensure data variety (different angles, lighting)
3. Increase epochs (try 100+)
4. Try different model architecture
5. Use larger image size

## 🔒 Firebase Security

### Development (TEST mode):
```json
{
  "rules": {
    ".read": true,
    ".write": true
  }
}
```

### Production (Recommended):
```json
{
  "rules": {
    "users": {
      "$uid": {
        ".read": "$uid === auth.uid",
        ".write": "$uid === auth.uid"
      }
    }
  }
}
```

## ⚠️ Important Notes

### Data Security:
- ❌ Never commit `serviceAccountKey.json` to Git
- ✅ Add to `.gitignore`
- ✅ Use environment variables for sensitive data

### Model Storage:
- Models are large (100-200 MB)
- Keep backup of trained models
- Document model version at accuracy

### Dataset Privacy:
- If using real farm data, get permission
- Ensure GDPR compliance
- Encrypt sensitive medical/personal data

## 🐛 Troubleshooting

### Training Issues

**"No such file or directory"**
```
→ Check dataset path is correct
→ Verify folder structure matches requirements
```

**"CUDA out of memory"**
```
→ Reduce batch size: --batch-size 16
→ Reduce image size: --image-size 224
→ Use CPU instead: Set TF_CPP_MIN_LOG_LEVEL=3
```

**"Only N images found"**
```
→ Add more images to each disease folder
→ Ensure images in correct subfolders
→ Check file extensions (jpg, png, jpeg only)
```

### Firebase Issues

**"credentials.json not found"**
```
→ Download service account key from Firebase Console
→ Place at correct path in .env
```

**"Permission denied"**
```
→ Check Firebase security rules
→ Verify authenticated user has proper permissions
```

**"Database URL is invalid"**
```
→ Copy exact URL from Firebase Console
→ Format: https://project-name.firebaseio.com
```

## 📝 Environment Variables

Required for Firebase:
```env
FIREBASE_SERVICE_ACCOUNT_KEY=./serviceAccountKey.json
FIREBASE_DATABASE_URL=https://project.firebaseio.com
FIREBASE_STORAGE_BUCKET=project.appspot.com
ENABLE_FIREBASE=true
```

Optional:
```env
MODEL_PATH=models/pineapple_disease_model_latest.h5
LOG_LEVEL=INFO
DEBUG=False
```

## 📚 Resources

- [Firebase Docs](https://firebase.google.com/docs)
- [TensorFlow Training](https://tensorflow.org/tutorials)
- [PyTorch Training](https://pytorch.org/tutorials)
- [OpenCV](https://docs.opencv.org)

## ✅ Checklist for Production

- [ ] Model accuracy >90%
- [ ] Tested on real farm images
- [ ] Firebase credentials configured
- [ ] Security rules set properly
- [ ] Backup model saved
- [ ] Error handling implemented
- [ ] Logging configured
- [ ] Documentation updated
- [ ] Team trained on system

## 🎓 Next Steps

1. Prepare your pineapple disease dataset
2. Run training script
3. Evaluate model performance
4. Set up Firebase project
5. Configure environment variables
6. Test Firebase integration
7. Deploy to production
8. Monitor performance
9. Retrain periodically with new data

---

For issues or questions, refer to individual script documentation or Firebase guides.

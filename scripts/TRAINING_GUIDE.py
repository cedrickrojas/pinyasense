#!/usr/bin/env python3
"""
Model Training Quick Guide
Comprehensive guide para mag-train ng custom pineapple disease model
"""

def print_training_guide():
    guide = """
╔════════════════════════════════════════════════════════════════╗
║         AgriPinya Model Training Guide                         ║
║      Paano mag-train ng custom pineapple disease model         ║
╚════════════════════════════════════════════════════════════════╝

📋 STEP 1: Prepare Your Dataset
═════════════════════════════════════════════════════════════════

Directory Structure:
  dataset/
    ├── Heart Rot/
    │   ├── image1.jpg
    │   ├── image2.png
    │   └── ... (≥20 images)
    ├── Fruit Rot/
    │   ├── image1.jpg
    │   └── ...
    ├── Yellow Spot/
    │   ├── image1.jpg
    │   └── ...
    ├── Pink Disease/
    │   ├── image1.jpg
    │   └── ...
    └── Healthy/
        ├── image1.jpg
        └── ...

✅ Requirements:
  • Minimum 20 images per disease class
  • Recommended: 50-100 images per class
  • File formats: JPG, PNG, JPEG
  • Image size: Recommended 300x300 pixels or larger
  • Variety: Different angles, lighting, quality

💡 Tips for Dataset:
  • Take photos in natural conditions
  • Include diseased and healthy leaves
  • Use different cameras/phones
  • Include close-ups and wide shots
  • Balance sick vs healthy samples

📋 STEP 2: Install Dependencies
═════════════════════════════════════════════════════════════════

  pip install -r requirements.txt

✅ Required packages:
  ✓ tensorflow (for Keras models)
  ✓ opencv-python (image processing)
  ✓ scikit-learn (data splitting)
  ✓ tqdm (progress bars)
  ✓ numpy (numerical computing)

📋 STEP 3a: Quick Training (Recommended for Beginners)
═════════════════════════════════════════════════════════════════

  python train_model.py /path/to/dataset

Example:
  python train_model.py ./dataset

Output:
  ✅ Loads images from dataset
  ✅ Splits into train (80%) / test (20%)
  ✅ Builds EfficientNetB0 model
  ✅ Trains for 50 epochs
  ✅ Saves best model automatically
  ✅ Evaluates accuracy and metrics

Time: ~10-30 minutes (depending on dataset size)

📋 STEP 3b: Advanced Training (Custom Options)
═════════════════════════════════════════════════════════════════

Change Model Architecture:
  python train_model.py ./dataset --model-type resnet
  python train_model.py ./dataset --model-type mobile

Available models:
  • efficientnet: Best accuracy (default)
  • resnet: Good balance of speed/accuracy
  • mobile: Fastest, suitable for mobile/edge devices

Change Image Size:
  python train_model.py ./dataset --image-size 256
  
  Default: 224x224 (recommended)
  Higher size = better accuracy but slower training

Change Batch Size:
  python train_model.py ./dataset --batch-size 16
  
  Default: 32
  Lower = slower, less memory
  Higher = faster, more memory

Change Training Epochs:
  python train_model.py ./dataset --epochs 100
  
  Default: 50
  Higher = better accuracy but risk of overfitting

Change Output Directory:
  python train_model.py ./dataset --output-dir ./my_models

Full Example:
  python train_model.py ./dataset \\
    --model-type efficientnet \\
    --image-size 256 \\
    --batch-size 32 \\
    --epochs 100 \\
    --output-dir ./models

📋 STEP 4: Monitor Training
═════════════════════════════════════════════════════════════════

During training, you'll see:
  • Loss: Lower is better
  • Accuracy: Higher is better (aim for >90%)
  • Val Loss: Should decrease (overfitting if increases)
  • Precision: Of positive predictions, how many are correct
  • Recall: Of actual positives, how many we found

Good Training Signs:
  ✓ Loss continuously decreasing
  ✓ Accuracy continuously increasing
  ✓ Val loss follows training loss

Bad Training Signs:
  ✗ Val loss increasing while training loss decreases = Overfitting
  ✗ Loss not decreasing = Learning rate too low
  ✗ Accuracy stuck at low value = Model not learning

📋 STEP 5: Understand the Output
═════════════════════════════════════════════════════════════════

After training, you'll get:
  ✅ best_model.h5 - Best model during training
  ✅ pineapple_disease_model_TIMESTAMP.h5 - Full h5 model
  ✅ pineapple_disease_model_TIMESTAMP.keras - Keras format
  ✅ pineapple_disease_model_latest.h5 - Latest model symlink

Evaluation Metrics:
  • Loss: How wrong the model is
  • Accuracy: Percentage of correct predictions
  • Precision: True positives / (true + false positives)
  • Recall: True positives / (true + false negatives)

Example Output:
  Loss: 0.1234
  Accuracy: 0.9456 (94.56% correct)
  Precision: 0.9234
  Recall: 0.9567

📋 STEP 6: Use the Trained Model
═════════════════════════════════════════════════════════════════

1. Update disease_detector.py:
   In disease_detector.py, update:
   
   model_path = 'models/pineapple_disease_model_TIMESTAMP.h5'

2. Or copy to default location:
   cp models/pineapple_disease_model_TIMESTAMP.h5 \\
      models/pineapple_disease_model_latest.h5

3. Restart Flask app:
   pkill -f "python app.py"
   python app.py

4. Test the detection:
   Visit http://localhost:5000/dashboard
   Upload a test image

📋 STEP 7: Evaluate Model Performance
═════════════════════════════════════════════════════════════════

Test with sample images:
  python test_model.py

Manual testing:
  1. Open dashboard
  2. Upload test images
  3. Check if predictions match reality
  4. Compare confidence scores

Performance Goals:
  ✅ Accuracy: >85% overall
  ✅ Per-class accuracy: >80% each disease
  ✅ Confidence: Most predictions >0.8

If accuracy is low:
  1. Add more training data
  2. Increase epochs
  3. Try different model architecture
  4. Data augmentation already enabled

📋 TROUBLESHOOTING
═════════════════════════════════════════════════════════════════

Problem: "No such file or directory"
→ Check dataset path is correct
→ Ensure folder structure matches requirements

Problem: "CUDA out of memory"
→ Reduce batch size: --batch-size 16
→ Reduce image size: --image-size 224
→ Close other GPU-heavy programs

Problem: "Only N images found"
→ Add more images to dataset
→ Ensure images in correct subfolders
→ Check file extensions are jpg/png/jpeg

Problem: "Low accuracy after training"
→ Dataset might be too small (add more images)
→ Dataset might be too similar (vary your photos)
→ Try different model-type
→ Increase training epochs

📊 DATASET STATISTICS
═════════════════════════════════════════════════════════════════

Let's say you have:
  • 100 images per class = 500 total
  • Split: 400 train (80%), 100 test (20%)
  • Per class in training: ~80 images
  
Expect:
  ✓ Training time: 10-15 minutes
  ✓ Model size: 100-200 MB
  ✓ Accuracy: 85-92%

With 300 images per class = 1500 total:
  ✓ Training time: 30-45 minutes
  ✓ Model size: 100-200 MB
  ✓ Accuracy: 92-96%

📚 NEXT STEPS
═════════════════════════════════════════════════════════════════

1. ✅ Train your first model
2. ✅ Test it on your farm
3. 📈 Collect more data based on real usage
4. 🔄 Retrain periodically with new data
5. 📊 Monitor accuracy over time
6. ☁️  Deploy to Firebase for backup

🎯 PRODUCTION CHECKLIST
═════════════════════════════════════════════════════════════════

Before using in production:
  ☐ Accuracy >90%
  ☐ Tested on real farm images
  ☐ Performance acceptable (<5 sec per image)
  ☐ Model file backed up
  ☐ Previous model saved as fallback
  ☐ Security rules configured (if using Firebase)

════════════════════════════════════════════════════════════════════

💡 Quick Commands Reference
════════════════════════════════════════════════════════════════════

# Basic training
python train_model.py ./dataset

# With specific options
python train_model.py ./dataset \\
  --model-type efficientnet \\
  --epochs 50 \\
  --batch-size 32 \\
  --output-dir ./models

# Test the model
python test_model.py

# Setup Firebase
python firebase_setup.py --test

════════════════════════════════════════════════════════════════════
"""
    print(guide)

if __name__ == '__main__':
    print_training_guide()
    
    print("\n📝 For detailed training, run:")
    print("   python train_model.py /path/to/dataset")
    
    print("\n❓ Need help?")
    print("   1. Check dataset folder structure")
    print("   2. Ensure minimum 20 images per class")
    print("   3. Use recommended image sizes (224x224+)")
    print("   4. Monitor GPU memory usage")

import sys
print("Testing imports...")
try:
    import tensorflow as tf
    print(f"✅ TensorFlow {tf.__version__} imported successfully")
except Exception as e:
    print(f"❌ TensorFlow import failed: {e}")
    sys.exit(1)

try:
    import cv2
    print(f"✅ OpenCV {cv2.__version__} imported successfully")
except Exception as e:
    print(f"❌ OpenCV import failed: {e}")
    sys.exit(1)

model_files = [
    'models/pineapple_disease_model_final.keras',
    'models/pineapple_disease_model_improved.h5',
    'models/pineapple_disease_model.h5'
]

working_model = None
print("\nTesting model loading...")
for model_file in model_files:
    try:
        print(f"\nTrying {model_file}...")
        model = tf.keras.models.load_model(model_file)
        print(f"✅ Model loaded successfully!")
        print(f"   Input shape: {model.input_shape}")
        print(f"   Output shape: {model.output_shape}")
        working_model = model_file
        break
    except Exception as e:
        print(f"❌ Failed: {str(e)[:100]}")

if working_model:
    print(f"\n✨ Success! Working model: {working_model}")
else:
    print("\n⚠️  No working model found, will use rule-based detection")

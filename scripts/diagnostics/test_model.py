#!/usr/bin/env python3
import tensorflow as tf
import sys

print("Testing model loading...")

# Try .h5 model first
try:
    print("\nTrying to load pineapple_disease_model.h5...")
    model = tf.keras.models.load_model('models/pineapple_disease_model.h5')
    print("SUCCESS: .h5 model loaded!")
    print(f"Model summary: {model.summary()}")
except Exception as e:
    print(f"FAILED: {e}")

# Try .keras model
try:
    print("\nTrying to load pineapple_disease_model_final.keras...")
    model = tf.keras.models.load_model('models/pineapple_disease_model_final.keras')
    print("SUCCESS: .keras model loaded!")
    print(f"Model summary: {model.summary()}")
except Exception as e:
    print(f"FAILED: {e}")

# Try improved model
try:
    print("\nTrying to load pineapple_disease_model_improved.h5...")
    model = tf.keras.models.load_model('models/pineapple_disease_model_improved.h5')
    print("SUCCESS: improved .h5 model loaded!")
    print(f"Model summary: {model.summary()}")
except Exception as e:
    print(f"FAILED: {e}")

#!/usr/bin/env python3
"""
AgriPinya Model Training Script
Trains a custom pineapple disease detection model using your dataset
"""

import os
import sys
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime

# Deep Learning imports
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, models
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau

# Data handling
from sklearn.model_selection import train_test_split
import cv2
from tqdm import tqdm

class PineappleDiseaseModelTrainer:
    """Trains a CNN model for pineapple disease classification"""
    
    def __init__(self, dataset_path, output_dir='models', image_size=224, batch_size=32):
        """
        Initialize trainer
        
        Args:
            dataset_path: Path to dataset folder with disease subfolders
            output_dir: Where to save trained models
            image_size: Input image size for model
            batch_size: Training batch size
        """
        self.dataset_path = dataset_path
        self.output_dir = output_dir
        self.image_size = image_size
        self.batch_size = batch_size
        self.model = None
        self.history = None
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Disease classes
        self.classes = ['Heart Rot', 'Fruit Rot', 'Yellow Spot', 'Pink Disease', 'Healthy']
        self.num_classes = len(self.classes)
        
    def validate_dataset(self):
        """Check if dataset structure is correct"""
        print(f"\n📁 Validating dataset at {self.dataset_path}")
        
        if not os.path.exists(self.dataset_path):
            print(f"❌ Dataset path does not exist: {self.dataset_path}")
            return False
        
        dataset_path = Path(self.dataset_path)
        
        for disease_class in self.classes:
            class_path = dataset_path / disease_class
            
            if not class_path.exists():
                print(f"❌ Missing disease folder: {disease_class}")
                return False
            
            # Count images
            image_files = list(class_path.glob('*.jpg')) + list(class_path.glob('*.png')) + list(class_path.glob('*.jpeg'))
            count = len(image_files)
            
            if count < 10:
                print(f"⚠️  {disease_class}: Only {count} images (recommended: ≥20)")
            else:
                print(f"✅ {disease_class}: {count} images")
        
        return True
    
    def load_images(self, split_ratio=0.8):
        """Load images from dataset"""
        print(f"\n📸 Loading images from {self.dataset_path}")
        
        images = []
        labels = []
        
        dataset_path = Path(self.dataset_path)
        
        for idx, disease_class in enumerate(self.classes):
            class_path = dataset_path / disease_class
            image_files = list(class_path.glob('*.jpg')) + \
                         list(class_path.glob('*.png')) + \
                         list(class_path.glob('*.jpeg'))
            
            print(f"  Loading {disease_class}...")
            
            for image_file in tqdm(image_files, desc=disease_class):
                try:
                    # Read image
                    img = cv2.imread(str(image_file))
                    if img is None:
                        continue
                    
                    # Resize
                    img = cv2.resize(img, (self.image_size, self.image_size))
                    
                    # Convert BGR to RGB
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    
                    # Normalize
                    img = img.astype('float32') / 255.0
                    
                    images.append(img)
                    labels.append(idx)
                    
                except Exception as e:
                    print(f"    Error loading {image_file}: {e}")
                    continue
        
        # Convert to numpy arrays
        X = np.array(images)
        y = np.array(labels)
        
        # Convert labels to one-hot
        y = keras.utils.to_categorical(y, self.num_classes)
        
        print(f"\n✅ Loaded {len(X)} images")
        
        # Split into train/test
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=1-split_ratio, random_state=42, stratify=np.argmax(y, axis=1)
        )
        
        print(f"   Train: {len(X_train)}, Test: {len(X_test)}")
        
        return (X_train, y_train), (X_test, y_test)
    
    def build_model(self, model_type='efficientnet'):
        """Build CNN model"""
        print(f"\n🏗️  Building {model_type} model...")
        
        if model_type == 'efficientnet':
            # Load pre-trained EfficientNetB0
            base_model = keras.applications.EfficientNetB0(
                input_shape=(self.image_size, self.image_size, 3),
                weights='imagenet',
                include_top=False
            )
            
        elif model_type == 'resnet':
            # Load pre-trained ResNet50
            base_model = keras.applications.ResNet50(
                input_shape=(self.image_size, self.image_size, 3),
                weights='imagenet',
                include_top=False
            )
            
        elif model_type == 'mobile':
            # Load pre-trained MobileNetV2
            base_model = keras.applications.MobileNetV2(
                input_shape=(self.image_size, self.image_size, 3),
                weights='imagenet',
                include_top=False
            )
        else:
            raise ValueError(f"Unknown model type: {model_type}")
        
        # Freeze base model
        base_model.trainable = False
        
        # Build model
        model = models.Sequential([
            keras.Input(shape=(self.image_size, self.image_size, 3)),
            base_model,
            layers.GlobalAveragePooling2D(),
            layers.Dense(256, activation='relu', kernel_regularizer=keras.regularizers.l2(1e-4)),
            layers.Dropout(0.5),
            layers.Dense(128, activation='relu', kernel_regularizer=keras.regularizers.l2(1e-4)),
            layers.Dropout(0.3),
            layers.Dense(self.num_classes, activation='softmax')
        ])
        
        # Compile
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=1e-3),
            loss='categorical_crossentropy',
            metrics=['accuracy', keras.metrics.Precision(), keras.metrics.Recall()]
        )
        
        print(f"✅ Model built successfully")
        print(f"   Total parameters: {model.count_params():,}")
        
        self.model = model
        return model
    
    def prepare_data_augmentation(self, X_train, y_train):
        """Create data augmentation pipelines"""
        print("\n🔄 Setting up data augmentation...")
        
        # Training data augmentation
        train_datagen = ImageDataGenerator(
            rotation_range=20,
            width_shift_range=0.2,
            height_shift_range=0.2,
            horizontal_flip=True,
            vertical_flip=True,
            zoom_range=0.2,
            brightness_range=[0.8, 1.2],
            fill_mode='nearest'
        )
        
        train_generator = train_datagen.flow(
            X_train, y_train,
            batch_size=self.batch_size,
            shuffle=True
        )
        
        return train_generator
    
    def train(self, X_train, y_train, X_test, y_test, epochs=50):
        """Train the model"""
        print(f"\n🚀 Training model for {epochs} epochs...")
        
        # Callbacks
        callbacks = [
            EarlyStopping(
                monitor='val_loss',
                patience=10,
                restore_best_weights=True,
                verbose=1
            ),
            ModelCheckpoint(
                os.path.join(self.output_dir, 'best_model.h5'),
                monitor='val_accuracy',
                save_best_only=True,
                verbose=1
            ),
            ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=5,
                min_lr=1e-7,
                verbose=1
            )
        ]
        
        # Train
        history = self.model.fit(
            X_train, y_train,
            batch_size=self.batch_size,
            epochs=epochs,
            validation_data=(X_test, y_test),
            callbacks=callbacks,
            verbose=1
        )
        
        self.history = history
        print(f"\n✅ Training completed!")
        
        return history
    
    def evaluate(self, X_test, y_test):
        """Evaluate the model"""
        print(f"\n📊 Evaluating model...")
        
        loss, accuracy, precision, recall = self.model.evaluate(X_test, y_test, verbose=0)
        
        print(f"   Loss: {loss:.4f}")
        print(f"   Accuracy: {accuracy:.4f}")
        print(f"   Precision: {precision:.4f}")
        print(f"   Recall: {recall:.4f}")
        
        return {'loss': loss, 'accuracy': accuracy, 'precision': precision, 'recall': recall}
    
    def save_model(self, model_name='pineapple_disease_model'):
        """Save the trained model"""
        print(f"\n💾 Saving model...")
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Save as .h5
        h5_path = os.path.join(self.output_dir, f'{model_name}_{timestamp}.h5')
        self.model.save(h5_path)
        print(f"   ✅ Saved: {h5_path}")
        
        # Save as .keras
        keras_path = os.path.join(self.output_dir, f'{model_name}_{timestamp}.keras')
        self.model.save(keras_path)
        print(f"   ✅ Saved: {keras_path}")
        
        # Also save as latest
        latest_h5 = os.path.join(self.output_dir, f'{model_name}_latest.h5')
        self.model.save(latest_h5)
        print(f"   ✅ Saved: {latest_h5}")
        
        return keras_path

def main():
    """Main training script"""
    parser = argparse.ArgumentParser(
        description='Train pineapple disease detection model'
    )
    parser.add_argument(
        'dataset_path',
        help='Path to dataset folder with disease subfolders'
    )
    parser.add_argument(
        '--model-type',
        default='efficientnet',
        choices=['efficientnet', 'resnet', 'mobile'],
        help='Model architecture to use'
    )
    parser.add_argument(
        '--image-size',
        type=int,
        default=224,
        help='Input image size'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=32,
        help='Training batch size'
    )
    parser.add_argument(
        '--epochs',
        type=int,
        default=50,
        help='Number of training epochs'
    )
    parser.add_argument(
        '--output-dir',
        default='models',
        help='Directory to save models'
    )
    
    args = parser.parse_args()
    
    print(f"""
    ╔════════════════════════════════════════════════════╗
    ║      AgriPinya Model Training Tool                ║
    ║      Pineapple Disease Detection                  ║
    ╚════════════════════════════════════════════════════╝
    """)
    
    # Create trainer
    trainer = PineappleDiseaseModelTrainer(
        dataset_path=args.dataset_path,
        output_dir=args.output_dir,
        image_size=args.image_size,
        batch_size=args.batch_size
    )
    
    # Validate dataset
    if not trainer.validate_dataset():
        print("❌ Dataset validation failed!")
        sys.exit(1)
    
    # Load data
    (X_train, y_train), (X_test, y_test) = trainer.load_images()
    
    # Build model
    trainer.build_model(model_type=args.model_type)
    
    # Train
    trainer.train(X_train, y_train, X_test, y_test, epochs=args.epochs)
    
    # Evaluate
    trainer.evaluate(X_test, y_test)
    
    # Save model
    model_path = trainer.save_model()
    
    print(f"""
    ╔════════════════════════════════════════════════════╗
    ║ ✅ Training Completed Successfully!              ║
    ║ Model saved at: {model_path}
    ║ Next steps:                                        ║
    ║ 1. Test the model with test_model.py             ║
    ║ 2. Update disease_detector.py model path         ║
    ║ 3. Restart the Flask app                         ║
    ╚════════════════════════════════════════════════════╝
    """)

if __name__ == '__main__':
    main()

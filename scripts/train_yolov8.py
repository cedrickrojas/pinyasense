#!/usr/bin/env python3
"""
YOLOv8 Training Script for Pineapple Disease Detection
Trains YOLOv8 object detection model on pineapple disease dataset
"""

import os
import sys
import argparse
import yaml
from pathlib import Path
from datetime import datetime

try:
    from ultralytics import YOLO
    import torch
except ImportError:
    print("❌ ultralytics or torch not installed")
    print("   Install with: pip install ultralytics torch torchvision")
    sys.exit(1)


class YOLOv8Trainer:
    """Trains YOLOv8 model for pineapple disease detection"""
    
    def __init__(self, dataset_yaml, output_dir='models', model_size='n', device=None):
        """
        Initialize YOLOv8 trainer
        
        Args:
            dataset_yaml: Path to data.yaml file
            output_dir: Output directory for models
            model_size: YOLOv8 model size (n/s/m/l/x)
            device: Device to use (0 for GPU, 'cpu' for CPU, None for auto)
        """
        self.dataset_yaml = dataset_yaml
        self.output_dir = output_dir
        self.model_size = model_size
        self.device = device or (0 if torch.cuda.is_available() else 'cpu')
        self.model = None
        self.results = None
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Verify dataset.yaml exists
        if not os.path.exists(dataset_yaml):
            raise FileNotFoundError(f"Dataset YAML not found: {dataset_yaml}")
        
        print(f"✅ YOLOv8 Trainer initialized")
        print(f"   Model size: {model_size}")
        print(f"   Device: {self.device}")
        print(f"   Output dir: {output_dir}")
    
    def validate_dataset(self):
        """Validate dataset structure"""
        print(f"\n📁 Validating dataset...")
        
        try:
            with open(self.dataset_yaml, 'r') as f:
                config = yaml.safe_load(f)
            
            print(f"✅ Dataset config loaded")
            print(f"   Classes: {config.get('names', {})}")
            print(f"   NC: {config.get('nc')}")
            
            # Check paths
            dataset_dir = os.path.dirname(self.dataset_yaml)
            
            for split in ['train', 'val', 'test']:
                split_path = config.get(split)
                if split_path:
                    full_path = os.path.join(dataset_dir, split_path)
                    if os.path.exists(full_path):
                        image_count = len([f for f in os.listdir(full_path) 
                                         if f.lower().endswith(('.jpg', '.png', '.jpeg'))])
                        print(f"   ✅ {split}: {image_count} images")
                    else:
                        print(f"   ⚠️  {split} path not found: {full_path}")
            
            return True
            
        except Exception as e:
            print(f"❌ Dataset validation failed: {e}")
            return False
    
    def load_model(self):
        """Load YOLOv8 model"""
        print(f"\n🤖 Loading YOLOv8{self.model_size} model...")
        
        try:
            model_name = f'yolov8{self.model_size}.pt'
            self.model = YOLO(model_name)
            print(f"✅ Model loaded: {model_name}")
            
            # Move to device
            if isinstance(self.device, int):
                self.model.to(f'cuda:{self.device}')
                print(f"   Device: GPU {self.device}")
            else:
                self.model.to(self.device)
                print(f"   Device: {self.device}")
            
            return True
            
        except Exception as e:
            print(f"❌ Failed to load model: {e}")
            return False
    
    def train(self, epochs=100, batch_size=16, imgsz=640, patience=20, 
              save_period=10, workers=4, resume=False):
        """Train YOLOv8 model"""
        print(f"\n🚀 Starting training...")
        print(f"   Epochs: {epochs}")
        print(f"   Batch size: {batch_size}")
        print(f"   Image size: {imgsz}")
        print(f"   Patience (early stopping): {patience}")
        
        try:
            # Train
            results = self.model.train(
                data=self.dataset_yaml,
                epochs=epochs,
                imgsz=imgsz,
                batch=batch_size,
                patience=patience,
                save=True,
                save_period=save_period,
                device=self.device,
                workers=workers,
                project=self.output_dir,
                name=f'yolov8{self.model_size}_pineapple',
                resume=resume,
                verbose=True,
                # Optimization
                optimizer='auto',  # SGD, Adam, AdamW, etc
                lr0=0.01,  # Initial learning rate
                lrf=0.01,  # Final learning rate
                # Augmentation
                mosaic=1.0,
                mixup=0.0,
                flipud=0.5,
                fliplr=0.5,
                degrees=10,
                translate=0.1,
                scale=0.5,
                # Logging
                save_txt=True,
                save_conf=True
            )
            
            self.results = results
            print(f"\n✅ Training completed!")
            
            return results
            
        except Exception as e:
            print(f"❌ Training failed: {e}")
            return None
    
    def validate(self):
        """Validate model on validation set"""
        print(f"\n📊 Validating model...")
        
        try:
            metrics = self.model.val()
            
            print(f"✅ Validation completed")
            print(f"   mAP50: {metrics.box.map50:.4f}")
            print(f"   mAP50-95: {metrics.box.map:.4f}")
            
            return metrics
            
        except Exception as e:
            print(f"❌ Validation failed: {e}")
            return None
    
    def test(self):
        """Test model on test set"""
        print(f"\n🧪 Testing model...")
        
        try:
            metrics = self.model.val(data=self.dataset_yaml, split='test')
            
            print(f"✅ Test completed")
            
            return metrics
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            return None
    
    def save_model(self, save_onnx=False, save_tflite=False):
        """Save trained model"""
        print(f"\n💾 Saving model...")
        
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Save as PyTorch
            pt_path = os.path.join(self.output_dir, f'pineapple_yolov8{self.model_size}_{timestamp}.pt')
            self.model.save(pt_path)
            print(f"   ✅ PyTorch model: {pt_path}")
            
            # Save as latest
            latest_path = os.path.join(self.output_dir, f'pineapple_yolov8{self.model_size}_latest.pt')
            self.model.save(latest_path)
            print(f"   ✅ Latest model: {latest_path}")
            
            # Save as ONNX
            if save_onnx:
                try:
                    onnx_path = os.path.join(self.output_dir, f'pineapple_yolov8{self.model_size}_{timestamp}.onnx')
                    self.model.export(format='onnx', imgsz=640, dynamic=False)
                    print(f"   ✅ ONNX model: {onnx_path}")
                except Exception as e:
                    print(f"   ⚠️  ONNX export failed: {e}")
            
            # Save as TFLite
            if save_tflite:
                try:
                    tflite_path = os.path.join(self.output_dir, f'pineapple_yolov8{self.model_size}_{timestamp}.tflite')
                    self.model.export(format='tflite', imgsz=640)
                    print(f"   ✅ TFLite model: {tflite_path}")
                except Exception as e:
                    print(f"   ⚠️  TFLite export failed: {e}")
            
            return pt_path
            
        except Exception as e:
            print(f"❌ Model save failed: {e}")
            return None
    
    def export_model(self, format='onnx'):
        """Export model to different formats"""
        print(f"\n📦 Exporting model to {format}...")
        
        try:
            path = self.model.export(format=format)
            print(f"✅ Export successful: {path}")
            return path
        except Exception as e:
            print(f"❌ Export failed: {e}")
            return None


def main():
    """Main training script"""
    parser = argparse.ArgumentParser(
        description='Train YOLOv8 model for pineapple disease detection'
    )
    parser.add_argument(
        'dataset_yaml',
        help='Path to data.yaml file'
    )
    parser.add_argument(
        '--model-size',
        default='n',
        choices=['n', 's', 'm', 'l', 'x'],
        help='YOLOv8 model size (n=nano, s=small, m=medium, l=large, x=xlarge)'
    )
    parser.add_argument(
        '--epochs',
        type=int,
        default=100,
        help='Number of training epochs'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=16,
        help='Training batch size'
    )
    parser.add_argument(
        '--imgsz',
        type=int,
        default=640,
        help='Image size for training'
    )
    parser.add_argument(
        '--patience',
        type=int,
        default=20,
        help='Early stopping patience'
    )
    parser.add_argument(
        '--output-dir',
        default='models',
        help='Output directory for models'
    )
    parser.add_argument(
        '--device',
        default=None,
        help='Device (0 for GPU, cpu for CPU, None for auto)'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Run validation after training'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Run testing after training'
    )
    parser.add_argument(
        '--export-onnx',
        action='store_true',
        help='Export model to ONNX format'
    )
    parser.add_argument(
        '--export-tflite',
        action='store_true',
        help='Export model to TFLite format'
    )
    
    args = parser.parse_args()
    
    # Convert device string to proper format
    if args.device and args.device != 'None':
        try:
            device = int(args.device)
        except:
            device = args.device
    else:
        device = None
    
    print(f"""
    ╔════════════════════════════════════════════════════╗
    ║        YOLOv8 Pineapple Disease Training          ║
    ║         Object Detection Model Training            ║
    ╚════════════════════════════════════════════════════╝
    """)
    
    # Create trainer
    trainer = YOLOv8Trainer(
        dataset_yaml=args.dataset_yaml,
        output_dir=args.output_dir,
        model_size=args.model_size,
        device=device
    )
    
    # Validate dataset
    if not trainer.validate_dataset():
        print("❌ Dataset validation failed!")
        sys.exit(1)
    
    # Load model
    if not trainer.load_model():
        print("❌ Failed to load model!")
        sys.exit(1)
    
    # Train
    trainer.train(
        epochs=args.epochs,
        batch_size=args.batch_size,
        imgsz=args.imgsz,
        patience=args.patience
    )
    
    # Validate
    if args.validate:
        trainer.validate()
    
    # Test
    if args.test:
        trainer.test()
    
    # Save model
    model_path = trainer.save_model(
        save_onnx=args.export_onnx,
        save_tflite=args.export_tflite
    )
    
    print(f"""
    ╔════════════════════════════════════════════════════╗
    ║ ✅ Training Completed Successfully!              ║
    ║ Model saved at: {model_path}
    ║ Next steps:                                        ║
    ║ 1. Update disease_detector.py model path         ║
    ║ 2. Test with inference                           ║
    ║ 3. Deploy to Flask app                           ║
    ╚════════════════════════════════════════════════════╝
    """)


if __name__ == '__main__':
    main()

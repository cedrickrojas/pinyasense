#!/usr/bin/env python3
"""
YOLOv8 Dataset Preparation and Training Setup
Helper script para sa YOLOv8 pineapple disease dataset
"""

import os
import shutil
import argparse
from pathlib import Path


def setup_yolov8_dataset(dataset_path, output_path='dataset_yolov8'):
    """
    Setup YOLOv8 dataset structure
    
    Args:
        dataset_path: Path to the downloaded YOLOv8 dataset
        output_path: Output directory for organized dataset
    """
    print(f"\n📁 Setting up YOLOv8 dataset...")
    print(f"   Source: {dataset_path}")
    print(f"   Output: {output_path}")
    
    dataset_path = Path(dataset_path)
    output_path = Path(output_path)
    
    # Check if data.yaml exists
    data_yaml = dataset_path / 'data.yaml'
    if not data_yaml.exists():
        print(f"❌ data.yaml not found in {dataset_path}")
        return False
    
    # Copy data.yaml to output
    output_path.mkdir(parents=True, exist_ok=True)
    shutil.copy(data_yaml, output_path / 'data.yaml')
    print(f"✅ Copied data.yaml")
    
    # Setup train, val, test directories
    for split in ['train', 'val', 'test']:
        split_path = dataset_path / split
        if split_path.exists():
            # Copy images
            images_src = split_path / 'images'
            images_dst = output_path / split / 'images'
            
            if images_src.exists():
                images_dst.parent.mkdir(parents=True, exist_ok=True)
                if not images_dst.exists():
                    shutil.copytree(images_src, images_dst)
                    print(f"✅ Copied {split}/images")
            
            # Copy labels
            labels_src = split_path / 'labels'
            labels_dst = output_path / split / 'labels'
            
            if labels_src.exists():
                labels_dst.parent.mkdir(parents=True, exist_ok=True)
                if not labels_dst.exists():
                    shutil.copytree(labels_src, labels_dst)
                    print(f"✅ Copied {split}/labels")
    
    print(f"\n✅ Dataset setup complete!")
    print(f"You can now train with:")
    print(f"  python train_yolov8.py {output_path}/data.yaml")
    
    return True


def validate_yolov8_dataset(data_yaml_path):
    """Validate YOLOv8 dataset structure"""
    print(f"\n✅ Validating YOLOv8 dataset...")
    
    yaml_path = Path(data_yaml_path)
    dataset_dir = yaml_path.parent
    
    try:
        import yaml
        with open(yaml_path, 'r') as f:
            config = yaml.safe_load(f)
        
        print(f"   Classes: {config.get('nc')} classes")
        print(f"   Names: {config.get('names')}")
        
        # Check dataset splits
        for split in ['train', 'val', 'test']:
            split_info = config.get(split)
            if split_info:
                split_path = dataset_dir / split_info
                if split_path.exists():
                    image_count = len(list(split_path.glob('*/*.jpg'))) + \
                                 len(list(split_path.glob('*/*.png')))
                    print(f"   ✅ {split}: {image_count} images")
                else:
                    print(f"   ⚠️  {split} not found")
        
        return True
        
    except Exception as e:
        print(f"   ❌ Validation failed: {e}")
        return False


def print_quick_guide():
    """Print quick start guide"""
    guide = """
╔════════════════════════════════════════════════════════╗
║      YOLOv8 Pineapple Disease Training Guide         ║
║      Object Detection with YOLOv8                     ║
╚════════════════════════════════════════════════════════╝

🎯 QUICK START
═════════════════════════════════════════════════════════

1. Prepare your YOLOv8 dataset:
   python prepare_yolov8_dataset.py /path/to/dataset

2. Validate dataset:
   python prepare_yolov8_dataset.py /path/to/dataset --validate

3. Train YOLOv8 model:
   python train_yolov8.py /path/to/data.yaml

📊 DATASET FORMAT
═════════════════════════════════════════════════════════

Your dataset should have:
  📁 dataset/
     ├── data.yaml          (class definitions)
     ├── train/
     │   ├── images/        (training images)
     │   └── labels/        (YOLO format labels)
     ├── val/
     │   ├── images/
     │   └── labels/
     └── test/
         ├── images/
         └── labels/

YOLO Label Format (txt files):
  <class_id> <x_center> <y_center> <width> <height>
  (coordinates normalized to 0-1)

📋 data.yaml Example
═════════════════════════════════════════════════════════

path: /path/to/dataset
train: train/images
val: val/images
test: test/images

nc: 5
names:
  0: CrownRot
  1: FruitRot
  2: MealybugWilt
  3: RootRot
  4: Healthy

🚀 TRAINING OPTIONS
═════════════════════════════════════════════════════════

Quick (nano model):
  python train_yolov8.py data.yaml --model-size n

Standard (small model):
  python train_yolov8.py data.yaml --model-size s

High Accuracy (large model):
  python train_yolov8.py data.yaml --model-size l

Custom Configuration:
  python train_yolov8.py data.yaml \\
    --model-size s \\
    --epochs 100 \\
    --batch-size 32 \\
    --imgsz 640

📈 MODEL SIZES
═════════════════════════════════════════════════════════

nano (n)   - Fast, small, less accurate (~6M params)
small (s)  - Balanced (≈11M params)
medium (m) - Good accuracy (≈25M params)
large (l)  - High accuracy (≈43M params)
xlarge (x) - Best accuracy, slow (≈71M params)

📊 EXPECTED OUTPUT
═════════════════════════════════════════════════════════

After training, you'll get:
  ✅ models/pineapple_yolov8s_TIMESTAMP.pt
  ✅ models/pineapple_yolov8s_latest.pt
  ✅ Training metrics (mAP, loss, accuracy)

✅ USING THE TRAINED MODEL
═════════════════════════════════════════════════════════

The model will be automatically detected by AgriPinya!

1. Upload to Flask app
2. Model loads automatically
3. Detection happens with YOLOv8

Test locally:
  from ultralytics import YOLO
  model = YOLO('models/pineapple_yolov8s_latest.pt')
  results = model.predict('test_image.jpg')

⚙️  CONFIGURATION
═════════════════════════════════════════════════════════

Training epochs: 100 (default)
Batch size: 16 (adjust based on GPU memory)
Image size: 640 (standard for YOLO)
Patience: 20 (early stopping)

GPU Memory Requirements:
  nano:    ~2GB
  small:   ~3GB
  medium:  ~5GB
  large:   ~8GB
  xlarge:  ~12GB

💡 TIPS FOR BEST RESULTS
═════════════════════════════════════════════════════════

1. Dataset Quality:
   - Minimum 20 images per class
   - 50-100 recommended
   - 100+ for production

2. Dataset Variety:
   - Different lighting conditions
   - Various angles and distances
   - Different camera types/quality

3. Training:
   - Start with nano or small model
   - Use at least 100 epochs
   - Monitor validation loss
   - Stop if overfitting occurs

4. Post-Training:
   - Validate on test set
   - Test on new farm images
   - Monitor real-world performance

⚠️  TROUBLESHOOTING
═════════════════════════════════════════════════════════

"CUDA out of memory"
  → Reduce batch size: --batch-size 8
  → Reduce image size: --imgsz 416

"No module named 'ultralytics'"
  → Install: pip install ultralytics

"data.yaml not found"
  → Check dataset path
  → Ensure data.yaml exists in dataset root

"Poor accuracy"
  → Add more training data
  → Increase training epochs
  → Check data quality
  → Try larger model size

📚 RESOURCES
═════════════════════════════════════════════════════════

- YOLOv8 Docs: https://docs.ultralytics.com
- Roboflow Datasets: https://roboflow.com
- YOLO Tutorial: https://docs.ultralytics.com/modes/train

════════════════════════════════════════════════════════════
"""
    print(guide)


def main():
    """Main script"""
    parser = argparse.ArgumentParser(
        description='YOLOv8 Dataset Preparation and Training Setup'
    )
    parser.add_argument(
        'dataset_path',
        nargs='?',
        help='Path to YOLOv8 dataset'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate YOLOv8 dataset'
    )
    parser.add_argument(
        '--output',
        default='dataset_yolov8',
        help='Output directory for organized dataset'
    )
    
    args = parser.parse_args()
    
    if not args.dataset_path:
        print_quick_guide()
        return
    
    dataset_path = Path(args.dataset_path)
    
    if not dataset_path.exists():
        print(f"❌ Dataset path not found: {dataset_path}")
        return
    
    # Check if it's data.yaml or dataset directory
    if dataset_path.is_file() and dataset_path.name == 'data.yaml':
        # Validate data.yaml
        if args.validate:
            validate_yolov8_dataset(str(dataset_path))
    else:
        # Setup dataset
        setup_yolov8_dataset(str(dataset_path), args.output)


if __name__ == '__main__':
    main()

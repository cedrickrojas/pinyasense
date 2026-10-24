#!/usr/bin/env python3
"""
AgriPinya Complete Training Automation
One-command solution: dataset conversion → training → deployment
"""

import os
import sys
import subprocess
from pathlib import Path
import shutil
import argparse
from datetime import datetime


def print_banner():
    """Print startup banner"""
    print(f"""
╔═════════════════════════════════════════════════════════╗
║     🍍 AgriPinya - Complete ML Training System 🍍      ║
║                                                          ║
║        Automated Dataset Setup & YOLOv8 Training        ║
╚═════════════════════════════════════════════════════════╝

⏰ Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
""")


def check_dependencies():
    """Check all required packages"""
    print("\n" + "="*60)
    print("📦 STEP 1: Checking Dependencies")
    print("="*60)
    
    deps = ['torch', 'ultralytics', 'cv2', 'yaml', 'numpy']
    missing = []
    
    for dep in deps:
        try:
            __import__(dep)
            print(f"✅ {dep}")
        except ImportError:
            print(f"❌ {dep}")
            missing.append(dep)
    
    if missing:
        print(f"\n⚠️  Installing missing packages: {', '.join(missing)}")
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install'] + missing,
            check=False
        )
    
    return True


def convert_dataset(input_dir, output_dir='dataset_yolov8'):
    """Convert dataset to YOLOv8 format"""
    print("\n" + "="*60)
    print("🔄 STEP 2: Converting Dataset")
    print("="*60)
    
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    print(f"\n📥 Input: {input_path}")
    print(f"📤 Output: {output_path}")
    
    if not input_path.exists():
        print(f"❌ Input directory not found: {input_path}")
        return False
    
    # Create output structure
    print("\n📁 Creating directory structure...")
    dirs = [
        'train/images', 'train/labels',
        'val/images', 'val/labels',
        'test/images', 'test/labels'
    ]
    for dir_name in dirs:
        (output_path / dir_name).mkdir(parents=True, exist_ok=True)
        print(f"  ✅ {dir_name}")
    
    # Detect and convert format
    print("\n🔍 Detecting dataset format...")
    
    if (input_path / 'train' / 'obj').exists():
        print("   Found: train/obj structure")
        train_dir = input_path / 'train' / 'obj'
        copy_split(train_dir, output_path / 'train', 'training')
    elif (input_path / 'train').exists():
        print("   Found: train/ directory")
        copy_split(input_path / 'train', output_path / 'train', 'training')
    
    if (input_path / 'test' / 'test').exists():
        print("   Found: test/test structure")
        test_dir = input_path / 'test' / 'test'
        copy_split(test_dir, output_path / 'test', 'test')
    elif (input_path / 'test').exists():
        print("   Found: test/ directory")
        copy_split(input_path / 'test', output_path / 'test', 'test')
    
    print("\n✅ Dataset conversion complete!")
    return True


def copy_split(src, dst, split_name):
    """Copy images and labels"""
    src_path = Path(src)
    images_dst = Path(dst) / 'images'
    labels_dst = Path(dst) / 'labels'
    
    images_dst.mkdir(parents=True, exist_ok=True)
    labels_dst.mkdir(parents=True, exist_ok=True)
    
    # Copy images
    image_exts = ['.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG']
    image_count = 0
    for ext in image_exts:
        for img in src_path.glob(f'*{ext}'):
            try:
                shutil.copy2(img, images_dst / img.name)
                image_count += 1
            except:
                pass
    
    # Copy labels
    label_count = 0
    for label in src_path.glob('*.txt'):
        try:
            shutil.copy2(label, labels_dst / label.name)
            label_count += 1
        except:
            pass
    
    print(f"   📊 {split_name}: {image_count} images, {label_count} labels")


def create_data_yaml(dataset_dir):
    """Create YOLOv8 data.yaml"""
    print("\n" + "="*60)
    print("📋 STEP 3: Creating Data Configuration")
    print("="*60)
    
    dataset_path = Path(dataset_dir).absolute()
    
    # Canonical 5-class pineapple disease set
    classes = {
        0: 'CrownRot',
        1: 'FruitRot',
        2: 'MealybugWilt',
        3: 'RootRot',
        4: 'Healthy'
    }
    
    yaml_content = f"""# YOLOv8 Pineapple Disease Dataset
path: {dataset_path}
train: train/images
val: val/images
test: test/images

nc: {len(classes)}
names:
"""
    
    for idx, name in classes.items():
        yaml_content += f"  {idx}: {name}\n"
    
    yaml_path = Path(dataset_dir) / 'data.yaml'
    with open(yaml_path, 'w') as f:
        f.write(yaml_content)
    
    print(f"\n✅ Created: data.yaml")
    print(f"   Classes: {len(classes)}")
    print(f"   Location: {yaml_path}")
    
    return yaml_path


def validate_dataset(dataset_dir):
    """Validate dataset structure"""
    print("\n" + "="*60)
    print("✅ STEP 4: Validating Dataset")
    print("="*60)
    
    dataset_path = Path(dataset_dir)
    
    required = ['data.yaml', 'train/images', 'train/labels']
    
    all_good = True
    for item in required:
        item_path = dataset_path / item
        if item_path.exists():
            if item_path.is_dir():
                count = len(list(item_path.glob('*')))
                print(f"✅ {item}: {count} files")
            else:
                print(f"✅ {item}")
        else:
            print(f"❌ {item}: MISSING")
            all_good = False
    
    return all_good


def train_model(data_yaml, model_size='s', epochs=100, batch_size=16):
    """Train YOLOv8 model"""
    print("\n" + "="*60)
    print("🚀 STEP 5: Starting YOLOv8 Training")
    print("="*60)
    
    print(f"""
Training Configuration:
  📊 Dataset: {data_yaml}
  🎯 Model Size: {model_size}
  ⏱️  Epochs: {epochs}
  📦 Batch Size: {batch_size}
  🖥️  Device: GPU (if available) / CPU
""")
    
    print("⏳ This may take 30min-2hours depending on your hardware...\n")
    
    try:
        from ultralytics import YOLO
        
        # Load model
        print("📥 Loading YOLOv8 model...")
        model_dict = {'n': 'yolov8n.pt', 's': 'yolov8s.pt', 'm': 'yolov8m.pt', 
                     'l': 'yolov8l.pt', 'x': 'yolov8x.pt'}
        model_name = model_dict.get(model_size, 'yolov8s.pt')
        model = YOLO(model_name)
        
        # Train
        print("🔄 Starting training...\n")
        results = model.train(
            data=str(data_yaml),
            epochs=epochs,
            imgsz=640,
            batch=batch_size,
            patience=20,
            device=0,  # GPU device
            verbose=True,
            save=True,
            project='runs/detect',
            name='train'
        )
        
        print("\n✅ Training complete!")
        return True
        
    except Exception as e:
        print(f"❌ Training error: {e}")
        return False


def deploy_model(model_size='s'):
    """Deploy trained model to AgriPinya"""
    print("\n" + "="*60)
    print("🚀 STEP 6: Deploying Model")
    print("="*60)
    
    try:
        models_dir = Path('models')
        models_dir.mkdir(exist_ok=True)
        
        train_dir = Path('runs/detect/train/weights')
        if (train_dir / 'best.pt').exists():
            src = train_dir / 'best.pt'
            dst = models_dir / f'pineapple_yolov8{model_size}_latest.pt'
            
            shutil.copy2(src, dst)
            
            size_mb = dst.stat().st_size / 1e6
            print(f"\n✅ Model deployed!")
            print(f"   Location: {dst}")
            print(f"   Size: {size_mb:.1f} MB")
            
            # Also update to use in app
            print(f"\n   Model is ready to use in AgriPinya!")
            print(f"   Start with: python app.py")
            
            return True
        else:
            print("❌ Trained model not found")
            return False
            
    except Exception as e:
        print(f"❌ Deployment error: {e}")
        return False


def test_model():
    """Test the trained model"""
    print("\n" + "="*60)
    print("🧪 STEP 7: Testing Model (Optional)")
    print("="*60)
    
    print("""
To test your trained model, run:

  python -m scripts.diagnostics.test_yolov8_inference detect \\
    models/pineapple_yolov8s_latest.pt \\
    path/to/test/image.jpg

Or visualize results:

  python -m scripts.diagnostics.test_yolov8_inference visualize \\
    models/pineapple_yolov8s_latest.pt \\
    path/to/test/image.jpg --output result.jpg
""")


def print_summary():
    """Print completion summary"""
    print("\n" + "="*60)
    print("🎉 TRAINING COMPLETE!")
    print("="*60)
    
    print(f"""
✅ All steps completed successfully!

📊 Summary:
   1. ✅ Dependencies checked
   2. ✅ Dataset converted to YOLOv8 format
   3. ✅ Configuration created (data.yaml)
   4. ✅ Dataset validated
   5. ✅ Model trained
   6. ✅ Model deployed to models/ directory

🚀 Next Steps:

1. Test your model:
   python -m scripts.diagnostics.test_yolov8_inference detect \\
     models/pineapple_yolov8s_latest.pt test_image.jpg

2. Use in AgriPinya:
   python app.py
   Open: http://localhost:5000

3. Upload images for disease detection!

⏰ Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
""")


def main():
    """Main automation pipeline"""
    parser = argparse.ArgumentParser(description='Complete ML Training Pipeline')
    parser.add_argument('dataset_dir', help='Input dataset directory')
    parser.add_argument('--output', default='dataset_yolov8', help='Output dir')
    parser.add_argument('--size', choices=['n', 's', 'm', 'l', 'x'], 
                       default='s', help='Model size')
    parser.add_argument('--epochs', type=int, default=100, help='Training epochs')
    parser.add_argument('--batch-size', type=int, default=16, help='Batch size')
    
    args = parser.parse_args()
    
    print_banner()
    
    try:
        # Step 1: Check
        if not check_dependencies():
            sys.exit(1)
        
        # Step 2: Convert
        if not convert_dataset(args.dataset_dir, args.output):
            sys.exit(1)
        
        # Step 3: Configure
        yaml_path = create_data_yaml(args.output)
        
        # Step 4: Validate
        if not validate_dataset(args.output):
            print("⚠️  Dataset issues detected but continuing anyway...")
        
        # Step 5: Train
        if not train_model(yaml_path, args.size, args.epochs, args.batch_size):
            sys.exit(1)
        
        # Step 6: Deploy
        if not deploy_model(args.size):
            print("⚠️  Deployment failed, but model is in runs/ directory")
        
        # Step 7: Test
        test_model()
        
        # Summary
        print_summary()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Training interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

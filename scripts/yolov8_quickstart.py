#!/usr/bin/env python3
"""
YOLOv8 Pineapple Disease - Automated Quick Start
Simplified startup script for training and deployment
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def print_banner():
    """Print AgriPinya YOLOv8 banner"""
    banner = """
╔═════════════════════════════════════════════════════════╗
║     🍍 AgriPinya YOLOv8 Disease Detection Setup 🍍     ║
║                                                          ║
║         Automated Training & Deployment Script          ║
╚═════════════════════════════════════════════════════════╝
"""
    print(banner)


def check_dependencies():
    """Check if all dependencies are installed"""
    print("\n📦 Checking dependencies...")
    
    dependencies = {
        'torch': 'PyTorch',
        'ultralytics': 'YOLOv8',
        'cv2': 'OpenCV',
        'yaml': 'PyYAML',
        'numpy': 'NumPy'
    }
    
    missing = []
    for module, name in dependencies.items():
        try:
            __import__(module)
            print(f"   ✅ {name}")
        except ImportError:
            print(f"   ❌ {name}")
            missing.append(module)
    
    if missing:
        print(f"\n⚠️  Missing packages: {', '.join(missing)}")
        print(f"\nInstall with:")
        print(f"   pip install {' '.join(missing)}")
        return False
    
    print(f"\n✅ All dependencies installed!")
    return True


def setup_dataset(dataset_path):
    """Setup dataset"""
    print(f"\n📁 Setting up dataset from: {dataset_path}")
    
    try:
        result = subprocess.run(
            [sys.executable, 'prepare_yolov8_dataset.py', dataset_path],
            capture_output=True,
            text=True,
            timeout=300
        )
        print(result.stdout)
        if result.returncode != 0:
            print(f"❌ Error: {result.stderr}")
            return False
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def train_model(data_yaml, model_size='s', epochs=100, batch_size=16):
    """Train YOLOv8 model"""
    print(f"\n🚀 Training YOLOv8 {model_size} model for {epochs} epochs...")
    print(f"   Batch size: {batch_size}")
    print(f"   Data: {data_yaml}")
    
    try:
        cmd = [
            sys.executable,
            'train_yolov8.py',
            data_yaml,
            '--model-size', model_size,
            '--epochs', str(epochs),
            '--batch-size', str(batch_size)
        ]
        
        result = subprocess.run(cmd, timeout=36000)  # 10 hour timeout
        
        if result.returncode == 0:
            print(f"\n✅ Training complete!")
            return True
        else:
            print(f"❌ Training failed")
            return False
    except subprocess.TimeoutExpired:
        print(f"❌ Training timeout (10 hours)")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def evaluate_model(model_path, data_yaml):
    """Evaluate trained model"""
    print(f"\n📊 Evaluating model: {model_path}")
    
    try:
        from ultralytics import YOLO
        model = YOLO(model_path)
        metrics = model.val()
        
        print(f"\n✅ Evaluation Results:")
        print(f"   mAP50: {metrics.results_dict.get('metrics/mAP50(B)', 'N/A')}")
        print(f"   mAP50-95: {metrics.results_dict.get('metrics/mAP50-95(B)', 'N/A')}")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_model(model_path, test_image):
    """Test model on single image"""
    print(f"\n🧪 Testing model on: {test_image}")
    
    try:
        cmd = [
            sys.executable,
            'test_yolov8_inference.py',
            'detect',
            model_path,
            test_image
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        
        if result.returncode == 0:
            print(f"✅ Detection successful!")
            return True
        else:
            print(f"❌ Detection failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def deploy_model(model_path, dest_name='pineapple_yolov8n_latest.pt'):
    """Deploy model to AgriPinya"""
    print(f"\n🚀 Deploying model...")
    
    try:
        models_dir = Path('models')
        models_dir.mkdir(exist_ok=True)
        
        dest_path = models_dir / dest_name
        
        # Copy model
        import shutil
        shutil.copy(model_path, dest_path)
        
        print(f"✅ Model deployed!")
        print(f"   Location: {dest_path}")
        print(f"   Size: {dest_path.stat().st_size / 1e6:.1f} MB")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def print_quick_commands():
    """Print quick commands reference"""
    commands = """
╔════════════════════════════════════════════════════════╗
║           🔧 Quick Commands Reference                 ║
╚════════════════════════════════════════════════════════╝

📝 Setup:
  python yolov8_quickstart.py --setup /path/to/dataset

🚀 Train (pick one):
  # Quick (30 min)
  python yolov8_quickstart.py --train data.yaml --size n

  # Recommended (60 min)  
  python yolov8_quickstart.py --train data.yaml --size s

  # High quality (120 min)
  python yolov8_quickstart.py --train data.yaml --size m

🧪 Test:
  # Single image
  python test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt test.jpg

  # Visualize
  python test_yolov8_inference.py visualize models/pineapple_yolov8s_latest.pt test.jpg

  # Batch
  python test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt /path/to/images

📊 Full Workflow:
  1. Setup: python yolov8_quickstart.py --setup /path/to/dataset
  2. Train: python yolov8_quickstart.py --train data.yaml --size s --epochs 100
  3. Test:  python test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt test.jpg
  4. Deploy: Automatic! Model is ready to use in AgriPinya

════════════════════════════════════════════════════════════
"""
    print(commands)


def main():
    """Main script"""
    parser = argparse.ArgumentParser(
        description='YOLOv8 Pineapple Disease - Quick Start'
    )
    
    parser.add_argument(
        '--check',
        action='store_true',
        help='Check dependencies'
    )
    parser.add_argument(
        '--setup',
        metavar='DATASET_PATH',
        help='Setup dataset from path'
    )
    parser.add_argument(
        '--train',
        metavar='DATA_YAML',
        help='Train model on data.yaml'
    )
    parser.add_argument(
        '--test',
        metavar='TEST_IMAGE',
        help='Test trained model on image'
    )
    parser.add_argument(
        '--deploy',
        metavar='MODEL_PATH',
        help='Deploy model to AgriPinya'
    )
    parser.add_argument(
        '--size',
        choices=['n', 's', 'm', 'l', 'x'],
        default='s',
        help='Model size (default: s)'
    )
    parser.add_argument(
        '--epochs',
        type=int,
        default=100,
        help='Training epochs (default: 100)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=16,
        help='Batch size (default: 16)'
    )
    parser.add_argument(
        '--full',
        metavar='DATASET_PATH',
        help='Full workflow: setup → train → test → deploy'
    )
    
    args = parser.parse_args()
    
    print_banner()
    
    # Check dependencies
    if args.check or not (args.setup or args.train or args.test or args.deploy or args.full):
        if not check_dependencies():
            sys.exit(1)
    
    if args.check:
        print_quick_commands()
        return
    
    # Setup
    if args.setup:
        if not check_dependencies():
            sys.exit(1)
        if not setup_dataset(args.setup):
            sys.exit(1)
    
    # Train
    if args.train:
        if not check_dependencies():
            sys.exit(1)
        if not train_model(args.train, args.size, args.epochs, args.batch_size):
            sys.exit(1)
    
    # Test
    if args.test and args.train:
        model_path = f'runs/detect/train/weights/best.pt'
        if not test_model(model_path, args.test):
            sys.exit(1)
    
    # Deploy
    if args.deploy:
        model_name = f'pineapple_yolov8{args.size}_latest.pt'
        if not deploy_model(args.deploy, model_name):
            sys.exit(1)
    
    # Full workflow
    if args.full:
        if not check_dependencies():
            sys.exit(1)
        
        data_yaml = Path(args.full) / 'data.yaml'
        
        if not setup_dataset(args.full):
            sys.exit(1)
        
        if not train_model(str(data_yaml), args.size, args.epochs, args.batch_size):
            sys.exit(1)
        
        model_path = 'runs/detect/train/weights/best.pt'
        if not deploy_model(model_path, f'pineapple_yolov8{args.size}_latest.pt'):
            sys.exit(1)
        
        print("\n" + "="*55)
        print("✅ FULL WORKFLOW COMPLETE!")
        print("="*55)
        print(f"\n🎉 Your YOLOv8 model is ready to use!")
        print(f"\nNext steps:")
        print(f"  1. Test detection: python test_yolov8_inference.py detect \\")
        print(f"       models/pineapple_yolov8{args.size}_latest.pt test_image.jpg")
        print(f"  2. Upload images to AgriPinya web interface")
        print(f"  3. Monitor detection results")
        print(f"\n📊 Model saved to: models/pineapple_yolov8{args.size}_latest.pt")
    
    if not (args.setup or args.train or args.test or args.deploy or args.full):
        print_quick_commands()


if __name__ == '__main__':
    main()

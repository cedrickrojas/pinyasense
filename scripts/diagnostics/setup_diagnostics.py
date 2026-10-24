#!/usr/bin/env python3
"""
AgriPinya YOLOv8 - Setup & Diagnostics Script
Checks environment, installs dependencies, and validates setup
"""

import os
import sys
import subprocess
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]


def print_header(text):
    """Print formatted header"""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def print_status(status, message):
    """Print colored status message"""
    if status == 'ok':
        print(f"✅ {message}")
    elif status == 'error':
        print(f"❌ {message}")
    elif status == 'warning':
        print(f"⚠️  {message}")
    elif status == 'info':
        print(f"ℹ️  {message}")


def check_python_version():
    """Check Python version"""
    print_header("🐍 Python Version")
    
    version = sys.version_info
    print(f"Python {version.major}.{version.minor}.{version.micro}")
    
    if version.major >= 3 and version.minor >= 8:
        print_status('ok', f"Python version: {version.major}.{version.minor}")
        return True
    else:
        print_status('error', "Python 3.8+ required")
        return False


def check_cuda():
    """Check CUDA/GPU availability"""
    print_header("🖥️  GPU/CUDA Status")
    
    try:
        import torch
        if torch.cuda.is_available():
            print_status('ok', f"CUDA available: {torch.cuda.get_device_name(0)}")
            print_status('info', f"CUDA Version: {torch.version.cuda}")
            print_status('info', f"GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
            return True
        else:
            print_status('warning', "CUDA not available - will use CPU (slower)")
            return False
    except Exception as e:
        print_status('warning', f"Could not detect CUDA: {e}")
        return False


def check_dependencies():
    """Check if all required packages are installed"""
    print_header("📦 Dependencies Check")
    
    dependencies = {
        'torch': 'PyTorch',
        'torchvision': 'TorchVision',
        'tensorflow': 'TensorFlow',
        'cv2': 'OpenCV',
        'sklearn': 'scikit-learn',
        'numpy': 'NumPy',
        'PIL': 'Pillow',
        'flask': 'Flask',
        'yaml': 'PyYAML',
        'ultralytics': 'Ultralytics (YOLOv8)',
        'firebase_admin': 'Firebase Admin',
        'tqdm': 'tqdm'
    }
    
    missing = []
    installed = []
    
    for module, name in dependencies.items():
        try:
            __import__(module)
            print_status('ok', name)
            installed.append(name)
        except ImportError:
            print_status('error', name)
            missing.append(module)
    
    return missing, installed


def check_directory_structure():
    """Check AgriPinya directory structure"""
    print_header("📁 Directory Structure")
    
    required_dirs = [
        'models',
        'static',
        'templates',
        'uploads',
        'results',
        'sensor_data'
    ]
    
    all_exist = True
    for dir_name in required_dirs:
        dir_path = APP_ROOT / dir_name
        if dir_path.exists():
            print_status('ok', f"Directory: {dir_name}/")
        else:
            print_status('warning', f"Directory missing: {dir_name}/")
            all_exist = False
    
    return all_exist


def check_yolov8_tools():
    """Check if YOLOv8 tools are available"""
    print_header("🛠️  YOLOv8 Tools")
    
    tools = {
        'scripts/training/train_yolov8.py': 'YOLOv8 Training Script',
        'scripts/diagnostics/test_yolov8_inference.py': 'YOLOv8 Testing Script',
        'scripts/training/prepare_yolov8_dataset.py': 'Dataset Preparation',
        'scripts/training/yolov8_quickstart.py': 'Quick Start Automation',
        'README.md': 'Application Documentation',
        'scripts/README.md': 'Script Commands and Safety Notes',
        'models/README.txt': 'Model Documentation'
    }
    
    all_exist = True
    for filename, description in tools.items():
        if (APP_ROOT / filename).exists():
            print_status('ok', description)
        else:
            print_status('warning', f"Missing: {description}")
            all_exist = False
    
    return all_exist


def check_app_structure():
    """Check Flask app structure"""
    print_header("🌐 Flask App Structure")
    
    app_files = {
        'app.py': 'Main Flask application',
        'core/disease_detector.py': 'Disease detection engine',
        'core/config.py': 'Configuration',
        'core/auth.py': 'Authentication'
    }
    
    templates = {
        'templates/index.html': 'Dashboard',
        'templates/diseases.html': 'Diseases page',
        'templates/sensors.html': 'Sensors page',
        'templates/soil_moisture.html': 'Soil moisture'
    }
    
    all_exist = True
    
    print("\nApplication files:")
    for file, desc in app_files.items():
        if (APP_ROOT / file).exists():
            print_status('ok', f"{desc}")
        else:
            print_status('warning', f"Missing: {desc}")
            all_exist = False
    
    print("\nTemplates:")
    for file, desc in templates.items():
        if (APP_ROOT / file).exists():
            print_status('ok', f"{desc}")
        else:
            print_status('warning', f"Missing: {desc}")
            all_exist = False
    
    return all_exist


def available_models():
    """Check available trained models"""
    print_header("🤖 Trained Models")
    
    models_dir = APP_ROOT / 'models'
    if not models_dir.exists():
        print_status('warning', "models/ directory not found")
        return 0
    
    yolo_models = list(models_dir.glob('pineapple_yolov8*.pt'))
    keras_models = list(models_dir.glob('*.keras')) + list(models_dir.glob('*.h5'))
    
    if yolo_models:
        print_status('ok', f"YOLOv8 models: {len(yolo_models)}")
        for model in yolo_models:
            size_mb = model.stat().st_size / 1e6
            print(f"     - {model.name} ({size_mb:.1f} MB)")
    else:
        print_status('info', "No YOLOv8 models found yet")
    
    if keras_models:
        print_status('ok', f"PyTorch/Keras models: {len(keras_models)}")
        for model in keras_models[:3]:  # Show first 3
            size_mb = model.stat().st_size / 1e6
            print(f"     - {model.name} ({size_mb:.1f} MB)")
    
    return len(yolo_models)


def print_next_steps(missing_deps, has_yolo_models):
    """Print next steps based on diagnostics"""
    print_header("📋 Next Steps")
    
    if missing_deps:
        print("1️⃣  Install missing dependencies:")
        print(f"     pip install {' '.join(missing_deps)}")
    else:
        print("1️⃣  ✅ All dependencies installed")
    
    if has_yolo_models == 0:
        print("\n2️⃣  Train YOLOv8 model:")
        print("     # Quick setup")
        print("     python -m scripts.training.yolov8_quickstart --setup /path/to/dataset")
        print("     python -m scripts.training.yolov8_quickstart --train data.yaml")
        print("\n     OR use full workflow:")
        print("     python -m scripts.training.yolov8_quickstart --full /path/to/dataset")
    else:
        print(f"\n2️⃣  ✅ {has_yolo_models} YOLOv8 model(s) available")
        print("     Test model:")
        print("     python -m scripts.diagnostics.test_yolov8_inference detect models/pineapple_yolov8s_latest.pt test_image.jpg")
    
    print("\n3️⃣  Run AgriPinya:")
    print("     python app.py")
    print("     Open: http://localhost:5000")
    
    print("\n4️⃣  Reference guides:")
    print("     📘 YOLOV8_WORKFLOW_GUIDE.md - Complete guide")
    print("     📗 YOLOV8_TOOLS_README.md - Tool documentation")
    print("     📕 YOLOV8_QUICK_REFERENCE.md - Quick commands")


def main():
    """Run all diagnostics"""
    banner = """
╔═════════════════════════════════════════════════════════╗
║  🍍 AgriPinya YOLOv8 - Setup & Diagnostics 🍍         ║
║                                                          ║
║    Checking system setup and dependencies               ║
╚═════════════════════════════════════════════════════════╝
"""
    print(banner)
    
    # Run checks
    python_ok = check_python_version()
    cuda_available = check_cuda()
    missing_deps, installed = check_dependencies()
    dirs_ok = check_directory_structure()
    tools_ok = check_yolov8_tools()
    app_ok = check_app_structure()
    num_models = available_models()
    
    # Summary
    print_header("📊 Summary")
    
    checks = [
        ("Python 3.8+", python_ok),
        ("All directories", dirs_ok),
        ("YOLOv8 tools", tools_ok),
        ("Flask app", app_ok)
    ]
    
    passed = sum(1 for _, result in checks if result)
    total = len(checks)
    
    print(f"Checks passed: {passed}/{total}\n")
    
    for check_name, result in checks:
        if result:
            print_status('ok', check_name)
        else:
            print_status('error', check_name)
    
    if missing_deps:
        print(f"\nMissing packages ({len(missing_deps)}):")
        for dep in missing_deps:
            print(f"  - {dep}")
    
    if cuda_available:
        print_status('info', "GPU acceleration available ⚡")
    else:
        print_status('warning', "Using CPU only (download CUDA for speedup)")
    
    # Next steps
    print_next_steps(missing_deps, num_models)
    
    print("\n")
    
    # Return status code
    if missing_deps or not all(ok for _, ok in checks):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

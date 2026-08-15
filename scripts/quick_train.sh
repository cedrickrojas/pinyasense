#!/bin/bash
# Quick Training Starter - Run as soon as dataset arrives
# Usage: ./quick_train.sh /path/to/dataset

set -e

echo "╔═════════════════════════════════════════════════════════╗"
echo "║     🍍 AgriPinya - Quick Training Script 🍍            ║"
echo "╚═════════════════════════════════════════════════════════╝"
echo ""

DATASET_PATH="${1:-dataset_raw}"

if [ ! -d "$DATASET_PATH" ]; then
    echo "❌ Dataset not found: $DATASET_PATH"
    echo ""
    echo "📥 FAST TRANSFER OPTIONS:"
    echo ""
    echo "Option 1 - Using VSCode (EASIEST):"
    echo "  1. Open folder: C:\Users\Cedrick\Downloads\archive (1)"
    echo "  2. Drag & drop to Linux VSCode workspace"
    echo "  3. Rename to: dataset_raw"
    echo ""
    echo "Option 2 - Using SCP:"
    echo "  scp -r \"C:\Users\Cedrick\Downloads\archive (1)\" user@host:/home/voicebrain/agripinya/dataset_raw"
    echo ""
    echo "Option 3 - Manual:"
    echo "  1. Zip the archive folder on Windows"
    echo "  2. Upload via any method"
    echo "  3. Unzip on Linux: unzip archive.zip -d dataset_raw"
    echo ""
    exit 1
fi

echo "✅ Dataset found: $DATASET_PATH"
echo ""

# Activate virtual environment
if [ -f "venv/bin/activate" ]; then
    echo "🐍 Activating virtual environment..."
    source venv/bin/activate
fi

# Check dependencies
echo "📦 Checking dependencies..."
python -c "import torch; import ultralytics; print('✅ All packages ready')" 2>/dev/null || {
    echo "⚠️  Installing required packages..."
    pip install ultralytics torch torchvision opencv-python pyyaml numpy -q
}

echo ""
echo "🚀 Starting complete training pipeline..."
echo ""

# Run training
python scripts/train_complete.py "$DATASET_PATH" --size s --epochs 100 --batch-size 16

echo ""
echo "🎉 Training complete!"
echo ""
echo "🧪 Test your model:"
echo "  python scripts/test_yolov8_inference.py detect models/pineapple_yolov8s_latest.pt test_image.jpg"
echo ""
echo "🌐 Use in AgriPinya:"
echo "  python app.py"
echo "  Open: http://localhost:5000"
echo ""
echo "📚 Docs:"
echo "  cat docs/README.md"
echo "  cat docs/YOLOV8_GETTING_STARTED.md"
echo "  cat scripts/README.md"
echo ""

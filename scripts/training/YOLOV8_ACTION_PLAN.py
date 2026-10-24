#!/usr/bin/env python3
"""
AgriPinya YOLOv8 - Quick Checklist & Action Plan
Print this and check off as you go!
"""

import sys
from datetime import datetime

def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def print_section(num, title, subtitle=""):
    print(f"\n{'─'*60}")
    print(f"  {num}. {title}")
    if subtitle:
        print(f"     {subtitle}")
    print(f"{'─'*60}\n")

def main():
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║     🍍 AgriPinya YOLOv8 - Action Plan & Checklist 🍍    ║
║                                                            ║
║       Complete this guide to train your first model        ║
║                                                            ║
║       Date: {datetime.now().strftime('%Y-%m-%d %H:%M')} │
╚═══════════════════════════════════════════════════════════╝
""")

    print(f"""
✅ CHECKLIST - Print This & Check Off As You Go!
{'─'*60}

PHASE 1: PREPARE (5 minutes)
────────────────────────────
☐ Step 1.1: Have your dataset ready
            Path: /path/to/Pineapple-Disease.v1i.yolov8
            
☐ Step 1.2: Verify Python installation
            Command: python --version
            Expected: Python 3.8 or higher
            
☐ Step 1.3: Install dependencies
            Command: pip install -r requirements.txt
            

PHASE 2: VERIFY (5 minutes)  
────────────────────────────
☐ Step 2.1: Run system diagnostics
            Command: python -m scripts.diagnostics.setup_diagnostics
            Expected: All green ✅ checks
            
☐ Step 2.2: Check for missing packages
            Look for: Red ❌ marks in output
            If found: Install using pip install <package>


PHASE 3: SETUP DATASET (5 minutes)
──────────────────────────────────
☐ Step 3.1: Prepare dataset
            Command: python -m scripts.training.yolov8_quickstart --setup /path/to/dataset
            Time: 2-3 minutes
            
☐ Step 3.2: Verify setup
            Command: ls -la dataset_yolov8/
            Check: Should have data.yaml, train/, val/, test/


PHASE 4: TRAIN MODEL (1-2 hours)
────────────────────────────────
☐ Step 4.1: Start training
            Command: python -m scripts.training.yolov8_quickstart --train data.yaml
            Time: 30-120 minutes (depends on GPU)
            
☐ Step 4.2: Monitor training
            Watch for:
            - ✅ Losses decreasing
            - ✅ No GPU memory errors
            - ✅ Validation improving
            
☐ Step 4.3: Training complete
            Check: models/pineapple_yolov8s_latest.pt exists
            Size: Should be ~25 MB


PHASE 5: TEST MODEL (5 minutes)
───────────────────────────────
☐ Step 5.1: Test on single image
            Command: python -m scripts.diagnostics.test_yolov8_inference detect \\
                    models/pineapple_yolov8s_latest.pt test_image.jpg
            Expected: Shows detected diseases with confidence
            
☐ Step 5.2: Visualize results
            Command: python -m scripts.diagnostics.test_yolov8_inference visualize \\
                    models/pineapple_yolov8s_latest.pt test_image.jpg \\
                    --output result.jpg
            Expected: Saves image with bounding boxes


PHASE 6: DEPLOY (1 minute)
──────────────────────────
☐ Step 6.1: Verify model location
            Command: ls -lh models/pineapple_yolov8s_latest.pt
            Expected: File exists and is ~25 MB
            
☐ Step 6.2: Start AgriPinya
            Command: python app.py
            Expected: Server runs on http://localhost:5000
            
☐ Step 6.3: Use in web interface
            Action: Open browser to http://localhost:5000
            Upload: Test image
            Result: Automatic detection using YOLOv8 ✅


PHASE 7: MONITOR (Ongoing)
──────────────────────────
☐ Step 7.1: Check detection quality
            Action: Upload various farm images
            Monitor: Accuracy and response time
            
☐ Step 7.2: Make notes
            Record: Which diseases are detected well
            Record: Any false positives to address
            
☐ Step 7.3: Plan improvements
            Options: More training data, longer epochs, larger model


SUCCESS CRITERIA - All Should Be ✓
──────────────────────────────────
✓ Model trained and saved
✓ Detection works on test images
✓ AgriPinya runs without errors
✓ Web interface shows results
✓ Model detects 2+ disease types
✓ Confidence scores are shown


QUICK REFERENCE
───────────────
Troubleshooting:
  Out of memory? → Reduce --batch-size to 8
  Slow training? → Use --model-size n instead of s
  Poor accuracy? → Increase --epochs to 200
  Dataset issue? → Run python -m scripts.diagnostics.setup_diagnostics

Documentation:
  Getting started? → Read YOLOV8_GETTING_STARTED.md
  Need commands? → See YOLOV8_QUICK_REFERENCE.md
  Want deep dive? → Read YOLOV8_WORKFLOW_GUIDE.md
  Tools details? → Check YOLOV8_TOOLS_README.md

Commands Summary:
  Check system:     python -m scripts.diagnostics.setup_diagnostics
  Setup dataset:    python -m scripts.training.yolov8_quickstart --setup /path
  Train model:      python -m scripts.training.yolov8_quickstart --train data.yaml
  Test detection:   python -m scripts.diagnostics.test_yolov8_inference detect model.pt image.jpg
  Start app:        python app.py


TIME ESTIMATE
─────────────
Prepare:    5 minutes  ⏱️
Verify:     5 minutes  ⏱️
Dataset:    5 minutes  ⏱️
Training:  60 minutes  ⏱️ (GPU) or 2-3 hours (CPU)
Test:       5 minutes  ⏱️
Deploy:     1 minute   ⏱️
──────────────────────
TOTAL:    ≈1.5 hours   🎉


NEXT STEPS
──────────
1. Print this checklist
2. Get your dataset ready
3. Start Phase 1: python -m scripts.diagnostics.setup_diagnostics
4. Follow each phase in order
5. Celebrate when complete! 🎉


NEED HELP?
──────────
Error → Check YOLOV8_WORKFLOW_GUIDE.md troubleshooting section
Questions → Read YOLOV8_GETTING_STARTED.md
Commands → See YOLOV8_QUICK_REFERENCE.md
Deep dive → Check YOLOV8_TOOLS_README.md


═══════════════════════════════════════════════════════════
                    YOU GOT THIS! 💪
═══════════════════════════════════════════════════════════

Start now:
  python -m scripts.diagnostics.setup_diagnostics

Happy farming with AI-powered disease detection! 🌾🍍
""")

    # Save to file
    try:
        with open('YOLOV8_ACTION_PLAN.txt', 'w') as f:
            f.write(f"""
╔═══════════════════════════════════════════════════════════╗
║     🍍 AgriPinya YOLOv8 - Action Plan & Checklist 🍍    ║
║                                                            ║
║       Complete this guide to train your first model        ║
║                                                            ║
║       Date: {datetime.now().strftime('%Y-%m-%d %H:%M')} │
╚═══════════════════════════════════════════════════════════╝

PHASE 1: PREPARE (5 minutes)
☐ Have dataset ready: /path/to/Pineapple-Disease.v1i.yolov8
☐ Verify Python: python --version (need 3.8+)
☐ Install dependencies: pip install -r requirements.txt

PHASE 2: VERIFY (5 minutes)
☐ Run diagnostics: python -m scripts.diagnostics.setup_diagnostics
☐ Check all green ✅ marks
☐ Fix any red ❌ issues

PHASE 3: SETUP DATASET (5 minutes)
☐ Prepare: python -m scripts.training.yolov8_quickstart --setup /path/to/dataset
☐ Verify: ls -la dataset_yolov8/
☐ Check: data.yaml, train/, val/, test/ exist

PHASE 4: TRAIN MODEL (1-2 hours)
☐ Train: python -m scripts.training.yolov8_quickstart --train data.yaml
☐ Monitor: Watch losses decrease
☐ Wait: 30-120 min depending on GPU

PHASE 5: TEST MODEL (5 minutes)
☐ Test single: python -m scripts.diagnostics.test_yolov8_inference detect models/pineapple_yolov8s_latest.pt image.jpg
☐ Visualize: python -m scripts.diagnostics.test_yolov8_inference visualize models/pineapple_yolov8s_latest.pt image.jpg
☐ Check: Output shows detected diseases

PHASE 6: DEPLOY (1 minute)
☐ Verify model: ls models/pineapple_yolov8s_latest.pt
☐ Start app: python app.py
☐ Open: http://localhost:5000
☐ Test: Upload image and verify detection

SUCCESS CHECKLIST
✓ Model trained and saved
✓ Detection works on test images
✓ AgriPinya runs
✓ Web interface works
✓ Model detects diseases

TROUBLESHOOTING QUICK FIXES
Out of memory → python -m scripts.training.yolov8_quickstart --train data.yaml --batch-size 8
Slow → Use --model-size n instead of s
Poor accuracy → Increase --epochs to 200
Questions → Read YOLOV8_GETTING_STARTED.md

TIME ESTIMATE: ~1.5 hours total (including training)

═══════════════════════════════════════════════════════════
START: python -m scripts.diagnostics.setup_diagnostics
═══════════════════════════════════════════════════════════
""")
        print("\n📄 Checklist saved to: YOLOV8_ACTION_PLAN.txt")
        print("   (You can print this file for reference!)\n")
    except Exception as e:
        print(f"Warning: Could not save checklist: {e}\n")


if __name__ == '__main__':
    main()

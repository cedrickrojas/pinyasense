#!/usr/bin/env python3
"""
Dataset Converter - Convert various formats to YOLOv8 format
Handles Roboflow, CVAT, and custom dataset formats
"""

import os
import sys
import shutil
import argparse
from pathlib import Path
import json


# Canonical 5-class taxonomy used by AgriPinya.
CANONICAL_CLASSES = {
    0: 'CrownRot',
    1: 'FruitRot',
    2: 'MealybugWilt',
    3: 'RootRot',
    4: 'Healthy'
}

# Legacy 6-class YOLO datasets can be merged into the 5-class taxonomy.
LEGACY_6_TO_5_CLASS_ID_MAP = {
    0: 0,  # CrownRot -> CrownRot
    1: 1,  # FruitFasciation -> FruitRot
    2: 1,  # FruitRot -> FruitRot
    3: 2,  # MealybugWilt -> MealybugWilt
    4: 3,  # MultipleCrown -> RootRot bucket
    5: 4   # Healthy -> Healthy
}


def setup_yolov8_directory_structure(output_dir):
    """Create proper YOLOv8 directory structure"""
    print("\n📁 Creating YOLOv8 directory structure...")
    
    dirs = [
        'train/images',
        'train/labels',
        'val/images',
        'val/labels',
        'test/images',
        'test/labels'
    ]
    
    for dir_name in dirs:
        dir_path = Path(output_dir) / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"   ✅ Created: {dir_name}")
    
    return Path(output_dir)


def convert_dataset(input_dir, output_dir='dataset_yolov8'):
    """
    Convert dataset from various formats to YOLOv8 format
    
    Handles:
    - Roboflow format (obj_train_data, obj_test_data)
    - Custom format with train/ and test/ directories
    """
    print(f"\n🔄 Converting dataset...")
    print(f"   Input: {input_dir}")
    print(f"   Output: {output_dir}")
    
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    # Create structure
    setup_yolov8_directory_structure(output_path)
    
    # Handle different dataset formats
    if (input_path / 'obj_train_data').exists():
        print("\n📊 Detected Roboflow format...")
        convert_roboflow(input_path, output_path)
    
    elif (input_path / 'train').exists() and (input_path / 'test').exists():
        print("\n📊 Detected custom format (train/test)...")
        convert_custom_format(input_path, output_path)
    
    elif (input_path / 'train' / 'obj').exists():
        print("\n📊 Detected custom format with obj/ structure...")
        convert_custom_obj_format(input_path, output_path)
    
    else:
        print("❌ Unknown dataset format")
        print("\n   Expected one of:")
        print("   - obj_train_data/ and obj_test_data/ (Roboflow)")
        print("   - train/ and test/ directories")
        return False
    
    return True


def convert_roboflow(input_path, output_path):
    """Convert Roboflow format to YOLOv8"""
    print("\n   Converting training data...")
    
    train_src = input_path / 'obj_train_data'
    val_src = input_path / 'obj_val_data' if (input_path / 'obj_val_data').exists() else None
    test_src = input_path / 'obj_test_data'
    
    # Copy training data
    copy_images_and_labels(train_src, output_path / 'train', 'train')
    
    # Copy validation (or split from training)
    if val_src:
        copy_images_and_labels(val_src, output_path / 'val', 'val')
    else:
        print("   ⚠️  No validation data found")
    
    # Copy test data
    copy_images_and_labels(test_src, output_path / 'test', 'test')


def convert_custom_format(input_path, output_path):
    """Convert custom format (train/ and test/) to YOLOv8"""
    print("\n   Converting training data...")
    
    train_src = input_path / 'train'
    test_src = input_path / 'test'
    
    copy_images_and_labels(train_src, output_path / 'train', 'train')
    copy_images_and_labels(test_src, output_path / 'test', 'test')


def convert_custom_obj_format(input_path, output_path):
    """Convert custom format with obj/ structure to YOLOv8"""
    print("\n   Converting training data...")
    
    train_src = input_path / 'train' / 'obj'
    test_src = input_path / 'test' / 'test'
    
    if train_src.exists():
        copy_images_and_labels(train_src, output_path / 'train', 'train')
    
    if test_src.exists():
        copy_images_and_labels(test_src, output_path / 'test', 'test')


def remap_legacy_label_line(line):
    """Remap one YOLO label line from legacy 6-class IDs to canonical 5-class IDs."""
    stripped = line.strip()
    if not stripped:
        return line

    parts = stripped.split()
    if not parts:
        return line

    try:
        cls_id = int(parts[0])
    except ValueError:
        return line

    if cls_id in LEGACY_6_TO_5_CLASS_ID_MAP:
        parts[0] = str(LEGACY_6_TO_5_CLASS_ID_MAP[cls_id])
        return " ".join(parts) + "\n"

    return line


def remap_label_file_if_needed(src_file, dst_file):
    """Copy label file and remap class IDs when legacy 6-class IDs are present."""
    with open(src_file, 'r') as f:
        lines = f.readlines()

    class_ids = []
    for line in lines:
        tokens = line.strip().split()
        if not tokens:
            continue
        try:
            class_ids.append(int(tokens[0]))
        except ValueError:
            continue

    needs_remap = any(cls_id >= 5 for cls_id in class_ids)
    output_lines = [remap_legacy_label_line(line) for line in lines] if needs_remap else lines

    with open(dst_file, 'w') as f:
        f.writelines(output_lines)

    return needs_remap


def copy_images_and_labels(src_dir, dst_dir, split_name):
    """Copy images and labels from source to destination"""
    src_path = Path(src_dir)
    images_dst = Path(dst_dir) / 'images'
    labels_dst = Path(dst_dir) / 'labels'
    
    images_dst.mkdir(parents=True, exist_ok=True)
    labels_dst.mkdir(parents=True, exist_ok=True)
    
    if not src_path.exists():
        print(f"   ⚠️  Source dir not found: {src_path}")
        return
    
    # Copy image files
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.JPG', '.JPEG', '.PNG', '.BMP']
    txt_files = []
    image_files = []
    
    for ext in image_extensions:
        image_files.extend(src_path.glob(f'*{ext}'))
    
    # Copy labels (.txt files)
    txt_files = list(src_path.glob('*.txt'))
    
    copied_images = 0
    copied_labels = 0
    
    for img_file in image_files:
        try:
            shutil.copy2(img_file, images_dst / img_file.name)
            copied_images += 1
        except Exception as e:
            print(f"   ⚠️  Error copying {img_file.name}: {e}")
    
    remapped_files = 0
    for txt_file in txt_files:
        try:
            target_label_path = labels_dst / txt_file.name
            was_remapped = remap_label_file_if_needed(txt_file, target_label_path)
            if was_remapped:
                remapped_files += 1
            copied_labels += 1
        except Exception as e:
            print(f"   ⚠️  Error copying {txt_file.name}: {e}")
    
    print(f"   ✅ {split_name}: {copied_images} images, {copied_labels} labels")
    if remapped_files:
        print(f"      ↪️  Remapped {remapped_files} legacy label files to 5 classes")


def detect_classes(dataset_path):
    """Detect classes from label files"""
    print("\n🔍 Detecting classes...")
    
    classes = set()
    labels_dir = Path(dataset_path) / 'train' / 'labels'
    
    if not labels_dir.exists():
        print("   ⚠️  Labels directory not found")
        return None
    
    # Read label files to find class IDs
    for label_file in labels_dir.glob('*.txt'):
        try:
            with open(label_file, 'r') as f:
                for line in f:
                    if line.strip():
                        class_id = int(line.split()[0])
                        classes.add(class_id)
        except Exception as e:
            print(f"   ⚠️  Error reading {label_file.name}: {e}")
    
    if classes:
        print(f"   ✅ Found {len(classes)} classes: {sorted(classes)}")
        return sorted(classes)
    
    return None


def create_data_yaml(dataset_path, class_count=None):
    """Create data.yaml for YOLOv8"""
    print("\n📋 Creating data.yaml...")
    
    dataset_abs_path = Path(dataset_path).absolute()
    
    # Canonical classes for pineapple disease (5-class)
    default_classes = CANONICAL_CLASSES
    
    # Detect classes, or use provided count
    if class_count:
        classes = default_classes
    else:
        detected_classes = detect_classes(dataset_path)
        if detected_classes:
            # Build class dict from detected IDs
            classes = {}
            for idx, class_id in enumerate(detected_classes):
                if class_id in default_classes:
                    classes[class_id] = default_classes[class_id]
                else:
                    classes[class_id] = f'class_{class_id}'
        else:
            classes = default_classes
    
    yaml_content = f"""# YOLOv8 Pineapple Disease Dataset
path: {dataset_abs_path}
train: train/images
val: val/images
test: test/images

# Number of classes
nc: {len(classes)}

# Class names
names:
"""
    
    for idx in sorted(classes.keys()):
        yaml_content += f"  {idx}: {classes[idx]}\n"
    
    yaml_path = Path(dataset_path) / 'data.yaml'
    with open(yaml_path, 'w') as f:
        f.write(yaml_content)
    
    print(f"   ✅ Created: data.yaml")
    print(f"      Classes: {len(classes)}")
    print(f"      Path: {yaml_path}")
    
    return yaml_path


def validate_dataset(dataset_path):
    """Validate YOLOv8 dataset structure"""
    print("\n✅ Validating dataset...")
    
    dataset_path = Path(dataset_path)
    required = ['data.yaml', 'train/images', 'train/labels']
    optional = ['val/images', 'val/labels', 'test/images', 'test/labels']
    
    all_valid = True
    
    # Check required
    for item in required:
        item_path = dataset_path / item
        if item_path.exists():
            count = len(list(item_path.glob('*')))
            print(f"   ✅ {item}: {count} files")
        else:
            print(f"   ❌ {item}: NOT FOUND")
            all_valid = False
    
    # Check optional
    for item in optional:
        item_path = dataset_path / item
        if item_path.exists():
            count = len(list(item_path.glob('*')))
            print(f"   ℹ️  {item}: {count} files")
    
    return all_valid


def main():
    parser = argparse.ArgumentParser(
        description='Convert dataset to YOLOv8 format'
    )
    parser.add_argument(
        'input_dir',
        help='Input dataset directory'
    )
    parser.add_argument(
        '--output',
        default='dataset_yolov8',
        help='Output directory (default: dataset_yolov8)'
    )
    parser.add_argument(
        '--validate',
        action='store_true',
        help='Validate dataset only'
    )
    
    args = parser.parse_args()
    
    print("""
╔═════════════════════════════════════════════════════════╗
║        Dataset Converter - YOLO Format                 ║
╚═════════════════════════════════════════════════════════╝
""")
    
    if args.validate:
        validate_dataset(args.input_dir)
        return
    
    # Convert dataset
    if not convert_dataset(args.input_dir, args.output):
        sys.exit(1)
    
    # Create data.yaml
    output_path = Path(args.output)
    create_data_yaml(output_path)
    
    # Validate
    if validate_dataset(output_path):
        print("\n🎉 Dataset conversion successful!")
        print(f"\n📊 Ready to train!")
        print(f"\nNext step:")
        print(f"  python yolov8_quickstart.py --train {args.output}/data.yaml")
    else:
        print("\n⚠️  Dataset validation warnings - may still work")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
YOLOv8 Pineapple Disease Detection Inference Script
Test trained YOLOv8 models on images
"""

import argparse
import json
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime


def load_yolov8_model(model_path):
    """Load YOLOv8 model"""
    try:
        from ultralytics import YOLO
        print(f"📦 Loading YOLOv8 model: {model_path}")
        model = YOLO(model_path)
        print(f"✅ Model loaded successfully")
        return model
    except Exception as e:
        print(f"❌ Error loading model: {e}")
        return None


def detect_diseases(model, image_path, conf_threshold=0.5):
    """
    Run disease detection on image
    
    Args:
        model: YOLOv8 model
        image_path: Path to image
        conf_threshold: Confidence threshold (0-1)
    
    Returns:
        Detection results
    """
    print(f"\n🖼️  Detecting diseases in: {image_path}")
    
    try:
        # Run inference
        results = model.predict(
            image_path,
            conf=conf_threshold,
            verbose=False,
            device=0  # GPU if available, else CPU
        )
        
        # Parse results
        detections = []
        for r in results:
            if r.boxes is None or len(r.boxes) == 0:
                print("   ⚠️  No diseases detected")
                continue
            
            for box in r.boxes:
                class_id = int(box.cls.item())
                confidence = float(box.conf.item())
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                
                detection = {
                    'class_id': class_id,
                    'class_name': r.names[class_id],
                    'confidence': confidence,
                    'bbox': {
                        'x1': x1,
                        'y1': y1,
                        'x2': x2,
                        'y2': y2,
                        'width': x2 - x1,
                        'height': y2 - y1
                    }
                }
                detections.append(detection)
                
                print(f"   ✅ {detection['class_name']}: {confidence:.2%}")
        
        if detections:
            # Aggregate by disease
            disease_counts = {}
            for det in detections:
                disease = det['class_name']
                disease_counts[disease] = disease_counts.get(disease, 0) + 1
            
            print(f"\n📊 Summary:")
            for disease, count in disease_counts.items():
                print(f"   - {disease}: {count} region(s)")
        
        return detections, results
        
    except Exception as e:
        print(f"❌ Detection error: {e}")
        return None, None


def visualize_detections(model, image_path, output_path=None, conf_threshold=0.5):
    """
    Visualize detections on image
    
    Args:
        model: YOLOv8 model
        image_path: Path to image
        output_path: Path to save annotated image
        conf_threshold: Confidence threshold
    """
    print(f"\n🎨 Visualizing detections...")
    
    try:
        # Run inference
        results = model.predict(
            image_path,
            conf=conf_threshold,
            verbose=False,
            device=0
        )
        
        # Draw results
        for r in results:
            im_array = r.plot()
            
            # Save annotated image
            if output_path is None:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                output_path = f"detection_result_{timestamp}.jpg"
            
            cv2.imwrite(output_path, im_array)
            print(f"✅ Saved annotated image: {output_path}")
            
            return output_path
        
    except Exception as e:
        print(f"❌ Visualization error: {e}")
        return None


def batch_detect(model, image_dir, conf_threshold=0.5, output_json=None):
    """
    Run detection on multiple images
    
    Args:
        model: YOLOv8 model
        image_dir: Directory containing images
        conf_threshold: Confidence threshold
        output_json: Path to save results JSON
    """
    print(f"\n📁 Batch detection on: {image_dir}")
    
    image_dir = Path(image_dir)
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp']
    
    images = []
    for ext in image_extensions:
        images.extend(image_dir.glob(f'*{ext}'))
        images.extend(image_dir.glob(f'*{ext.upper()}'))
    
    if not images:
        print(f"❌ No images found in {image_dir}")
        return
    
    print(f"📊 Found {len(images)} images")
    
    results_list = []
    for i, image_path in enumerate(images, 1):
        print(f"\n[{i}/{len(images)}] Processing: {image_path.name}")
        detections, _ = detect_diseases(model, str(image_path), conf_threshold)
        
        if detections:
            results_list.append({
                'image': str(image_path),
                'detections': detections
            })
    
    # Save results
    if output_json and results_list:
        output_path = Path(output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(results_list, f, indent=2)
        
        print(f"\n✅ Results saved: {output_path}")
        print(f"   Total detections: {sum(len(r['detections']) for r in results_list)}")


def compare_models(image_path, model1_path, model2_path, conf_threshold=0.5):
    """
    Compare two YOLOv8 models on same image
    
    Args:
        image_path: Path to test image
        model1_path: Path to first model
        model2_path: Path to second model
        conf_threshold: Confidence threshold
    """
    print(f"\n⚖️  Comparing models on: {image_path}")
    
    model1 = load_yolov8_model(model1_path)
    model2 = load_yolov8_model(model2_path)
    
    if not model1 or not model2:
        print("❌ Could not load models")
        return
    
    print("\n📊 Model 1 Results:")
    det1, _ = detect_diseases(model1, image_path, conf_threshold)
    
    print("\n📊 Model 2 Results:")
    det2, _ = detect_diseases(model2, image_path, conf_threshold)
    
    print("\n📈 Comparison:")
    print(f"   Model 1 detections: {len(det1) if det1 else 0}")
    print(f"   Model 2 detections: {len(det2) if det2 else 0}")


def print_model_info(model_path):
    """Print model information"""
    try:
        from ultralytics import YOLO
        model = YOLO(model_path)
        
        print(f"\n📋 Model Information")
        print(f"{'='*50}")
        print(f"Model: {model_path}")
        print(f"Classes: {model.names}")
        print(f"Num classes: {model.nc}")
        print(f"Input size: 640x640")
        print(f"Framework: YOLOv8")
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


def main():
    """Main script"""
    parser = argparse.ArgumentParser(
        description='YOLOv8 Pineapple Disease Detection'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Detect command
    detect_parser = subparsers.add_parser(
        'detect',
        help='Detect diseases in image(s)'
    )
    detect_parser.add_argument(
        'model',
        help='YOLOv8 model path'
    )
    detect_parser.add_argument(
        'image',
        help='Image or directory'
    )
    detect_parser.add_argument(
        '--conf',
        type=float,
        default=0.5,
        help='Confidence threshold (default: 0.5)'
    )
    detect_parser.add_argument(
        '--output',
        help='Output JSON file for batch'
    )
    
    # Visualize command
    viz_parser = subparsers.add_parser(
        'visualize',
        help='Visualize detections on image'
    )
    viz_parser.add_argument(
        'model',
        help='YOLOv8 model path'
    )
    viz_parser.add_argument(
        'image',
        help='Image path'
    )
    viz_parser.add_argument(
        '--output',
        help='Output image path'
    )
    viz_parser.add_argument(
        '--conf',
        type=float,
        default=0.5,
        help='Confidence threshold'
    )
    
    # Info command
    info_parser = subparsers.add_parser(
        'info',
        help='Print model information'
    )
    info_parser.add_argument(
        'model',
        help='YOLOv8 model path'
    )
    
    args = parser.parse_args()
    
    if args.command == 'detect':
        model = load_yolov8_model(args.model)
        if model:
            image_path = Path(args.image)
            if image_path.is_file():
                detect_diseases(model, str(image_path), args.conf)
            elif image_path.is_dir():
                batch_detect(model, str(image_path), args.conf, args.output)
            else:
                print(f"❌ Path not found: {image_path}")
    
    elif args.command == 'visualize':
        model = load_yolov8_model(args.model)
        if model:
            visualize_detections(model, args.image, args.output, args.conf)
    
    elif args.command == 'info':
        print_model_info(args.model)
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()

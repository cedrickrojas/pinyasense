import cv2
import numpy as np
import os
import json
from datetime import datetime

class PineappleDiseaseDetector:
    """
    Pineapple Disease Detector using image processing and ML
    Detects common pineapple diseases from leaf and fruit images
    """
    
    def __init__(self, model_path=None):
        """Initialize detector with optional model path"""
        # Try different model paths in order of preference
        possible_paths = [
            model_path,
            'models/pineapple_yolov8n_latest.pt',  # YOLOv8 nano
            'models/pineapple_disease_model_final.keras',
            'models/pineapple_disease_model.h5',
            'models/pineapple_disease_model_improved.h5',
            'models/pineapple_disease_model.pt'
        ]
        
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        possible_paths = [path if os.path.isabs(path) else os.path.join(project_root, path)
                          for path in possible_paths if path]
        self.model_path = None
        for path in possible_paths:
            if path and os.path.exists(path):
                self.model_path = path
                break
        
        self.model = None
        self.model_type = None  # 'keras', 'pytorch', or 'yolov8'
        self.scene_model = None
        self.num_classes = None
        self.metadata = None
        self.metadata_path = None
        # Full disease list (for 5-class models)
        self.diseases_5 = [
            'Heart Rot',
            'Fruit Rot',
            'Yellow Spot',
            'Pink Disease',
            'Healthy'
        ]
        # Simplified disease list (for 3-class models)
        self.diseases_3 = [
            'Diseased',
            'Possibly Diseased',
            'Healthy'
        ]
        # YOLOv8 classes mapping
        self.yolov8_disease_map = {
            'CrownRot': 'Crown Rot',
            'FruitFasciation': 'Fruit Fasciation Disorder',
            'FruitRot': 'Fruit Rot',
            'MealybugWilt': 'Mealybug Wilt',
            'RootRot': 'Root Rot',
            'MultipleCrown': 'Multiple Crown Disorder',
            'Healthy': 'Healthy',
            'Heart_Rot_Disease': 'Heart Rot',
            'Fruit_Rot_Disease': 'Fruit Rot',
            'Yellow_Spot_Disease': 'Yellow Spot',
            'Pink_Disease': 'Pink Disease',
            'Fruit_Fasciation_Disorder': 'Fruit Fasciation Disorder',
            **{name: name for name in self.diseases_5},
        }
        self.diseases = self.diseases_5  # Default

        # Both model backends must preserve the condition named by their labels.
        self.keras_class_map = self.yolov8_disease_map

        self.metadata_candidates = []
        if self.model_path:
            model_dir = os.path.dirname(self.model_path)
            if model_dir:
                self.metadata_candidates.append(os.path.join(model_dir, 'pineapple_model_metadata.json'))
        self.metadata_candidates.extend([
            os.path.join(project_root, 'models', 'pineapple_model_metadata.json'),
            os.path.join(project_root, 'pineapple_model_metadata.json')
        ])

        # Read metadata first so class names and input settings are available immediately.
        self.load_metadata()
        
        # Load model if exists
        if self.model_path:
            self.load_model()
        else:
            print(f"Warning: No model found")
            print("Using rule-based detection as fallback")

        self.load_scene_model()

    def load_scene_model(self):
        """Load the general COCO model used to reject obvious non-plant scenes."""
        scene_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'yolov8n.pt')
        if not os.path.exists(scene_path):
            return
        try:
            from ultralytics import YOLO
            self.scene_model = YOLO(scene_path)
            print(f"✅ Scene validation model loaded from {scene_path}")
        except Exception as e:
            print(f"⚠️ Scene validation model unavailable: {e}")

    def detect_scene_objects(self, image_path):
        """Return obvious non-plant objects detected by the general model."""
        if self.scene_model is None:
            return []
        try:
            results = self.scene_model.predict(image_path, verbose=False, conf=0.35)
            blocked = {'person', 'cat', 'dog', 'bird', 'car', 'motorcycle', 'bicycle'}
            objects = []
            for result in results or []:
                if result.boxes is None:
                    continue
                for box in result.boxes:
                    name = result.names[int(box.cls[0])]
                    if name in blocked:
                        objects.append(name)
            return sorted(set(objects))
        except Exception as e:
            print(f"⚠️ Scene validation failed: {e}")
            return []

    def load_metadata(self):
        """Load model metadata JSON if available."""
        for candidate in self.metadata_candidates:
            if not candidate or not os.path.exists(candidate):
                continue

            try:
                with open(candidate, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                classes = metadata.get('classes') or []
                mapped_classes = [self.keras_class_map.get(c, c) for c in classes]

                self.metadata = metadata
                self.metadata_path = candidate

                if mapped_classes:
                    self.diseases = mapped_classes

                if metadata.get('num_classes'):
                    self.num_classes = int(metadata['num_classes'])

                print(f"✅ Metadata loaded from {candidate}")
                if classes:
                    print(f"   Metadata classes: {classes}")
                break
            except Exception as e:
                print(f"Warning: Failed to load metadata from {candidate}: {e}")
    
    def load_model(self):
        """Load supported checkpoints by their contents, including YOLO best.pt."""
        try:
            extension = os.path.splitext(self.model_path)[1].lower()
            if extension == '.pt':
                try:
                    from ultralytics import YOLO
                    self.model = YOLO(self.model_path)
                    self.model_type = 'yolov8'
                except Exception:
                    import torch
                    self.model = torch.load(self.model_path, map_location='cpu')
                    self.model.eval()
                    self.model_type = 'pytorch'
            elif extension in {'.keras', '.h5'}:
                import tensorflow as tf
                self.model = tf.keras.models.load_model(self.model_path, compile=False)
                self.model_type = 'keras'
                self.num_classes = self.model.output_shape[-1]
                classes = self.metadata.get('classes', []) if self.metadata else []
                mapped = [self.keras_class_map.get(name, name) for name in classes]
                if len(mapped) == self.num_classes:
                    self.diseases = mapped
                else:
                    self.diseases = self.diseases_3 if self.num_classes == 3 else self.diseases_5
            if self.model is not None:
                print(f'Model loaded: {self.model_type} ({self.model_path})')
        except Exception as error:
            print(f'Error loading model: {error}')
            self.model = None
            self.model_type = None
    
    def preprocess_image(self, image_path):
        """Preprocess image for detection"""
        # Read image
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError("Unable to read image")
        
        # Determine target size based on model
        if self.model and self.model_type == 'keras':
            # Get target size from model input shape
            input_shape = self.model.input_shape
            target_size = (input_shape[1], input_shape[2]) if len(input_shape) >= 3 else (224, 224)
        elif self.metadata and self.metadata.get('img_size'):
            img_size = self.metadata.get('img_size', [224, 224])
            target_size = (int(img_size[0]), int(img_size[1]))
        else:
            # Default size for rule-based or PyTorch
            target_size = (640, 640)
        
        # Resize to target size
        img = cv2.resize(img, target_size)
        
        # Convert to RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        return img, img_rgb

    def validate_pineapple_image(self, img):
        """Return whether the image looks like a pineapple plant or fruit.

        This is a conservative pre-check so obvious non-pineapple images are
        rejected before disease classification runs.
        """
        if img is None or img.size == 0:
            return False, 0.0, {'reason': 'empty_image'}

        resized = cv2.resize(img, (256, 256))
        hsv = cv2.cvtColor(resized, cv2.COLOR_BGR2HSV)

        green_mask = cv2.inRange(hsv, np.array([35, 30, 30]), np.array([90, 255, 255]))
        yellow_mask = cv2.inRange(hsv, np.array([15, 40, 40]), np.array([40, 255, 255]))
        brown_mask = cv2.inRange(hsv, np.array([5, 40, 20]), np.array([25, 255, 140]))

        green_ratio = float(np.sum(green_mask > 0)) / (256 * 256)
        yellow_ratio = float(np.sum(yellow_mask > 0)) / (256 * 256)
        brown_ratio = float(np.sum(brown_mask > 0)) / (256 * 256)

        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 80, 160)
        edge_density = float(np.sum(edges > 0)) / (256 * 256)

        color_score = min(1.0, green_ratio + yellow_ratio + brown_ratio)
        texture_score = min(1.0, edge_density * 6.0)
        pineapple_score = (color_score * 0.7) + (texture_score * 0.3)

        # Pineapple images usually have enough plant/fruit coloration and edge detail.
        # Reject generic green plants and textured backgrounds. The previous low
        # threshold allowed almost any leafy image to reach disease inference.
        is_pineapple = pineapple_score >= 0.40 and (
            yellow_ratio >= 0.08 or brown_ratio >= 0.08 or green_ratio >= 0.18
        )

        return is_pineapple, pineapple_score, {
            'green_ratio': round(green_ratio, 4),
            'yellow_ratio': round(yellow_ratio, 4),
            'brown_ratio': round(brown_ratio, 4),
            'edge_density': round(edge_density, 4),
            'pineapple_score': round(pineapple_score, 4)
        }
    
    def rule_based_detection(self, img):
        """
        Rule-based disease detection using color analysis
        This is a fallback method when ML model is not available
        """
        # Convert to HSV for better color analysis
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        # Analyze different color ranges
        # Yellow spots detection
        yellow_lower = np.array([20, 50, 50])
        yellow_upper = np.array([40, 255, 255])
        yellow_mask = cv2.inRange(hsv, yellow_lower, yellow_upper)
        yellow_ratio = np.sum(yellow_mask > 0) / (img.shape[0] * img.shape[1])
        
        # Brown/Black rot detection
        brown_lower = np.array([10, 50, 20])
        brown_upper = np.array([20, 255, 100])
        brown_mask = cv2.inRange(hsv, brown_lower, brown_upper)
        brown_ratio = np.sum(brown_mask > 0) / (img.shape[0] * img.shape[1])
        
        # Pink disease detection
        pink_lower = np.array([140, 50, 50])
        pink_upper = np.array([170, 255, 255])
        pink_mask = cv2.inRange(hsv, pink_lower, pink_upper)
        pink_ratio = np.sum(pink_mask > 0) / (img.shape[0] * img.shape[1])
        
        # Green (healthy) detection
        green_lower = np.array([40, 40, 40])
        green_upper = np.array([80, 255, 255])
        green_mask = cv2.inRange(hsv, green_lower, green_upper)
        green_ratio = np.sum(green_mask > 0) / (img.shape[0] * img.shape[1])
        
        # Determine disease based on color ratios
        max_threshold = 0.15
        
        if brown_ratio > max_threshold:
            if brown_ratio > 0.25:
                disease = 'Heart Rot'
                confidence = min(0.95, 0.60 + brown_ratio)
            else:
                disease = 'Fruit Rot'
                confidence = min(0.95, 0.55 + brown_ratio * 2)
        elif yellow_ratio > max_threshold:
            disease = 'Yellow Spot'
            confidence = min(0.95, 0.50 + yellow_ratio * 2)
        elif pink_ratio > 0.10:
            disease = 'Pink Disease'
            confidence = min(0.95, 0.50 + pink_ratio * 3)
        elif green_ratio > 0.30:
            disease = 'Healthy'
            confidence = min(0.99, 0.70 + green_ratio)
        else:
            disease = 'Healthy'
            confidence = 0.60
        
        return disease, confidence, {
            'yellow_ratio': float(yellow_ratio),
            'brown_ratio': float(brown_ratio),
            'pink_ratio': float(pink_ratio),
            'green_ratio': float(green_ratio)
        }
    
    def yolov8_detection(self, image_path):
        """Detection using YOLOv8 object detection model"""
        try:
            # Run inference
            results = self.model.predict(image_path, verbose=False, conf=0.5)
            
            if not results or len(results) == 0:
                return None, None, {'num_bboxes': 0, 'reason': 'no_pineapple_object_detected'}
            
            result = results[0]
            boxes = result.boxes
            
            if boxes is None or len(boxes) == 0:
                # No objects detected
                return None, None, {'num_bboxes': 0, 'reason': 'no_pineapple_object_detected'}
            
            # Get detections
            detected_classes = {}
            confidences = []
            
            for box in boxes:
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])
                class_name = result.names[class_id]
                
                # Map YOLOv8 class names to our disease names
                mapped_disease = self.yolov8_disease_map.get(class_name)
                if not mapped_disease:
                    continue
                
                if mapped_disease not in detected_classes:
                    detected_classes[mapped_disease] = []
                detected_classes[mapped_disease].append(confidence)
                confidences.append(confidence)
            
            # Determine final disease
            if not detected_classes:
                return None, None, {
                    'num_bboxes': 0,
                    'reason': 'no_recognized_pineapple_object_detected'
                }
            
            # Find disease with highest average confidence
            disease_confidences = {
                disease: np.mean(confs) for disease, confs in detected_classes.items()
            }
            
            final_disease = max(disease_confidences, key=disease_confidences.get)
            final_confidence = disease_confidences[final_disease]
            
            # Detection statistics
            analysis = {
                'detected_classes': list(detected_classes.keys()),
                'class_counts': {d: len(c) for d, c in detected_classes.items()},
                'avg_confidence': float(np.mean(confidences)) if confidences else 0.0,
                'num_bboxes': len(boxes)
            }
            
            return final_disease, final_confidence, analysis
            
        except Exception as e:
            print(f"Error in YOLOv8 detection: {e}")
            import traceback
            traceback.print_exc()
            return None, None, None
    
    def model_based_detection(self, img):
        """Detection using trained ML model (supports Keras and PyTorch)"""
        try:
            if self.model_type == 'keras':
                # Keras/TensorFlow prediction
                import tensorflow as tf
                
                # Preprocess for Keras model
                img_array = np.array(img).astype('float32') / 255.0
                img_array = np.expand_dims(img_array, axis=0)
                
                # Run inference
                predictions = self.model.predict(img_array, verbose=0)
                predicted_idx = np.argmax(predictions[0])
                confidence = float(predictions[0][predicted_idx])
                
                disease = self.diseases[predicted_idx]
                
                return disease, confidence, None
                
            elif self.model_type == 'pytorch':
                # PyTorch prediction
                import torch
                
                # Preprocess for PyTorch model
                img_tensor = torch.from_numpy(img).permute(2, 0, 1).float() / 255.0
                img_tensor = img_tensor.unsqueeze(0)
                
                # Run inference
                with torch.no_grad():
                    outputs = self.model(img_tensor)
                    probabilities = torch.nn.functional.softmax(outputs, dim=1)
                    confidence, predicted = torch.max(probabilities, 1)
                
                disease = self.diseases[predicted.item()]
                confidence = confidence.item()
                
                return disease, confidence, None
            else:
                return None, None, None
            
        except Exception as e:
            print(f"Error in model-based detection: {e}")
            import traceback
            traceback.print_exc()
            return None, None, None
    
    def detect(self, image_path):
        """
        Main detection method
        Returns detection results
        """
        try:
            img, img_rgb = self.preprocess_image(image_path)
            is_pineapple, pineapple_score, pineapple_analysis = self.validate_pineapple_image(img)

            scene_objects = self.detect_scene_objects(image_path)
            if scene_objects:
                return {
                    'error': 'Not a pineapple image. Remove people or unrelated objects from the frame.',
                    'not_pineapple': True,
                    'disease': 'Not Pineapple',
                    'confidence': 0.0,
                    'method': 'scene-validation',
                    'timestamp': datetime.now().isoformat(),
                    'image_path': image_path,
                    'analysis': {'blocked_objects': scene_objects}
                }

            if not is_pineapple:
                return {
                    'error': 'Not a pineapple image. Disease detection skipped.',
                    'not_pineapple': True,
                    'disease': 'Not Pineapple',
                    'confidence': 0.0,
                    'method': 'validation',
                    'timestamp': datetime.now().isoformat(),
                    'image_path': image_path,
                    'analysis': pineapple_analysis,
                    'recommendations': {
                        'severity': 'None',
                        'action': 'Upload a pineapple leaf or fruit image',
                        'treatments': [
                            'Please upload a pineapple plant or fruit photo',
                            'Close-up images of leaves or fruit work best'
                        ],
                        'recommendations': [
                            'Make sure the image contains pineapple leaves or fruit',
                            'Avoid uploading unrelated objects, people, or scenery'
                        ]
                    }
                }

            # Try YOLOv8 detection first if model is YOLOv8
            if self.model is not None and self.model_type == 'yolov8':
                disease, confidence, analysis = self.yolov8_detection(image_path)
                if disease is None:
                    return {
                        'error': 'Not a pineapple image. No pineapple plant or fruit was detected.',
                        'not_pineapple': True,
                        'disease': 'Not Pineapple',
                        'confidence': 0.0,
                        'method': 'yolov8-validation',
                        'timestamp': datetime.now().isoformat(),
                        'image_path': image_path,
                        'analysis': analysis or {'reason': 'no_pineapple_object_detected'}
                    }
                if pineapple_score < 0.40:
                    return {
                        'error': 'Not a pineapple image. Please capture a pineapple plant or fruit.',
                        'not_pineapple': True,
                        'disease': 'Not Pineapple',
                        'confidence': 0.0,
                        'method': 'visual-validation',
                        'timestamp': datetime.now().isoformat(),
                        'image_path': image_path,
                        'analysis': pineapple_analysis
                    }
                method = 'yolov8'
            else:
                # Preprocess image for other models
                img, img_rgb = self.preprocess_image(image_path)
                
                # Try model-based detection
                if self.model is not None:
                    disease, confidence, analysis = self.model_based_detection(img_rgb)
                    if disease is not None:
                        method = 'model'
                    else:
                        # Fallback to rule-based
                        disease, confidence, analysis = self.rule_based_detection(img)
                        method = 'rule-based'
                else:
                    # Use rule-based detection
                    disease, confidence, analysis = self.rule_based_detection(img)
                    method = 'rule-based'
            
            # Prepare result
            result = {
                'disease': disease,
                'confidence': float(confidence),
                'method': method,
                'timestamp': datetime.now().isoformat(),
                'image_path': image_path
            }
            
            # Add analysis details if available
            if analysis:
                result['analysis'] = analysis

            if pineapple_analysis:
                result['pineapple_validation'] = pineapple_analysis
            
            # Add recommendations based on disease, excluding fertilization guidance.
            result['recommendations'] = self.get_recommendations(disease)
            if isinstance(result['recommendations'], dict):
                result['recommendations'].pop('fertilization', None)
            
            return result
            
        except Exception as e:
            return {
                'error': str(e),
                'disease': 'Unknown',
                'confidence': 0.0
            }
    
    def get_recommendations(self, disease):
        """Get treatment and fertilization recommendations for detected disease"""
        recommendations = {
            'Heart Rot': {
                'severity': 'High',
                'action': 'Immediate',
                'treatments': [
                    'Mag-apply ng fungicide tulad ng metalaxyl o fosetyl-Al',
                    'Alisin ang mga nahawaang parte ng halaman',
                    'Pagbutihin ang drainage ng lupa',
                    'Bawasan ang watering upang hindi maging sobrang basa'
                ],
                'recommendations': [
                    'Mag-spray tuwing 7-14 days',
                    'Monitor ang neighboring plants',
                    'Gumamit ng resistant varieties sa susunod'
                ],
                'fertilization': {
                    'priority': 'Medium',
                    'note': 'Reduce nitrogen during treatment. Focus on recovery.',
                    'schedule': [
                        {
                            'timing': 'After treatment (2-3 weeks)',
                            'type': 'Balanced NPK (14-14-14)',
                            'amount': '50g per plant',
                            'method': 'Side dressing around plant base',
                            'frequency': 'Monthly'
                        },
                        {
                            'timing': 'Recovery phase (1-2 months)',
                            'type': 'Potassium-rich fertilizer (0-0-60)',
                            'amount': '30g per plant',
                            'method': 'Foliar spray (diluted)',
                            'frequency': 'Bi-weekly'
                        }
                    ],
                    'micronutrients': ['Zinc', 'Iron', 'Manganese'],
                    'avoid': ['Excessive nitrogen - may worsen infection']
                }
            },
            'Fruit Rot': {
                'severity': 'High',
                'action': 'Immediate',
                'treatments': [
                    'Linisin ang mga sugat sa prutas gamit ang fungicide',
                    'Mag-apply ng benomyl o thiabendazole',
                    'Panatilihing tuyo ang prutas',
                    'Harvest ang hinog na prutas agad'
                ],
                'recommendations': [
                    'Careful handling ng prutas',
                    'Post-harvest treatment',
                    'Proper storage conditions'
                ],
                'fertilization': {
                    'priority': 'Low',
                    'note': 'Focus on fruit protection. Minimal fertilization during harvest.',
                    'schedule': [
                        {
                            'timing': 'Post-harvest',
                            'type': 'Balanced NPK (12-12-17)',
                            'amount': '40g per plant',
                            'method': 'Broadcast application',
                            'frequency': 'Once after harvest'
                        }
                    ],
                    'micronutrients': ['Calcium', 'Boron'],
                    'avoid': ['Heavy fertilization during fruiting stage']
                }
            },
            'Yellow Spot': {
                'severity': 'Medium',
                'action': 'Within 1-2 days',
                'treatments': [
                    'Mag-spray ng copper-based fungicide',
                    'Alisin at sunugin ang mga infected leaves',
                    'Pagbutihin ang air circulation',
                    'Mag-apply ng balanced fertilizer'
                ],
                'recommendations': [
                    'Regular monitoring',
                    'Maintain plant health',
                    'Control humidity levels'
                ],
                'fertilization': {
                    'priority': 'High',
                    'note': 'Strengthen plant immunity through proper nutrition.',
                    'schedule': [
                        {
                            'timing': 'Immediately',
                            'type': 'Complete fertilizer (16-16-16)',
                            'amount': '60g per plant',
                            'method': 'Side dressing, 15cm from base',
                            'frequency': 'Every 6 weeks'
                        },
                        {
                            'timing': 'Ongoing',
                            'type': 'Foliar fertilizer (NPK + micronutrients)',
                            'amount': '2g per liter water',
                            'method': 'Foliar spray on leaves',
                            'frequency': 'Weekly'
                        }
                    ],
                    'micronutrients': ['Zinc', 'Manganese', 'Iron', 'Copper'],
                    'avoid': ['Imbalanced nutrients may worsen symptoms']
                }
            },
            'Pink Disease': {
                'severity': 'High',
                'action': 'Immediate',
                'treatments': [
                    'Alisin ang mga infected fruits',
                    'Disinfect ang tools gamit ang 10% bleach solution',
                    'Control ang insect pests',
                    'Iwasan ang mga sugat sa prutas'
                ],
                'recommendations': [
                    'Proper sanitation practices',
                    'Insect control measures',
                    'Careful harvesting techniques'
                ],
                'fertilization': {
                    'priority': 'Low',
                    'note': 'Bacterial infection - focus on sanitation first.',
                    'schedule': [
                        {
                            'timing': 'After infection control',
                            'type': 'Low nitrogen NPK (10-10-20)',
                            'amount': '40g per plant',
                            'method': 'Soil application',
                            'frequency': 'Monthly'
                        }
                    ],
                    'micronutrients': ['Calcium - strengthens cell walls'],
                    'avoid': ['High nitrogen - promotes bacterial growth']
                }
            },
            'Healthy': {
                'severity': 'None',
                'action': 'Maintain',
                'treatments': [
                    'Ipagpatuloy ang regular care',
                    'Balanced fertilization',
                    'Proper watering schedule',
                    'Regular monitoring'
                ],
                'recommendations': [
                    'Continue prevention measures',
                    'Regular inspection',
                    'Maintain good agricultural practices'
                ],
                'fertilization': {
                    'priority': 'High',
                    'note': 'Optimal growth phase - maintain regular fertilization.',
                    'schedule': [
                        {
                            'timing': 'Vegetative stage (Month 1-6)',
                            'type': 'High nitrogen NPK (20-10-10)',
                            'amount': '70g per plant',
                            'method': 'Side dressing in circular band',
                            'frequency': 'Every 2 months'
                        },
                        {
                            'timing': 'Pre-flowering (Month 7-10)',
                            'type': 'Balanced NPK (14-14-14)',
                            'amount': '60g per plant',
                            'method': 'Broadcast and incorporate',
                            'frequency': 'Every 6-8 weeks'
                        },
                        {
                            'timing': 'Fruiting stage (Month 11-18)',
                            'type': 'Potassium-rich (10-10-30)',
                            'amount': '80g per plant',
                            'method': 'Split application around plant',
                            'frequency': 'Every 2 months'
                        },
                        {
                            'timing': 'Supplemental feeding',
                            'type': 'Foliar spray (NPK 15-30-15)',
                            'amount': '3g per liter water',
                            'method': 'Early morning foliar application',
                            'frequency': 'Bi-weekly'
                        }
                    ],
                    'micronutrients': ['Iron', 'Zinc', 'Manganese', 'Boron', 'Copper', 'Molybdenum'],
                    'organic_options': [
                        'Compost: 2-3kg per plant every 3 months',
                        'Vermicast: 1kg per plant monthly',
                        'Chicken manure: 500g per plant (well-composted)',
                        'Seaweed extract: Foliar spray bi-weekly'
                    ],
                    'avoid': ['Over-fertilization', 'Application during very hot or dry conditions']
                }
            },
            'Diseased': {
                'severity': 'High',
                'action': 'Immediate',
                'treatments': [
                    'Identify specific disease symptoms',
                    'Isolate affected plants if possible',
                    'Apply broad-spectrum fungicide',
                    'Remove severely affected parts',
                    'Improve overall plant health'
                ],
                'recommendations': [
                    'Get professional diagnosis for specific disease',
                    'Monitor closely for disease progression',
                    'Improve growing conditions'
                ],
                'fertilization': {
                    'priority': 'Medium',
                    'note': 'Boost plant immunity while treating disease.',
                    'schedule': [
                        {
                            'timing': 'During treatment',
                            'type': 'Balanced NPK (15-15-15)',
                            'amount': '50g per plant',
                            'method': 'Side dressing',
                            'frequency': 'Every 6 weeks'
                        },
                        {
                            'timing': 'Recovery support',
                            'type': 'Potassium sulfate',
                            'amount': '30g per plant',
                            'method': 'Soil drench',
                            'frequency': 'Monthly'
                        }
                    ],
                    'micronutrients': ['Complete micronutrient mix'],
                    'avoid': ['Excessive nitrogen during disease treatment']
                }
            },
            'Possibly Diseased': {
                'severity': 'Medium',
                'action': 'Monitor closely',
                'treatments': [
                    'Observe symptoms carefully',
                    'Improve air circulation',
                    'Adjust watering schedule',
                    'Apply preventive fungicide if needed',
                    'Check for pest presence'
                ],
                'recommendations': [
                    'Take another photo in 1-2 days for re-evaluation',
                    'Check nearby plants for similar symptoms',
                    'Maintain good sanitation practices'
                ],
                'fertilization': {
                    'priority': 'Medium',
                    'note': 'Maintain plant health while monitoring condition.',
                    'schedule': [
                        {
                            'timing': 'Current stage',
                            'type': 'Balanced NPK (14-14-14)',
                            'amount': '55g per plant',
                            'method': 'Ring application around plant',
                            'frequency': 'Every 2 months'
                        },
                        {
                            'timing': 'Supplemental',
                            'type': 'Seaweed extract or organic fertilizer',
                            'amount': '50ml per plant (diluted 1:20)',
                            'method': 'Foliar and soil application',
                            'frequency': 'Weekly'
                        }
                    ],
                    'micronutrients': ['Iron', 'Zinc', 'Manganese'],
                    'avoid': ['Hold heavy fertilization until diagnosis is clear']
                }
            }
        }
        
        return recommendations.get(disease, {
            'severity': 'Unknown',
            'action': 'Consult expert',
            'treatments': ['Consult agricultural expert'],
            'recommendations': ['Get professional diagnosis'],
            'fertilization': {
                'priority': 'Low',
                'note': 'Wait for proper diagnosis before fertilization.',
                'schedule': [],
                'micronutrients': [],
                'avoid': ['Any fertilization until diagnosis is confirmed']
            }
        })

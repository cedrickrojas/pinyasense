# Scripts Index

Use this folder for helper, training, and test Python scripts.

## Training and Dataset Tools

- [quick_train.sh](quick_train.sh)
- [train_complete.py](train_complete.py)
- [train_yolov8.py](train_yolov8.py)
- [yolov8_quickstart.py](yolov8_quickstart.py)
- [prepare_yolov8_dataset.py](prepare_yolov8_dataset.py)
- [setup_diagnostics.py](setup_diagnostics.py)
- [balance_dataset_5class.py](balance_dataset_5class.py)
- [convert_dataset.py](convert_dataset.py)
- [train_model.py](train_model.py)
- [firebase_setup.py](firebase_setup.py)
- [TRAINING_GUIDE.py](TRAINING_GUIDE.py)
- [YOLOV8_ACTION_PLAN.py](YOLOV8_ACTION_PLAN.py)

## Tests and Validation

- [test_bh1750_detect.py](test_bh1750_detect.py)
- [test_dht22.py](test_dht22.py)
- [test_model.py](test_model.py)
- [test_sensor.py](test_sensor.py)
- [test_simple.py](test_simple.py)
- [test_yolov8_inference.py](test_yolov8_inference.py)
- [bh1750_test.py](bh1750_test.py)

## Notes

- Reusable runtime modules live in `core/`.
- Move training outputs to `archive/training/` after copying deployable weights into `models/`.
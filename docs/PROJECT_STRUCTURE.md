# Project Structure

This is the current top-level layout for AgriPinya.

```text
agripinya/
├── app.py                      # Main Flask app
├── core/                       # Reusable runtime modules
│   ├── auth.py                 # Login/session helpers
│   ├── config.py               # App configuration
│   ├── disease_detector.py     # Detection engine
│   ├── email_service.py        # Mail helpers
│   ├── firebase_manager.py     # Firebase integration
│   ├── sensor_monitor.py       # Sensor integration
│   └── time_series_forecaster.py # Forecasting logic
├── requirements.txt            # Python dependencies
│
├── templates/                  # HTML templates
├── static/                     # CSS, JS, icons, PWA assets
│
├── uploads/                    # Active upload queue (.gitkeep only)
├── results/                    # Active detection results (.gitkeep only)
│
├── models/                     # Deployable model files
│   ├── pineapple_disease_model*.h5
│   ├── pineapple_disease_model_final.keras
│   ├── pineapple_model_metadata.json
│   └── pineapple_yolov8n_latest.pt
│
├── scripts/                    # Helper, training, and test Python scripts
│   ├── train_complete.py
│   ├── train_yolov8.py
│   ├── test_yolov8_inference.py
│   └── yolov8_quickstart.py
│
├── imported_dataset/           # Source and prepared datasets
│
├── archive/                    # Old generated files and experiments
│   ├── results/                # Archived result JSON files
│   ├── uploads/                # Archived test uploads and media
│   └── training/               # Archived training outputs
│       ├── models/             # Old YOLO training run folders
│       └── runs/               # Old detection/training outputs
│
└── docs/                       # Documentation and training guides
```

Rules of thumb:

- Keep deployable models in `models/`.
- Keep reusable runtime modules in `core/`.
- Keep helper and training scripts in `scripts/`.
- Keep active app uploads and results folders empty except for `.gitkeep`.
- Move old test uploads and result files into `archive/uploads/` and `archive/results/`.
- Move old YOLO training folders and runs into `archive/training/`.
- Keep docs in `docs/` and use `docs/README.md` as the guide index.

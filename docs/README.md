# AgriPinya - Pineapple Disease Detection System

<div align="center">
  <h1>🍍 AgriPinya</h1>
  <p><strong>Sistema ng Pag-detect ng Sakit ng Pinya</strong></p>
  <p>Isang advanced web-based system para sa mabilis at tumpak na detection ng mga sakit ng pinya gamit ang artificial intelligence at image processing.</p>
</div>

---

## 📋 Tungkol sa Proyekto

Ang **AgriPinya** ay isang web application na dinisenyo para tulungan ang mga magsasaka ng pinya sa Pilipinas na mabilis na matukoy ang mga sakit ng kanilang pananim. Sa pamamagitan ng pag-upload ng larawan ng dahon o bunga ng pinya, ang system ay kayang mag-detect ng mga sumusunod na sakit:

### Mga Sakit na Natutukoy:
- **Heart Rot** (Phytophthora spp.)
- **Fruit Rot** (Thielaviopsis paradoxa)
- **Yellow Spot** (Curvularia spp.)
- **Pink Disease** (Pantoea citrea)
- **Healthy** (Malusog na pinya)

### Project Objective (Item 4)
- **To build a web-based platform that displays real-time data, health diagnostics, and harvest-time predictions.**

---

## ✨ Mga Features

- 🖼️ **Image Upload** - I-upload ang larawan ng pinya (PNG, JPG, JPEG)
- 🔍 **Real-time Detection** - Mabilis na detection sa loob ng ilang segundo
- 📊 **Detailed Results** - Confidence score at komprehensibong analysis
- 💊 **Treatment Recommendations** - Mga recommended treatments at prevention measures
- 📚 **Disease Information** - Detalyadong impormasyon tungkol sa bawat sakit
- 📝 **Detection History** - I-track ang lahat ng naunang detection
- 📱 **Responsive Design** - Gumagana sa desktop, tablet, at mobile
- 🌐 **Tagalog Interface** - User-friendly na interface sa wikang Filipino

---

## 🛠️ Technologies Used

### Backend:
- **Python 3.8+**
- **Flask** - Web framework
- **OpenCV** - Image processing
- **NumPy** - Numerical computations
- **PyTorch** (Optional) - Machine learning model support

### Frontend:
- **HTML5**
- **CSS3** (with modern gradients and animations)
- **JavaScript** (Vanilla JS)
- **Font Awesome** - Icons

---

## 📦 Installation

### Prerequisites:
- Python 3.8 or higher
- pip (Python package manager)
- Virtual environment (recommended)

### Step-by-Step Installation:

1. **Clone o download ang repository**
   ```bash
   cd /home/voicebrain/agripinya
   ```

2. **Create virtual environment** (recommended)
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Sa Linux/Mac
   # or
   venv\Scripts\activate  # Sa Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create necessary directories**
   ```bash
   mkdir -p uploads results models static/images
   ```

5. **Run the application**
   ```bash
   python app.py
   ```

6. **Open sa browser**
   ```
   http://localhost:5000
   ```

---

## 🚀 Usage Guide

### Para sa Mga Magsasaka:

1. **Kumuha ng Larawan**
   - Kumuha ng malinaw na larawan ng dahon o bunga ng pinya
   - Siguraduhing maayos ang lighting
   - Malapit na shot para sa mas tumpak na results

2. **I-upload ang Larawan**
   - Buksan ang AgriPinya sa browser
   - Click ang "Pumili ng Larawan" o mag-drag and drop
   - Piliin ang larawan mula sa inyong device

3. **I-detect ang Sakit**
   - Click ang "Detect Disease" button
   - Maghintay ng ilang segundo para sa results

4. **Basahin ang Results**
   - Makikita ang detected disease
   - Confidence score (tumpak na percentage)
   - Severity level at action required
   - Recommended treatments
   - Prevention measures

5. **Gumawa ng Aksyon**
   - Sundin ang mga recommended treatments
   - Konsultahin ang agricultural expert kung kinakailangan
   - Regular monitoring ng taniman

---

## 📊 Paano Gumagana ang Detection

Ang AgriPinya ay gumagamit ng dalawang pamamaraan:

### 1. Rule-Based Detection (Default)
- Sinusuri ang mga kulay ng larawan (HSV color space)
- Tinutukoy ang mga pattern ng sakit base sa color ratios
- Mabilis at hindi nangangailangan ng trained model
- Good fallback method

### 2. Model-Based Detection (Advanced)
- Gumagamit ng PyTorch deep learning model
- Mas tumpak na results
- Nangangailangan ng trained model file
- Automatic fallback sa rule-based kung walang model

---

## 🗂️ Project Structure

See [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for the full folder map, [docs/README.md](docs/README.md) for the documentation index, and [scripts/README.md](scripts/README.md) for the Python script index.

```
agripinya/
│
├── app.py                      # Main Flask application
├── core/                       # Reusable runtime modules
│   ├── auth.py
│   ├── config.py
│   ├── disease_detector.py
│   ├── email_service.py
│   ├── firebase_manager.py
│   ├── sensor_monitor.py
│   └── time_series_forecaster.py
├── requirements.txt            # Python dependencies
├── README.md                   # Documentation (ito!)
│
├── templates/                  # HTML templates
│   ├── index.html             # Main page
│   └── about.html             # About page
│
├── static/                     # Static files
│   ├── css/
│   │   └── style.css          # Stylesheet
│   └── js/
│       └── app.js             # JavaScript
│
├── uploads/                    # Uploaded images
├── results/                    # Detection results (JSON)
├── models/                     # Deployable ML models
│   └── pineapple_disease_model.pt
├── scripts/                    # Helper and training Python scripts
└── archive/                    # Archived generated files
   ├── results/
   ├── uploads/
   └── training/
      ├── models/
      └── runs/
```

---

## 🔧 Configuration

### Mga Settings na Pwedeng I-adjust:

Sa `app.py`:
```python
UPLOAD_FOLDER = 'uploads'           # Folder para sa uploads
RESULTS_FOLDER = 'results'          # Folder para sa results
MAX_FILE_SIZE = 16 * 1024 * 1024   # Max file size (16MB)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}  # Allowed file types
```

Sa `disease_detector.py`:
```python
self.model_path = 'models/pineapple_disease_model.pt'  # Model path
```

---

## 🤝 Para sa Developers

### API Endpoints:

1. **POST /api/detect**
   - Upload image para sa detection
   - Parameters: `image` (file)
   - Returns: Detection results (JSON)

2. **GET /api/diseases**
   - Get list ng lahat ng diseases with info
   - Returns: Disease information (JSON)

3. **GET /api/history**
   - Get detection history
   - Returns: Array ng past detections (JSON)

4. **GET /api/stats**
   - Get detection statistics
   - Returns: Stats (total, counts, recent) (JSON)

5. **GET /api/forecast/growth-harvest**
   - Time-series forecasting for pineapple growth stage and optimal harvest date
   - Query Params (optional):
     - `planting_date` (format: `YYYY-MM-DD`)
     - `horizon_days` (forecast horizon, default: `30`, max: `90`)
     - `history_days` (sensor history window, default: `90`, max: `365`)
     - `profile` (`standard`, `smooth_cayenne`, `md2`)
     - `cycle_days` (custom total cycle override)
     - `stage_vegetative_end`, `stage_pre_flowering_end`, `stage_fruit_development_end`, `stage_ripening_end`
   - Returns: Predicted growth stage, optimal harvest date, confidence, and daily environment forecast (JSON)

6. **GET /forecast**
   - Web dashboard for growth-stage and harvest forecasting
   - Includes charts and farm profile tuning controls

### Adding a Custom ML Model:

1. I-train ang model gamit ang pineapple disease dataset
2. I-save as PyTorch model (.pt file)
3. I-place sa `models/` folder
4. Update ang `model_path` sa `disease_detector.py`
5. Siguraduhing may 5 classes: Heart Rot, Fruit Rot, Yellow Spot, Pink Disease, Healthy

---

## 🐛 Troubleshooting

### Common Issues:

**Issue: "Module not found" error**
```bash
# Solution:
pip install -r requirements.txt
```

**Issue: "Port already in use"**
```bash
# Solution: Change port sa app.py
app.run(debug=True, host='0.0.0.0', port=5001)  # Use different port
```

**Issue: Mabagal ang detection**
```bash
# Solution: Make sure may sapat na RAM at CPU
# Consider using smaller image sizes
```

**Issue: Low confidence scores**
```bash
# Solution: 
# - Use clearer, well-lit images
# - Take closer shots of affected areas
# - Train a custom model for better accuracy
```

---

## 📈 Future Enhancements

- [ ] Mobile App version
- [ ] Offline detection capability
- [ ] Multi-language support (English, other Filipino dialects)
- [ ] GPS tagging para sa location-based tracking
- [ ] Community forum para sa mga magsasaka
- [ ] Integration with weather data
- [ ] Pest detection (hindi lang diseases)
- [ ] Yield prediction features
- [ ] SMS/Email notifications
- [ ] Export reports as PDF

---

## 📝 License

This project is created for educational and agricultural purposes to help Filipino farmers improve their pineapple farming practices.

---

## 👥 Contributors

- VoiceBrain Team
- Agricultural experts at consultants
- Filipino pineapple farmers community

---

## 📞 Contact & Support

Para sa mga tanong, suggestions, o bug reports:
- Create an issue sa GitHub repository
- Email: support@agripinya.ph (example)

---

## 🙏 Acknowledgments

Salamat sa:
- Mga magsasaka ng pinya sa Pilipinas
- Agricultural research institutions
- Open-source community
- Filipino tech community

---

<div align="center">
  <p><strong>Gawa para sa mga Magsasaka, Gawa ng mga Pilipino</strong></p>
  <p>🍍 AgriPinya - Mas Malusog na Pinya, Mas Masaganang Ani 🍍</p>
</div>

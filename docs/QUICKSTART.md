# 🍍 AgriPinya - Quick Start Guide

Mabilis na Gabay para Magsimula

---

## 1️⃣ Installation (Unang Gamit Lang)

```bash
cd /home/voicebrain/agripinya

# Option 1: Gamit ang startup script (Recommended)
./start.sh

# Option 2: Manual installation
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
mkdir -p uploads results models
python app.py
```

---

## 2️⃣ Paano Magrun ng System

### Simple:
```bash
cd /home/voicebrain/agripinya
./start.sh
```

### O kaya Manual:
```bash
cd /home/voicebrain/agripinya
source venv/bin/activate
python app.py
```

---

## 3️⃣ Access sa Browser

Buksan ang browser at pumunta sa:
```
http://localhost:5000
```

O kung may ibang device sa network:
```
http://YOUR_IP:5000
```

---

## 4️⃣ Paano Gamitin

1. **Upload Image** - Click "Pumili ng Larawan" o drag-and-drop
2. **Detect** - Click "Detect Disease" button
3. **View Results** - Makikita ang results, treatments, at recommendations
4. **Check History** - Scroll down para sa past detections

---

## 5️⃣ I-run as Service (Background)

Para tumakbo ang AgriPinya kahit naka-logout:

```bash
# Copy service file
sudo cp agripinya.service /etc/systemd/system/

# Enable and start
sudo systemctl enable agripinya
sudo systemctl start agripinya

# Check status
sudo systemctl status agripinya

# View logs
journalctl -u agripinya -f
```

---

## 6️⃣ Common Commands

```bash
# Start
./start.sh

# Stop (Ctrl+C sa terminal)
# O kung service:
sudo systemctl stop agripinya

# Restart service
sudo systemctl restart agripinya

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Clear uploads/results
rm uploads/* results/*
```

---

## 7️⃣ Troubleshooting

**Hindi mag-start?**
```bash
# Check kung may naka-run na sa port 5000
sudo lsof -i :5000
# O kaya
sudo netstat -tulpn | grep :5000

# Kill kung meron
sudo kill -9 <PID>
```

**Module not found?**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

**Permission denied?**
```bash
chmod +x start.sh
```

---

## 8️⃣ Para sa Production

1. **Change SECRET_KEY** sa config.py
2. **Disable DEBUG mode** sa app.py
3. **Use production WSGI server** (Gunicorn)
   ```bash
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:5000 app:app
   ```
4. **Setup reverse proxy** (Nginx)
5. **Enable HTTPS** (Let's Encrypt)

---

## 📞 Need Help?

- Basahin ang README.md para sa detailed documentation
- Check ang error logs
- Create issue sa repository

---

**Enjoy using AgriPinya! 🍍**

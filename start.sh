#!/bin/bash

# AgriPinya Startup Script
# This script sets up and runs the AgriPinya system

echo "🍍 Starting AgriPinya - Pineapple Disease Detection System"
echo "=================================================="

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found!"
    echo "Creating virtual environment..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "❌ Failed to create virtual environment"
        exit 1
    fi
    echo "✅ Virtual environment created"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if dependencies are installed
echo "Checking dependencies..."
pip list | grep -q Flask
if [ $? -ne 0 ]; then
    echo "Installing dependencies..."
    pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "❌ Failed to install dependencies"
        exit 1
    fi
    echo "✅ Dependencies installed"
fi

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p uploads results models static/images

# Create placeholder files
touch uploads/.gitkeep
touch results/.gitkeep

echo "✅ Setup complete!"
echo "=================================================="
echo "Starting Flask application..."
echo "Access the system at: http://localhost:5001"
echo "Optional camera mode: USE_HTTPS=1 python app.py"
echo "Press Ctrl+C to stop the server"
echo "=================================================="

# Safe default GPIO assignments for local startup (can still be overridden
# by existing exported environment variables before launching this script).
export SOIL_MOISTURE_PIN="${SOIL_MOISTURE_PIN:-17}"
export DHT_PIN="${DHT_PIN:-4}"
export WATER_PUMP_PIN="${WATER_PUMP_PIN:-27}"
export WATER_PUMP_ACTIVE_LOW="${WATER_PUMP_ACTIVE_LOW:-0}"

# Run the application
python app.py

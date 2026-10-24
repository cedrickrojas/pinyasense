// Global variables
let selectedFile = null;
let detectionResults = null;
let currentUser = null;
let singleDetectionMarkup = null;

function getResultsSection(restoreSingle = false) {
    const section = document.getElementById('resultsSection');
    if (!section) return null;
    if (singleDetectionMarkup === null && document.getElementById('diseaseBadge')) {
        singleDetectionMarkup = section.innerHTML;
    }
    if (restoreSingle && singleDetectionMarkup !== null) section.innerHTML = singleDetectionMarkup;
    return section;
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    settleMobileInputFocus();
    initializeApp();
});

function dismissMobileInputFocus() {
    const activeElement = document.activeElement;
    if (activeElement && typeof activeElement.blur === 'function') {
        activeElement.blur();
    }
    window.scrollTo(0, 0);
}

function settleMobileInputFocus() {
    dismissMobileInputFocus();
    [100, 350, 700].forEach((delay) => {
        window.setTimeout(dismissMobileInputFocus, delay);
    });
}

function initializeApp() {
    // Reset any toggle-able sections back to their default hidden state and scroll to
    // top. Without this, a bfcache restore (or a browser scroll-restoration edge case
    // scrollRestoration='manual' doesn't fully cover) can leave the page looking like it
    // landed on Spread Risk/Trends instead of Home after login or a refresh.
    ['weatherAlertSection', 'spreadRiskSection', 'trendsSection', 'riskMapSection'].forEach((id) => {
        const section = document.getElementById(id);
        if (section) section.style.display = 'none';
    });
    window.scrollTo(0, 0);

    // Check authentication first
    verifyAuthentication();

    // Setup event listeners
    setupUploadArea();
    
    // Load initial data only if relevant elements exist
    if (document.getElementById('totalDetections') || document.getElementById('trendCanvas')) {
        loadStats();
    }
    if (document.getElementById('diseasesGrid') || document.getElementById('diseaseBadge')) {
        loadDiseases();
    }
    
    // Setup detect button
    const detectBtn = document.getElementById('detectBtn');
    if (detectBtn) {
        detectBtn.addEventListener('click', detectDisease);
    }
    
    // Setup cancel button
    const cancelBtn = document.getElementById('cancelBtn');
    if (cancelBtn) {
        cancelBtn.addEventListener('click', cancelUpload);
    }
}

// Compatibility shim: some pages call `loadDiseaseSpreadRisk()` but older builds
// used the function name `showRiskMap`. Provide a safe alias to avoid runtime
// ReferenceError and stop breaking other scripts.
function loadDiseaseSpreadRisk() {
    if (typeof showRiskMap === 'function') {
        try {
            return showRiskMap();
        } catch (e) {
            console.warn('showRiskMap failed:', e);
            return Promise.resolve();
        }
    }
    return Promise.resolve();
}

// Pages that don't require a session; app.js is included on some of these too
// (e.g. login.html), so verifyAuthentication() must not redirect to /login while
// already there — doing so caused an infinite reload loop on the login page.
const PUBLIC_PATHS = ['/login', '/signup', '/', '/about'];

function verifyAuthentication() {
    if (PUBLIC_PATHS.includes(window.location.pathname)) {
        return;
    }

    fetch('/api/verify-session')
        .then(response => response.json())
        .then(data => {
            if (data.authenticated) {
                currentUser = data.user;
                updateUserUI();
            } else if (!PUBLIC_PATHS.includes(window.location.pathname)) {
                // Redirect to login if not authenticated
                window.location.href = '/login';
            }
        })
        .catch(error => {
            console.error('Error verifying session:', error);
            if (!PUBLIC_PATHS.includes(window.location.pathname)) {
                window.location.href = '/login';
            }
        });
}

function updateUserUI() {
    // Add user info to sidebar if available
    const sidebar = document.querySelector('.sidebar-menu');
    if (sidebar && currentUser) {
        const existingAdminLink = document.querySelector('.admin-staff-item');
        if (existingAdminLink) {
            existingAdminLink.remove();
        }

        // Remove existing logout item if present
        const existingLogout = document.querySelector('.logout-item');
        if (existingLogout) {
            existingLogout.remove();
        }
        
        const logoutItem = document.createElement('li');
        logoutItem.className = 'logout-item';
        logoutItem.innerHTML = `
            <a href="#" onclick="logout(); return false;" style="color: #ef4444;">
                <i class="fas fa-sign-out-alt"></i> Logout
            </a>
        `;
        sidebar.appendChild(logoutItem);
    }
}

function logout() {
    fetch('/api/logout', {
        method: 'POST'
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.location.href = '/login';
        }
    })
    .catch(error => {
        console.error('Error logging out:', error);
    });
}

function setupUploadArea() {
    const uploadArea = document.getElementById('uploadArea');
    const imageInput = document.getElementById('imageInput');
    const cameraInput = document.getElementById('cameraInput');
    const cameraOption = document.getElementById('cameraOption');
    const uploadOption = document.getElementById('uploadOption');
    
    if (!imageInput) return;
    
    // Camera option click - Opens the camera modal instead of file input
    if (cameraOption) {
        cameraOption.addEventListener('click', function() {
            openCameraModal();
        });
    }
    
    // Upload option click
    if (uploadOption) {
        uploadOption.addEventListener('click', function() {
            imageInput.click();
        });
    }
    
    // Camera input change
    if (cameraInput) {
        cameraInput.addEventListener('change', function(e) {
            handleFileSelect(e.target.files[0], { mode: 'image' });
        });
    }
    
    // File input change
    imageInput.addEventListener('change', function(e) {
        handleFileSelect(e.target.files[0], { mode: 'image' });
    });
    
    // Drag and drop on upload area
    if (uploadArea) {
        uploadArea.addEventListener('dragover', function(e) {
            e.preventDefault();
            uploadArea.style.backgroundColor = 'rgba(16, 185, 129, 0.1)';
            uploadArea.style.borderColor = '#10b981';
        });
        
        uploadArea.addEventListener('dragleave', function() {
            uploadArea.style.backgroundColor = '';
            uploadArea.style.borderColor = '';
        });
        
        uploadArea.addEventListener('drop', function(e) {
            e.preventDefault();
            uploadArea.style.backgroundColor = '';
            uploadArea.style.borderColor = '';
            if (e.dataTransfer.files.length > 0) {
                handleFileSelect(e.dataTransfer.files[0]);
            }
        });
    }
}

function handleFileSelect(file, options = {}) {
    if (!file) return;
    
    // Validate file type
    const imageTypes = [
        'image/png',
        'image/jpeg',
        'image/jpg'
    ];

    const videoTypes = [
        'video/mp4',
        'video/quicktime',
        'video/x-msvideo',
        'video/x-matroska',
        'video/webm'
    ];

    const allowedTypes = options.mode === 'image'
        ? imageTypes
        : [...imageTypes, ...videoTypes];

    if (!allowedTypes.includes(file.type)) {
        const errorMessage = options.mode === 'image'
            ? 'Invalid file type. Please upload PNG, JPG, or JPEG only.'
            : 'Invalid file type. Please upload PNG, JPG, JPEG, MP4, MOV, AVI, MKV, or WEBM.';
        showNotification(errorMessage, 'error');
        return;
    }
    
    // Validate file size (200MB)
    if (file.size > 200 * 1024 * 1024) {
        showNotification('File too large. Maximum size is 200MB.', 'error');
        return;
    }
    
    selectedFile = file;
    
    // Show preview (image or video)
    const imagePreview = document.getElementById('imagePreview');
    const videoPreview = document.getElementById('videoPreview');
    const isVideo = file.type.startsWith('video/');

    if (isVideo) {
        imagePreview.style.display = 'none';
        videoPreview.style.display = 'block';
        videoPreview.src = URL.createObjectURL(file);
    } else {
        videoPreview.pause();
        videoPreview.removeAttribute('src');
        videoPreview.load();
        videoPreview.style.display = 'none';
        imagePreview.style.display = 'block';

        const reader = new FileReader();
        reader.onload = function(e) {
            imagePreview.src = e.target.result;
        };
        reader.readAsDataURL(file);
    }

    document.getElementById('uploadArea').style.display = 'none';
    document.getElementById('previewContainer').style.display = 'block';
}

function cancelUpload() {
    selectedFile = null;
    const videoPreview = document.getElementById('videoPreview');
    if (videoPreview) {
        videoPreview.pause();
        videoPreview.removeAttribute('src');
        videoPreview.load();
        videoPreview.style.display = 'none';
    }
    document.getElementById('uploadArea').style.display = 'block';
    document.getElementById('previewContainer').style.display = 'none';
    document.getElementById('resultsSection').style.display = 'none';
    document.getElementById('imageInput').value = '';
}

async function detectDisease() {
    if (!selectedFile) {
        showNotification('Please select a photo or video first.', 'error');
        return;
    }
    
    // Show loading
    document.getElementById('loadingIndicator').style.display = 'block';
    document.getElementById('previewContainer').style.display = 'none';
    
    const formData = new FormData();
    formData.append('image', selectedFile);
    
    try {
        const response = await fetch('/api/detect', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || result.message || 'Detection failed');
        }

        detectionResults = result;
        
        // Hide loading and show results
        document.getElementById('loadingIndicator').style.display = 'none';
        displayResults(result);
        
        // Reload stats
        loadStats();
        
        showNotification('Detection completed successfully!', 'success');
        
    } catch (error) {
        document.getElementById('loadingIndicator').style.display = 'none';
        document.getElementById('previewContainer').style.display = 'block';
        showNotification('Error during detection: ' + error.message, 'error');
    }
}

function displayResults(result) {
    const resultsSection = getResultsSection(true);
    if (!resultsSection) return;
    resultsSection.style.display = 'block';

    if (result.not_pineapple || result.error === 'Not a pineapple image. Disease detection skipped.') {
        resultsSection.innerHTML = `
            <h2>Detection Result</h2>
            <div class="result-card">
                <div class="error sensor-disconnected" style="margin-top: 0;">
                    <i class="fas fa-leaf"></i>
                    <div class="error-content">
                        <div class="error-title">Not a Pineapple Image</div>
                        <div class="error-message">${escapeHtml(result.error || 'Please upload a pineapple leaf or fruit image so the disease detector can analyze it.')}</div>
                    </div>
                </div>
            </div>
        `;
        resultsSection.scrollIntoView({ behavior: 'smooth' });
        return;
    }
    
    // Set disease name
    const diseaseBadge = document.getElementById('diseaseBadge');
    const diseaseName = document.getElementById('diseaseName');
    diseaseName.textContent = result.disease;
    
    // Set badge color
    if (result.disease === 'Healthy') {
        diseaseBadge.className = 'disease-badge healthy';
    } else {
        diseaseBadge.className = 'disease-badge diseased';
    }
    
    // Set confidence
    const confidenceValue = document.getElementById('confidenceValue');
    const confidence = Math.round(result.confidence * 100);
    confidenceValue.textContent = confidence + '%';
    
    // Set confidence circle color
    const confidenceCircle = document.getElementById('confidenceCircle');
    if (confidence >= 80) {
        confidenceCircle.style.color = '#27ae60';
    } else if (confidence >= 60) {
        confidenceCircle.style.color = '#f39c12';
    } else {
        confidenceCircle.style.color = '#e74c3c';
    }
    
    // Set recommendations
    if (result.recommendations) {
        document.getElementById('severityLevel').textContent = result.recommendations.severity;
        document.getElementById('actionRequired').textContent = result.recommendations.action;
        displayImmediateAction(result);
        
        // Treatments
        const treatmentList = document.getElementById('treatmentList');
        treatmentList.innerHTML = '';
        result.recommendations.treatments.forEach(treatment => {
            const li = document.createElement('li');
            li.textContent = treatment;
            treatmentList.appendChild(li);
        });
        
        // Recommendations
        const recommendationsList = document.getElementById('recommendationsList');
        recommendationsList.innerHTML = '';
        result.recommendations.recommendations.forEach(rec => {
            const li = document.createElement('li');
            li.textContent = rec;
            recommendationsList.appendChild(li);
        });
        
    }
    
    // Scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth' });
}

function displayImmediateAction(result) {
    const section = document.getElementById('immediateActionSection');
    const titleEl = document.getElementById('immediateActionTitle');
    const listEl = document.getElementById('immediateActionList');

    if (!section || !titleEl || !listEl) return;

    const disease = (result.disease || '').toLowerCase();
    const severity = ((result.recommendations && result.recommendations.severity) || '').toLowerCase();

    const playbook = buildImmediateActionPlaybook(disease, severity, result);

    titleEl.textContent = playbook.title;
    listEl.innerHTML = '';

    playbook.steps.forEach(step => {
        const li = document.createElement('li');
        li.innerHTML = `<i class="fas fa-check-circle"></i> ${step}`;
        listEl.appendChild(li);
    });

    section.classList.remove('action-low', 'action-medium', 'action-high');
    section.classList.add(playbook.levelClass);
}

function buildImmediateActionPlaybook(disease, severity, result) {
    const general = {
        title: 'Do this now',
        steps: [
            'Separate the affected plant from healthy plants if possible.',
            'Inspect nearby plants for the same symptoms today.',
            'Avoid watering the crown and keep the area well-drained.',
        ],
        levelClass: 'action-medium'
    };

    if (result.not_pineapple) {
        return {
            title: 'Upload a pineapple image next time',
            steps: [
                'Use a clear pineapple leaf, crown, or fruit image.',
                'Make sure the plant fills most of the frame.',
                'Avoid blurry or non-pineapple photos so the detector can help you faster.'
            ],
            levelClass: 'action-low'
        };
    }

    if (disease.includes('healthy')) {
        return {
            title: 'Plant looks healthy - keep monitoring',
            steps: [
                'Continue regular monitoring every 2-3 days.',
                'Keep fertilizer and watering on schedule.',
                'Watch for early discoloration, soft spots, or wilting.'
            ],
            levelClass: 'action-low'
        };
    }

    if (disease.includes('fruit_rot')) {
        return {
            title: 'Act now to stop Fruit Rot',
            steps: [
                'Remove the infected fruit or plant part immediately.',
                'Disinfect tools before touching another plant.',
                'Reduce moisture and check for standing water around the roots.',
                'Apply the recommended fungicide only if your local agronomist confirms it.'
            ],
            levelClass: severity === 'high' ? 'action-high' : 'action-medium'
        };
    }

    if (disease.includes('crownrot') || disease.includes('crown_rot')) {
        return {
            title: 'Act now to stop Crown Rot',
            steps: [
                'Cut away infected tissue if safe to do so and isolate the plant.',
                'Improve drainage immediately and stop overhead watering.',
                'Inspect nearby plants for crown softness or bad smell.',
                'Use treatment guidance from an agricultural expert before spraying.'
            ],
            levelClass: severity === 'high' ? 'action-high' : 'action-medium'
        };
    }

    if (disease.includes('mealybug')) {
        return {
            title: 'Control pests now',
            steps: [
                'Check leaf bases and undersides for mealybugs.',
                'Remove heavily infested parts and isolate the plant.',
                'Use approved insect control and monitor neighboring plants closely.'
            ],
            levelClass: severity === 'high' ? 'action-high' : 'action-medium'
        };
    }

    if (disease.includes('rootrot') || disease.includes('root_rot')) {
        return {
            title: 'Fix root conditions immediately',
            steps: [
                'Stop watering until the soil drains better.',
                'Loosen compacted soil and remove standing water.',
                'Check root zone for decay and isolate the worst plants first.'
            ],
            levelClass: severity === 'high' ? 'action-high' : 'action-medium'
        };
    }

    return {
        title: 'Do this now',
        steps: general.steps,
        levelClass: severity === 'high' ? 'action-high' : general.levelClass
    };
}

async function loadStats() {
    const counters = ['totalDetections', 'healthyCount', 'diseaseCount']
        .map(id => document.getElementById(id));
    if (counters.some(counter => !counter)) return;
    try {
        const response = await fetch('/api/stats');
        if (!response.ok) throw new Error('Detection statistics are unavailable');
        const data = await response.json();
        
        document.getElementById('totalDetections').textContent = data.total_detections;
        document.getElementById('healthyCount').textContent = data.disease_count['Healthy'] || 0;
        
        const diseaseCount = data.total_detections - (data.disease_count['Healthy'] || 0);
        document.getElementById('diseaseCount').textContent = diseaseCount;
        const description = data.data_source === 'local'
            ? 'Showing locally saved detections.'
            : data.data_source === 'mixed' ? 'Showing cloud and locally saved detections.'
            : 'Showing saved cloud detections.';
        counters.forEach(counter => { counter.title = description; });
        
    } catch (error) {
        counters.forEach(counter => {
            counter.textContent = '\u2014';
            counter.title = 'Unable to load detection statistics. Please try again.';
        });
        console.error('Error loading stats:', error);
    }
}

async function loadDiseases() {
    try {
        const response = await fetch('/api/diseases');
        const data = await response.json();
        
        const diseasesGrid = document.getElementById('diseasesGrid');
        if (!diseasesGrid) return;
        
        diseasesGrid.innerHTML = '';
        
        data.diseases.forEach(disease => {
            const card = createDiseaseCard(disease);
            diseasesGrid.appendChild(card);
        });
        
    } catch (error) {
        console.error('Error loading diseases:', error);
    }
}

function createDiseaseCard(disease) {
    const card = document.createElement('div');
    card.className = 'disease-card';
    
    const icon = disease.name === 'Healthy' ? 
        '<i class="fas fa-check-circle" style="color: #27ae60;"></i>' : 
        '<i class="fas fa-virus" style="color: #e74c3c;"></i>';
    
    card.innerHTML = `
        <h3>${icon} ${disease.name}</h3>
        <p class="scientific-name">${disease.scientific_name}</p>
        
        <h4>Symptoms:</h4>
        <ul>
            ${disease.symptoms.map(s => `<li>${s}</li>`).join('')}
        </ul>
        
        <h4>Treatment:</h4>
        <ul>
            ${disease.treatment.map(t => `<li>${t}</li>`).join('')}
        </ul>
        
        <h4>Prevention:</h4>
        <ul>
            ${disease.prevention.map(p => `<li>${p}</li>`).join('')}
        </ul>
    `;
    
    return card;
}

function showNotification(message, type = 'info') {
    // Simple notification - you can enhance this with a proper notification library
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: calc(72px + env(safe-area-inset-top));
        right: 16px;
        left: auto;
        width: min(360px, calc(100vw - 32px));
        padding: 1rem 2rem;
        background: ${type === 'error' ? '#e74c3c' : type === 'success' ? '#27ae60' : '#3498db'};
        color: white;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        z-index: 1000;
        animation: slideIn 0.3s ease;
    `;
    notification.textContent = message;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => {
            document.body.removeChild(notification);
        }, 300);
    }, 3000);
}

// Camera Functions
let cameraStream = null;
let cameraDevices = [];
let activeCameraDeviceId = null;
let preferredFacingMode = 'environment';

function stopCameraStream() {
    if (!cameraStream) {
        return;
    }

    cameraStream.getTracks().forEach(track => track.stop());
    cameraStream = null;
}

async function refreshCameraDevices() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
        cameraDevices = [];
        return;
    }

    const devices = await navigator.mediaDevices.enumerateDevices();
    cameraDevices = devices.filter(device => device.kind === 'videoinput');
}

function updateSwitchCameraButton() {
    const switchBtn = document.getElementById('switchCameraBtn');
    if (!switchBtn) {
        return;
    }

    const canSwitch = cameraDevices.length > 1;
    switchBtn.style.display = canSwitch ? 'inline-flex' : 'none';
    switchBtn.disabled = !canSwitch;
}

async function startCameraStream() {
    const video = document.getElementById('cameraStream');

    stopCameraStream();

    let constraints = {
        video: {
            facingMode: { ideal: preferredFacingMode },
            width: { ideal: 1280 },
            height: { ideal: 720 }
        }
    };

    if (activeCameraDeviceId) {
        constraints.video.deviceId = { exact: activeCameraDeviceId };
    }

    try {
        cameraStream = await navigator.mediaDevices.getUserMedia(constraints);
    } catch (error) {
        cameraStream = await navigator.mediaDevices.getUserMedia({ video: true });
    }

    video.srcObject = cameraStream;
    await video.play();

    const track = cameraStream.getVideoTracks()[0];
    const settings = track ? track.getSettings() : {};
    if (settings.deviceId) {
        activeCameraDeviceId = settings.deviceId;
    }
    if (settings.facingMode) {
        preferredFacingMode = settings.facingMode;
    }

    await refreshCameraDevices();
    updateSwitchCameraButton();
}

function openCameraModal() {
    const modal = document.getElementById('cameraModal');
    const errorDiv = document.getElementById('cameraError');
    
    modal.style.display = 'flex';
    errorDiv.style.display = 'none';

    startCameraStream().catch(error => {
        console.error('Error accessing camera:', error);
        errorDiv.style.display = 'block';
        
        let errorMessage = 'Error accessing camera. Please check permissions or try a different browser.';
        
        // Detect iOS HTTPS requirement
        if (error.name === 'NotAllowedError') {
            const isHTTP = window.location.protocol === 'http:';
            const isLocalhost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
            
            if (isHTTP && !isLocalhost) {
                errorMessage = '🔒 HTTPS Required: iOS Safari blocks camera access on HTTP. Use HTTPS or access via: ngrok or localhost';
            } else {
                errorMessage = 'Camera permission denied. Please grant camera access in browser settings.';
            }
        } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
            errorMessage = 'No camera device found. Please check your device has a camera.';
        } else if (error.name === 'NotReadableError') {
            errorMessage = 'Camera is in use by another app. Please close other apps using the camera.';
        } else if (error.name === 'SecurityError') {
            errorMessage = '🔒 HTTPS Required: This device blocks camera access on insecure connections. Use HTTPS instead of HTTP.';
        }
        
        errorDiv.querySelector('p').textContent = errorMessage;
        showNotification(errorMessage, 'error');
    });
}

function switchCamera() {
    if (cameraDevices.length < 2) {
        showNotification('Only one camera is available on this device.', 'info');
        return;
    }

    const currentIndex = cameraDevices.findIndex(device => device.deviceId === activeCameraDeviceId);
    const nextIndex = currentIndex >= 0 ? (currentIndex + 1) % cameraDevices.length : 0;
    activeCameraDeviceId = cameraDevices[nextIndex].deviceId;

    startCameraStream().catch(error => {
        console.error('Error switching camera:', error);
        showNotification('Unable to switch camera right now.', 'error');
    });
}

function closeCameraModal() {
    const modal = document.getElementById('cameraModal');
    const video = document.getElementById('cameraStream');
    
    stopCameraStream();
    
    video.srcObject = null;
    modal.style.display = 'none';
}

function capturePhoto() {
    const video = document.getElementById('cameraStream');
    const canvas = document.getElementById('cameraCanvas');
    const ctx = canvas.getContext('2d');
    
    // Set canvas size to match video
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    
    // Draw current video frame to canvas
    ctx.drawImage(video, 0, 0);
    
    // Convert canvas to blob and create file
    canvas.toBlob(blob => {
        const file = new File([blob], `capture-${Date.now()}.jpg`, { type: 'image/jpeg' });
        
        // Close camera modal
        closeCameraModal();
        
        // Handle the file as if it was selected
        handleFileSelect(file);
        
        showNotification('Photo captured successfully!', 'success');
    }, 'image/jpeg', 0.95);
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// ============================================
// NEW FEATURES: BATCH, TRENDS, EXPORT, WEATHER, LANGUAGE
// ============================================

let currentLanguage = 'en';

// Setup event listeners for new upload options
document.addEventListener('DOMContentLoaded', function() {
    // Batch upload
    const batchOption = document.getElementById('batchOption');
    const batchInput = document.getElementById('batchInput');
    if (batchOption && batchInput) {
        batchOption.addEventListener('click', () => batchInput.click());
        batchInput.addEventListener('change', handleBatchUpload);
    }

    // Video upload
    const videoOption = document.getElementById('videoOption');
    const videoInput = document.getElementById('videoInput');
    if (videoOption && videoInput) {
        videoOption.addEventListener('click', () => videoInput.click());
        videoInput.addEventListener('change', handleVideoUpload);
    }

    // Load weather alerts on page load (shows a small banner, no scrolling).
    // Do NOT auto-load the risk map here: showRiskMap() force-displays the
    // Spread Risk section AND scrolls the page into it, which is only meant
    // to happen when the user clicks "Spread Risk" in the sidebar. Calling it
    // on every page load was the cause of the dashboard appearing to auto
    // scroll down to Spread Risk after every login/refresh.
    loadWeatherRecommendations();
});

// ============================================
// BATCH UPLOAD
// ============================================
async function handleBatchUpload(event) {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    if (files.length < 2) {
        showNotification('Batch upload requires at least 2 images.', 'error');
        event.target.value = '';
        return;
    }

    const formData = new FormData();
    for (let file of files) {
        formData.append('files', file);
    }

    try {
        showNotification(`Processing ${files.length} images...`, 'info');
        
        const response = await fetch('/api/detect-batch', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (response.ok && data.results.length > 0) {
            displayBatchResults(data);
        } else {
            showNotification(data.error || 'Batch detection failed', 'error');
        }
    } catch (error) {
        console.error('Batch upload error:', error);
        showNotification('Error uploading batch: ' + error.message, 'error');
    }
}

function displayBatchResults(data) {
    const resultsSection = getResultsSection();
    if (!resultsSection) return;

    let html = `
        <h2>Batch Detection Results</h2>
        <div style="margin-bottom: 20px;">
            <p><strong>Processed: ${data.batch_count} images</strong></p>
    `;

    if (data.errors && data.errors.length > 0) {
        html += `<p style="color: #ef4444;"><strong>Errors: ${data.error_count}</strong></p>`;
    }

    html += '</div><div class="batch-results">';

    data.results.forEach((result, index) => {
        html += `
            <div class="batch-result-card">
                <h3>${index + 1}. ${escapeHtml(result.disease)}</h3>
                <p>Confidence: ${(result.confidence * 100).toFixed(1)}%</p>
                <p>Method: ${escapeHtml(result.method)}</p>
            </div>
        `;
    });

    html += '</div>';
    resultsSection.innerHTML = html;
    resultsSection.style.display = 'block';
}

// ============================================
// VIDEO UPLOAD
// ============================================
async function handleVideoUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        showNotification('Processing video... This may take a moment', 'info');
        
        const response = await fetch('/api/detect-video', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (response.ok) {
            displayVideoResults(data);
        } else {
            showNotification('Video detection failed: ' + data.error, 'error');
        }
    } catch (error) {
        console.error('Video upload error:', error);
        showNotification('Error uploading video: ' + error.message, 'error');
    }
}

function displayVideoResults(result) {
    const resultsSection = getResultsSection();
    if (!resultsSection) return;

    let html = `
        <h2>Video Analysis Results</h2>
        <div class="result-card">
            <div class="result-header">
                <div class="disease-badge">
                    <i class="fas fa-virus"></i>
                    <span>${escapeHtml(result.disease)}</span>
                </div>
                <div class="confidence-score">
                    <div class="confidence-circle">
                        <span>${(result.confidence * 100).toFixed(1)}%</span>
                    </div>
                </div>
            </div>
            <div class="result-details">
                <p><strong>Frames Analyzed:</strong> ${result.frame_count}</p>
                <p><strong>Detection Method:</strong> ${escapeHtml(result.method)}</p>
                <p><strong>Disease Distribution:</strong></p>
                <ul>
    `;

    for (const [disease, count] of Object.entries(result.disease_distribution)) {
        html += `<li>${escapeHtml(disease)}: ${Number(count)} frames</li>`;
    }

    html += `</ul></div></div>`;
    
    resultsSection.innerHTML = html;
    resultsSection.style.display = 'block';

    loadStats();
}

// ============================================
// TRENDS & ANALYTICS
// ============================================
async function showTrends() {
    try {
        const response = await fetch('/api/trends?days=30');
        if (response.status === 204) {
            showNotification('No trend data available yet', 'info');
            return;
        }

        const data = await response.json();

        if (!data || response.status !== 200) {
            showNotification(data && data.message ? data.message : 'No trend data available yet', 'info');
            return;
        }

        if (data.total_detections === 0) {
            showNotification(data.message || 'No trend data available yet', 'info');
        }

        const trendsSection = document.getElementById('trendsSection');
        if (!trendsSection) return;

        trendsSection.style.display = 'block';
        document.getElementById('trendTotal').textContent = data.total_detections || 0;
        document.getElementById('trendDiseases').textContent = data.unique_diseases || 0;

        // Scroll to trends section
        trendsSection.scrollIntoView({ behavior: 'smooth' });

    } catch (error) {
        console.error('Error loading trends:', error);
        showNotification('Failed to load trends', 'error');
    }
}

// ============================================
// EXPORT FUNCTIONALITY
// ============================================
async function exportCSV() {
    try {
        showNotification('Generating CSV report...', 'info');
        
        const response = await fetch('/api/export/csv?limit=1000');
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `agripinya_report_${new Date().toISOString().split('T')[0]}.csv`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            showNotification('CSV exported successfully', 'success');
        } else {
            const errorData = await response.json().catch(() => ({}));
            showNotification(errorData.error || 'Failed to export CSV', 'error');
        }
    } catch (error) {
        console.error('CSV export error:', error);
        showNotification('Error exporting CSV: ' + error.message, 'error');
    }
}

async function exportPDF() {
    try {
        showNotification('Generating PDF report...', 'info');
        
        const response = await fetch('/api/export/pdf?limit=100');
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `agripinya_report_${new Date().toISOString().split('T')[0]}.pdf`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            showNotification('PDF exported successfully', 'success');
        } else {
            const errorData = await response.json().catch(() => ({}));
            showNotification(errorData.error || 'Failed to export PDF', 'error');
        }
    } catch (error) {
        console.error('PDF export error:', error);
        showNotification('Error exporting PDF: ' + error.message, 'error');
    }
}

// ============================================
// WEATHER-BASED RECOMMENDATIONS
// ============================================
async function loadWeatherRecommendations() {
    try {
        const response = await fetch('/api/weather-recommendations');
        
        if (response.status === 204) {
            return; // No sensor data available
        }

        const data = await response.json();
        
        if (data.error || data.available === false || response.status !== 200) {
            return;
        }

        displayWeatherAlert(data);

    } catch (error) {
        console.error('Error loading weather recommendations:', error);
    }
}

function displayWeatherAlert(data) {
    const section = document.getElementById('weatherAlertSection');
    const content = document.getElementById('weatherAlertContent');
    
    if (!section || !content) return;

    let alertClass = 'alert-info';
    if (data.risk_level === 'high') {
        alertClass = 'alert-danger';
    } else if (data.risk_level === 'medium') {
        alertClass = 'alert-warning';
    }

    let html = `
        <p><strong>Temperature:</strong> ${data.current_temperature}°C | <strong>Humidity:</strong> ${data.current_humidity}%</p>
        <p><strong>Spray Conditions:</strong> ${data.spray_conditions.toUpperCase()}</p>
        <p><strong>Risk Level:</strong> ${data.risk_level.toUpperCase()}</p>
        <h4>Actions:</h4>
        <ul>
    `;

    data.actions.forEach(action => {
        html += `<li>${action}</li>`;
    });

    html += '</ul>';

    if (data.warnings && data.warnings.length > 0) {
        html += '<h4>⚠️ Warnings:</h4><ul>';
        data.warnings.forEach(warning => {
            html += `<li style="color: #ef4444;">${warning}</li>`;
        });
        html += '</ul>';
    }

    content.innerHTML = html;
    section.className = `alert-section alert ${alertClass}`;
    section.style.display = 'block';
}

// ============================================
// DISEASE SPREAD RISK MAP
// ============================================
async function showRiskMap() {
    try {
        const response = await fetch('/api/disease-spread-risk');
        const data = await response.json();

        const section = document.getElementById('riskMapSection');
        const content = document.getElementById('riskContent');

        if (!section || !content) return;

        let html = `
            <div class="risk-card">
                <h3>Risk Assessment</h3>
                <p><strong>Risk Level:</strong> <span style="font-size: 1.5em; color: 
        `;

        if (data.risk_level === 'critical') {
            html += '#dc2626">CRITICAL</span></p>';
        } else if (data.risk_level === 'high') {
            html += '#ea580c">HIGH</span></p>';
        } else if (data.risk_level === 'medium') {
            html += '#eab308">MEDIUM</span></p>';
        } else {
            html += '#16a34a">LOW</span></p>';
        }

        html += `
                <p><strong>Detections/Day (7-day avg):</strong> ${(data.detections_per_day || 0).toFixed(2)}</p>
                <p><strong>Days to Likely Spread:</strong> ${data.days_to_likely_spread || 'N/A'}</p>
                <p><strong>Recent Detections:</strong> ${data.recent_detection_count || 0}</p>
                <p style="margin-top: 20px; font-size: 0.9em; color: #666;">
                    Based on detection frequency in the last 7 days. Monitor closely if risk is medium or higher.
                </p>
            </div>
        `;

        content.innerHTML = html;
        section.style.display = 'block';
        section.scrollIntoView({ behavior: 'smooth' });

    } catch (error) {
        console.error('Error loading risk map:', error);
        showNotification('Failed to load disease spread risk', 'error');
    }
}


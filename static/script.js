const socket = io();
let uploadedFiles = [];
let dbConfig = {};

// DOM Elements
const dbForm = document.getElementById('db-form');
const testConnectionBtn = document.getElementById('test-connection');
const nextStep1Btn = document.getElementById('next-step1');
const backStep1Btn = document.getElementById('back-step1');
const uploadZone = document.getElementById('upload-zone');
const fileInput = document.getElementById('file-input');
const fileList = document.getElementById('file-list');
const startImportBtn = document.getElementById('start-import');
const newImportBtn = document.getElementById('new-import');

// Step management
function showStep(stepNumber) {
    // Hide all cards
    document.getElementById('database-config').classList.add('hidden');
    document.getElementById('file-upload').classList.add('hidden');
    document.getElementById('import-progress').classList.add('hidden');
    
    // Update step indicators
    document.querySelectorAll('.step').forEach(step => step.classList.remove('active'));
    document.getElementById(`step${stepNumber}`).classList.add('active');
    
    // Show current card
    switch(stepNumber) {
        case 1:
            document.getElementById('database-config').classList.remove('hidden');
            break;
        case 2:
            document.getElementById('file-upload').classList.remove('hidden');
            break;
        case 3:
            document.getElementById('import-progress').classList.remove('hidden');
            break;
    }
}

// Toast notifications
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 5000);
}

// Test database connection
testConnectionBtn.addEventListener('click', async () => {
    const formData = new FormData(dbForm);
    dbConfig = {
        host: document.getElementById('host').value,
        user: document.getElementById('user').value,
        password: document.getElementById('password').value,
        database: document.getElementById('database').value
    };
    
    testConnectionBtn.disabled = true;
    testConnectionBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Testing...';
    
    try {
        const response = await fetch('/test-connection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dbConfig)
        });
        
        const result = await response.json();
        
        if (result.success) {
            showToast('✅ Database connection successful!', 'success');
            nextStep1Btn.disabled = false;
        } else {
            showToast(`❌ Connection failed: ${result.message}`, 'error');
        }
    } catch (error) {
        showToast(`❌ Connection error: ${error.message}`, 'error');
    } finally {
        testConnectionBtn.disabled = false;
        testConnectionBtn.innerHTML = '<i class="fas fa-plug"></i> Test Connection';
    }
});

// Step navigation
nextStep1Btn.addEventListener('click', () => showStep(2));
backStep1Btn.addEventListener('click', () => showStep(1));

// File upload handling
uploadZone.addEventListener('click', () => fileInput.click());
uploadZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadZone.classList.add('dragover');
});
uploadZone.addEventListener('dragleave', () => {
    uploadZone.classList.remove('dragover');
});
uploadZone.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadZone.classList.remove('dragover');
    handleFiles(e.dataTransfer.files);
});

fileInput.addEventListener('change', (e) => {
    handleFiles(e.target.files);
});

function handleFiles(files) {
    const formData = new FormData();
    
    Array.from(files).forEach(file => {
        if (file.type === 'text/csv' || file.name.endsWith('.csv')) {
            formData.append('files', file);
        }
    });
    
    if (formData.has('files')) {
        uploadFiles(formData);
    } else {
        showToast('Please select CSV files only', 'error');
    }
}

async function uploadFiles(formData) {
    try {
        const response = await fetch('/upload-files', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            uploadedFiles = result.files;
            displayFiles();
            startImportBtn.disabled = false;
            showToast(`✅ ${result.files.length} files uploaded successfully!`, 'success');
        } else {
            showToast(`❌ Upload failed: ${result.message}`, 'error');
        }
    } catch (error) {
        showToast(`❌ Upload error: ${error.message}`, 'error');
    }
}

function displayFiles() {
    fileList.innerHTML = '';
    
    uploadedFiles.forEach((file, index) => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.innerHTML = `
            <div class="file-info">
                <div class="file-icon">
                    <i class="fas fa-file-csv"></i>
                </div>
                <div class="file-details">
                    <h4>${file.filename}</h4>
                    <p>Will be imported to table: <strong>${file.table_name}</strong></p>
                </div>
            </div>
            <input type="text" class="table-input" value="${file.table_name}" 
                   onchange="updateTableName(${index}, this.value)">
        `;
        fileList.appendChild(fileItem);
    });
}

function updateTableName(index, newName) {
    uploadedFiles[index].table_name = newName;
}

// Start import process
startImportBtn.addEventListener('click', () => {
    showStep(3);
    initializeProgress();
    
    socket.emit('start_import', {
        ...dbConfig,
        files: uploadedFiles
    });
});

function initializeProgress() {
    const progressList = document.getElementById('file-progress-list');
    progressList.innerHTML = '';
    
    uploadedFiles.forEach(file => {
        const progressItem = document.createElement('div');
        progressItem.className = 'file-progress-item';
        progressItem.id = `progress-${file.table_name}`;
        progressItem.innerHTML = `
            <div class="file-progress-header">
                <h4>${file.filename} → ${file.table_name}</h4>
                <span class="status-badge status-processing">Waiting...</span>
            </div>
            <div class="progress-bar">
                <div class="progress-fill"></div>
            </div>
            <div class="progress-text">Ready to process</div>
        `;
        progressList.appendChild(progressItem);
    });
}

// Socket event handlers
socket.on('import_started', (data) => {
    showToast('🚀 Import process started!', 'success');
});

socket.on('file_started', (data) => {
    const progressItem = document.getElementById(`progress-${data.table_name}`);
    const badge = progressItem.querySelector('.status-badge');
    const text = progressItem.querySelector('.progress-text');
    
    badge.textContent = 'Processing';
    badge.className = 'status-badge status-processing';
    text.textContent = 'Creating table...';
});

socket.on('table_created', (data) => {
    const progressItem = document.getElementById(`progress-${data.table_name}`);
    const text = progressItem.querySelector('.progress-text');
    text.textContent = 'Table created, importing data...';
});

socket.on('progress', (data) => {
    const progressItem = document.getElementById(`progress-${data.table_name}`);
    const text = progressItem.querySelector('.progress-text');
    text.textContent = `Loaded ${data.rows_loaded.toLocaleString()} rows${data.errors ? ` (${data.errors} errors)` : ''}`;
});

socket.on('file_completed', (data) => {
    const progressItem = document.getElementById(`progress-${data.table_name}`);
    const badge = progressItem.querySelector('.status-badge');
    const fill = progressItem.querySelector('.progress-fill');
    const text = progressItem.querySelector('.progress-text');
    
    badge.textContent = 'Completed';
    badge.className = 'status-badge status-success';
    fill.style.width = '100%';
    text.textContent = `✅ ${data.total_rows.toLocaleString()} rows imported${data.errors ? ` (${data.errors} errors)` : ''}`;
});

socket.on('import_completed', (data) => {
    // Update overall progress
    const overallFill = document.getElementById('overall-progress');
    const overallText = document.getElementById('overall-text');
    
    overallFill.style.width = '100%';
    overallText.textContent = `${data.total} / ${data.total} files completed`;
    
    // Show summary
    document.getElementById('success-count').textContent = data.successful;
    document.getElementById('error-count').textContent = data.failed;
    document.getElementById('total-count').textContent = data.total;
    document.getElementById('import-summary').classList.remove('hidden');
    
    const message = data.failed === 0 ? 
        '🎉 All files imported successfully!' : 
        `⚠️ Import completed with ${data.failed} failures`;
    
    showToast(message, data.failed === 0 ? 'success' : 'error');
});

socket.on('error', (data) => {
    showToast(`❌ Error: ${data.message}`, 'error');
});

// New import
newImportBtn.addEventListener('click', () => {
    uploadedFiles = [];
    dbConfig = {};
    document.getElementById('import-summary').classList.add('hidden');
    nextStep1Btn.disabled = true;
    startImportBtn.disabled = true;
    showStep(1);
});

// Modal functions
function showPrivacyPolicy() {
    document.getElementById('privacy-modal').classList.remove('hidden');
}

function showTerms() {
    document.getElementById('terms-modal').classList.remove('hidden');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.add('hidden');
}

// Close modal when clicking outside
window.onclick = function(event) {
    if (event.target.classList.contains('modal')) {
        event.target.classList.add('hidden');
    }
}

// Analytics tracking (add your Google Analytics ID)
function trackEvent(action, category = 'CSV Import') {
    if (typeof gtag !== 'undefined') {
        gtag('event', action, {
            'event_category': category,
            'event_label': window.location.pathname
        });
    }
}

// Track important events
testConnectionBtn.addEventListener('click', () => {
    trackEvent('test_connection', 'Database');
});

startImportBtn.addEventListener('click', () => {
    trackEvent('start_import', 'CSV Import');
});

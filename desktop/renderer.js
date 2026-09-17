const dropZone = document.getElementById('dropZone');
const statusEl = document.getElementById('status');
const resultEl = document.getElementById('result');
const resultInfo = document.getElementById('resultInfo');
const downloadBtn = document.getElementById('downloadBtn');

let currentJobId = null;
let currentFilename = null;
let dragCounter = 0;

const MAX_FILE_SIZE = 20 * 1024 * 1024; // 20MB
const ALLOWED_EXTENSIONS = ['jpg', 'jpeg', 'png', 'gif', 'bmp'];

// HTML escape to prevent XSS
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Prevent default drag behaviors
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
  dropZone.addEventListener(eventName, preventDefaults, false);
  document.body.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

// Highlight drop zone with counter to prevent flicker
dropZone.addEventListener('dragenter', () => {
  dragCounter++;
  dropZone.classList.add('drag-over');
});

dropZone.addEventListener('dragleave', () => {
  dragCounter--;
  if (dragCounter === 0) {
    dropZone.classList.remove('drag-over');
  }
});

dropZone.addEventListener('drop', () => {
  dragCounter = 0;
  dropZone.classList.remove('drag-over');
});

// Handle dropped files
dropZone.addEventListener('drop', (e) => {
  const files = e.dataTransfer.files;
  if (files.length > 0) {
    const file = files[0];
    
    // Validate file type
    const ext = file.name.split('.').pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      showStatus('error', 'Please drop an image file (JPG, PNG, GIF, BMP)');
      return;
    }
    
    // Validate file size
    if (file.size > MAX_FILE_SIZE) {
      showStatus('error', 'File too large (max 20MB)');
      return;
    }
    
    // Electron provides file.path for local file access
    if (!file.path) {
      showStatus('error', 'Could not read file path');
      return;
    }
    
    handleFile(file.path);
  }
});

// Click to browse
dropZone.addEventListener('click', async () => {
  const result = await window.api.showOpenDialog({
    properties: ['openFile'],
    filters: [
      { name: 'Images', extensions: ALLOWED_EXTENSIONS }
    ]
  });
  
  if (!result.canceled && result.filePaths.length > 0) {
    handleFile(result.filePaths[0]);
  }
});

async function handleFile(filePath) {
  showStatus('processing', 'Uploading and processing...');
  resultEl.classList.remove('show');
  
  const result = await window.api.uploadPhoto(filePath);
  
  if (result.success) {
    // Validate response shape
    if (!result.data || !result.data.job_id) {
      showStatus('error', 'Unexpected server response');
      return;
    }
    
    currentJobId = result.data.job_id;
    currentFilename = result.data.filename || 'model.stl';
    
    const partsCount = result.data.parts_count || (result.data.parts ? result.data.parts.length : 0);
    showStatus('success', `✓ Generated ${partsCount} part(s)`);
    showResult(result.data);
  } else {
    showStatus('error', `✗ Error: ${result.error}`);
  }
}

function showStatus(type, message) {
  statusEl.className = `status show ${type}`;
  statusEl.innerHTML = type === 'processing' 
    ? `<span class="spinner"></span>${escapeHtml(message)}`
    : escapeHtml(message);
}

function showResult(data) {
  const parts = Array.isArray(data.parts) ? data.parts : [];
  const partsCount = data.parts_count || parts.length;
  
  const partsList = parts.map(p => {
    const name = escapeHtml(p.name || 'Unknown');
    const category = escapeHtml(p.category || 'Unknown');
    const width = p.params && p.params.width ? p.params.width.toFixed(1) : '?';
    const height = p.params && p.params.height ? p.params.height.toFixed(1) : '?';
    const depth = p.params && p.params.depth ? p.params.depth.toFixed(1) : '?';
    return `<li><strong>${name}</strong> (${category}) - ${width}×${height}×${depth}mm</li>`;
  }).join('');
  
  resultInfo.innerHTML = `
    <p><strong>Job ID:</strong> ${escapeHtml(data.job_id)}</p>
    <p><strong>Parts generated:</strong> ${partsCount}</p>
    <ul style="margin-top: 10px; padding-left: 20px;">
      ${partsList}
    </ul>
  `;
  
  resultEl.classList.add('show');
}

// Download button
downloadBtn.addEventListener('click', async () => {
  downloadBtn.disabled = true;
  downloadBtn.innerHTML = '<span class="spinner"></span>Downloading...';
  
  const result = await window.api.downloadStl({
    jobId: currentJobId,
    filename: currentFilename
  });
  
  if (result.success) {
    showStatus('success', `✓ Downloaded to ${escapeHtml(result.path)}`);
  } else {
    showStatus('error', `✗ Download failed: ${escapeHtml(result.error)}`);
  }
  
  downloadBtn.disabled = false;
  downloadBtn.innerHTML = 'Download STL Files';
});

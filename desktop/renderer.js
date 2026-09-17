const { ipcRenderer } = require('electron');

const dropZone = document.getElementById('dropZone');
const statusEl = document.getElementById('status');
const resultEl = document.getElementById('result');
const resultInfo = document.getElementById('resultInfo');
const downloadBtn = document.getElementById('downloadBtn');

let currentJobId = null;
let currentFilename = null;

// Prevent default drag behaviors
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
  dropZone.addEventListener(eventName, preventDefaults, false);
  document.body.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

// Highlight drop zone
['dragenter', 'dragover'].forEach(eventName => {
  dropZone.addEventListener(eventName, () => {
    dropZone.classList.add('drag-over');
  }, false);
});

['dragleave', 'drop'].forEach(eventName => {
  dropZone.addEventListener(eventName, () => {
    dropZone.classList.remove('drag-over');
  }, false);
});

// Handle dropped files
dropZone.addEventListener('drop', (e) => {
  const files = e.dataTransfer.files;
  if (files.length > 0) {
    handleFile(files[0]);
  }
});

// Click to browse
dropZone.addEventListener('click', async () => {
  const { dialog } = require('electron').remote;
  const result = await dialog.showOpenDialog({
    properties: ['openFile'],
    filters: [
      { name: 'Images', extensions: ['jpg', 'jpeg', 'png', 'gif', 'bmp'] }
    ]
  });
  
  if (!result.canceled && result.filePaths.length > 0) {
    handleFile(result.filePaths[0]);
  }
});

async function handleFile(filePath) {
  showStatus('processing', 'Uploading and processing...');
  resultEl.classList.remove('show');
  
  const result = await ipcRenderer.invoke('upload-photo', filePath);
  
  if (result.success) {
    currentJobId = result.data.job_id;
    currentFilename = result.data.filename || 'model.stl';
    
    showStatus('success', `✓ Generated ${result.data.parts_count} part(s)`);
    showResult(result.data);
  } else {
    showStatus('error', `✗ Error: ${result.error}`);
  }
}

function showStatus(type, message) {
  statusEl.className = `status show ${type}`;
  statusEl.innerHTML = type === 'processing' 
    ? `<span class="spinner"></span>${message}`
    : message;
}

function showResult(data) {
  const partsList = data.parts.map(p => 
    `<li><strong>${p.name}</strong> (${p.category}) - ${p.params.width}×${p.params.height}×${p.params.depth}mm</li>`
  ).join('');
  
  resultInfo.innerHTML = `
    <p><strong>Job ID:</strong> ${data.job_id}</p>
    <p><strong>Parts generated:</strong> ${data.parts_count}</p>
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
  
  const result = await ipcRenderer.invoke('download-stl', {
    jobId: currentJobId,
    filename: currentFilename
  });
  
  if (result.success) {
    showStatus('success', `✓ Downloaded to ${result.path}`);
  } else {
    showStatus('error', `✗ Download failed: ${result.error}`);
  }
  
  downloadBtn.disabled = false;
  downloadBtn.innerHTML = 'Download STL Files';
});

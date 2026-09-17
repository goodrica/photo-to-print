const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');
const axios = require('axios');
const FormData = require('form-data');

// API endpoint - change this to your VPS URL
const API_URL = process.env.API_URL || 'http://187.124.75.2:8000';

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 800,
    height: 600,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    },
    icon: path.join(__dirname, 'icon.png')
  });

  mainWindow.loadFile('index.html');
  
  // Enable drag and drop
  mainWindow.webContents.on('will-navigate', (e) => e.preventDefault());
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

// Handle file upload
ipcMain.handle('upload-photo', async (event, filePath) => {
  try {
    const formData = new FormData();
    formData.append('file', fs.createReadStream(filePath));
    
    // Send to API
    const response = await axios.post(`${API_URL}/api/upload`, formData, {
      headers: formData.getHeaders(),
      timeout: 120000 // 2 minute timeout for processing
    });
    
    return {
      success: true,
      data: response.data
    };
  } catch (error) {
    return {
      success: false,
      error: error.message
    };
  }
});

// Handle STL download
ipcMain.handle('download-stl', async (event, { jobId, filename }) => {
  try {
    const { filePath } = await dialog.showSaveDialog(mainWindow, {
      defaultPath: filename,
      filters: [
        { name: 'STL Files', extensions: ['stl'] },
        { name: 'All Files', extensions: ['*'] }
      ]
    });
    
    if (!filePath) {
      return { success: false, error: 'Download cancelled' };
    }
    
    // Download from API
    const response = await axios.get(`${API_URL}/api/download/${jobId}`, {
      responseType: 'stream',
      timeout: 60000
    });
    
    const writer = fs.createWriteStream(filePath);
    response.data.pipe(writer);
    
    return new Promise((resolve) => {
      writer.on('finish', () => resolve({ success: true, path: filePath }));
      writer.on('error', (err) => resolve({ success: false, error: err.message }));
    });
  } catch (error) {
    return {
      success: false,
      error: error.message
    };
  }
});

// Handle file drop
ipcMain.on('file-drop', (event, filePaths) => {
  mainWindow.webContents.send('files-dropped', filePaths);
});

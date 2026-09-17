const { contextBridge, ipcRenderer } = require('electron');

// Expose only the needed IPC methods to the renderer
contextBridge.exposeInMainWorld('api', {
  uploadPhoto: (filePath) => ipcRenderer.invoke('upload-photo', filePath),
  downloadStl: (args) => ipcRenderer.invoke('download-stl', args),
  showOpenDialog: (options) => ipcRenderer.invoke('show-open-dialog', options)
});

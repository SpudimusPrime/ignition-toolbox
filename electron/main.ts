import { app, BrowserWindow, ipcMain, dialog, session, Menu } from 'electron';
import * as path from 'path';
import { PythonBackend } from './services/python-backend';
import { registerIpcHandlers } from './ipc/handlers';
import { initAutoUpdater } from './services/auto-updater';
import { openExternalUrl } from './utils/platform';

// Handle creating/removing shortcuts on Windows when installing/uninstalling
if (process.platform === 'win32' && require('electron-squirrel-startup')) {
  app.quit();
}

let mainWindow: BrowserWindow | null = null;
let pythonBackend: PythonBackend | null = null;

const isDev = !app.isPackaged;

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1024,
    minHeight: 768,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    show: false,
    backgroundColor: '#01050d', // Dark background matching Warp theme
  });

  // Show window when ready to prevent visual flash
  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
  });

  // Load the app
  if (isDev) {
    // Development: load from Vite dev server
    mainWindow.loadURL('http://localhost:3000');
    mainWindow.webContents.openDevTools();
  } else {
    // Production: load built frontend
    mainWindow.loadFile(path.join(__dirname, '../frontend/dist/index.html'));
  }

  // Native context menu for editable content (replaces Monaco's DOM menu which
  // dismisses immediately under Electron's sandbox mode)
  mainWindow.webContents.on('context-menu', (_event, params) => {
    const menu = Menu.buildFromTemplate([
      { label: 'Cut',       role: 'cut',       enabled: params.isEditable && params.selectionText.length > 0 },
      { label: 'Copy',      role: 'copy',      enabled: params.selectionText.length > 0 },
      { label: 'Paste',     role: 'paste',     enabled: params.isEditable },
      { type: 'separator' },
      { label: 'Select All', role: 'selectAll', enabled: params.isEditable || params.selectionText.length > 0 },
    ]);
    menu.popup({ window: mainWindow! });
  });

  // Handle external links
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    openExternalUrl(url).catch((err) => {
      console.error('Failed to open external URL:', err);
    });
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

async function startPythonBackend(): Promise<void> {
  pythonBackend = new PythonBackend();

  // Set up crash handler for when backend dies after startup
  pythonBackend.onCrash((crashInfo) => {
    console.error('[Main] Backend crashed after all restart attempts:', crashInfo);

    // Extract useful error info for the user
    let errorDetails = `The backend process crashed and could not be restarted.\n\n`;
    errorDetails += `Exit code: ${crashInfo.exitCode}\n`;
    errorDetails += `Restart attempts: ${crashInfo.restartAttempt + 1}/3\n\n`;

    if (crashInfo.stderr) {
      const lastError = crashInfo.stderr.split('\n').filter(l => l.trim()).slice(-5).join('\n');
      errorDetails += `Last errors:\n${lastError}\n\n`;
    }

    errorDetails += `Possible solutions:\n`;
    errorDetails += `• Check if antivirus is blocking the application\n`;
    errorDetails += `• Try running as Administrator\n`;
    errorDetails += `• Reinstall the application\n`;
    errorDetails += `• Check ${path.join(app.getPath('userData'), 'logs')} for details`;

    dialog.showMessageBox(mainWindow!, {
      type: 'error',
      title: 'Backend Crashed',
      message: 'The backend process has stopped unexpectedly.',
      detail: errorDetails,
      buttons: ['Restart Application', 'Continue Anyway', 'Quit'],
    }).then((result) => {
      if (result.response === 0) {
        // Restart Application
        app.relaunch();
        app.quit();
      } else if (result.response === 2) {
        // Quit
        app.quit();
      }
      // Continue Anyway - do nothing, let user see the broken state
    });
  });

  try {
    await pythonBackend.start();
    console.log(`Python backend started on port ${pythonBackend.getPort()}`);
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error('Failed to start Python backend:', error);
    dialog.showErrorBox(
      'Backend Error',
      `Failed to start the backend.\n\nError: ${errorMessage}\n\nCheck the log file at:\n${path.join(app.getPath('userData'), 'logs')}`
    );
    app.quit();
  }
}

async function stopPythonBackend(): Promise<void> {
  if (pythonBackend) {
    await pythonBackend.stop();
    pythonBackend = null;
  }
}

// App lifecycle
app.whenReady().then(async () => {
  // Set Content Security Policy
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [
          "default-src 'self'; " +
          "script-src 'self' 'unsafe-inline'; " +
          "style-src 'self' 'unsafe-inline'; " +
          "connect-src 'self' http://localhost:* ws://localhost:* http://127.0.0.1:* ws://127.0.0.1:*; " +
          "img-src 'self' data: blob:; " +
          "font-src 'self' data:;"
        ],
      },
    });
  });

  // Start Python backend first
  await startPythonBackend();

  // Register IPC handlers
  registerIpcHandlers(pythonBackend!);

  // Create main window
  createWindow();

  // Initialize auto-updater (only in production)
  if (!isDev && mainWindow) {
    initAutoUpdater(mainWindow);
  }

  app.on('activate', () => {
    // On macOS, re-create window when dock icon is clicked
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', async () => {
  await stopPythonBackend();

  // On macOS, keep app running until explicitly quit
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', async () => {
  await stopPythonBackend();
});

// Handle uncaught exceptions
process.on('uncaughtException', (error) => {
  console.error('Uncaught exception:', error);
});

process.on('unhandledRejection', (reason) => {
  console.error('Unhandled rejection:', reason);
});

// Export for IPC handlers
export function getMainWindow(): BrowserWindow | null {
  return mainWindow;
}

export function getPythonBackend(): PythonBackend | null {
  return pythonBackend;
}

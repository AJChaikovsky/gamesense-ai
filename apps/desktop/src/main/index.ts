import { join, resolve } from 'node:path'
import { BrowserWindow, app, ipcMain, shell } from 'electron'
import { IPC } from '../shared/bridge'
import { EngineProcess } from './engine'

const isDev = !app.isPackaged

const engine = new EngineProcess({
  repoRoot: resolve(app.getAppPath(), '..', '..'),
  isDev,
  resourcesPath: process.resourcesPath
})

function createDashboardWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1100,
    height: 720,
    minWidth: 800,
    minHeight: 560,
    show: false,
    backgroundColor: '#0b0d12',
    title: 'GameSense',
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  })

  win.once('ready-to-show', () => win.show())

  // Open external links in the browser, never inside the app.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) void shell.openExternal(url)
    return { action: 'deny' }
  })

  if (isDev && process.env.ELECTRON_RENDERER_URL) {
    void win.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    void win.loadFile(join(__dirname, '../renderer/index.html'))
  }
  return win
}

app.whenReady().then(() => {
  ipcMain.handle(IPC.engineConnection, () => engine.connection())
  engine.start()
  createDashboardWindow()

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createDashboardWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => engine.stop())

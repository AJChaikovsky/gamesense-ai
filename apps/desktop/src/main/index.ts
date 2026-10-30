import { join, resolve } from 'node:path'
import { BrowserWindow, app, ipcMain, shell } from 'electron'
import { type AppMetrics, IPC } from '../shared/bridge'
import { EngineProcess } from './engine'
import { registerHotkeys, unregisterHotkeys } from './hotkeys'
import { createOverlayWindow } from './overlay'

const isDev = !app.isPackaged
const repoRoot = resolve(app.getAppPath(), '..', '..')

// In dev, read the repo's .env so GAMESENSE_OVERLAY and hotkey overrides work like
// the engine's settings. Real environment variables still win.
if (isDev) {
  try {
    process.loadEnvFile(join(repoRoot, '.env'))
  } catch {
    // no .env: defaults apply
  }
}

const overlayEnabled = process.env.GAMESENSE_OVERLAY !== '0'

const engine = new EngineProcess({
  repoRoot,
  isDev,
  resourcesPath: process.resourcesPath
})

let overlay: BrowserWindow | null = null

function createDashboardWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1100,
    height: 760,
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

function appMetrics(): AppMetrics {
  const metrics = app.getAppMetrics()
  // privateBytes (Windows) excludes memory shared between processes, so it doesn't
  // double-count; other platforms only report the working set.
  const kb = metrics.reduce(
    (sum, m) => sum + (m.memory?.privateBytes ?? m.memory?.workingSetSize ?? 0),
    0
  )
  const cpu = metrics.reduce((sum, m) => sum + (m.cpu?.percentCPUUsage ?? 0), 0)
  return {
    memoryMb: Math.round(kb / 1024),
    cpuPercent: Math.round(cpu * 10) / 10,
    processCount: metrics.length
  }
}

app.whenReady().then(() => {
  ipcMain.handle(IPC.engineConnection, () => engine.connection())
  ipcMain.handle(IPC.appMetrics, () => appMetrics())
  ipcMain.handle(IPC.overlayVisible, (_event, visible: boolean) => {
    if (!overlay || overlay.isDestroyed()) return
    if (visible) overlay.showInactive()
    else overlay.hide()
  })

  engine.start()
  const hotkeyStatus = registerHotkeys()
  ipcMain.handle(IPC.hotkeyStatus, () => hotkeyStatus)
  createDashboardWindow()
  if (overlayEnabled) overlay = createOverlayWindow(isDev)

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createDashboardWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('will-quit', () => unregisterHotkeys())
app.on('before-quit', () => engine.stop())

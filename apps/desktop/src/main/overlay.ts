import { join } from 'node:path'
import { BrowserWindow, screen } from 'electron'

/**
 * A transparent, click-through, always-on-top window covering the primary display.
 *
 * It never takes focus or mouse input, so the game keeps both. Works over windowed
 * and borderless games; exclusive fullscreen games draw over it (see ADR-002).
 */
export function createOverlayWindow(isDev: boolean): BrowserWindow {
  const { bounds } = screen.getPrimaryDisplay()
  const win = new BrowserWindow({
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    transparent: true,
    backgroundColor: '#00000000',
    frame: false,
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    fullscreenable: false,
    focusable: false,
    skipTaskbar: true,
    hasShadow: false,
    alwaysOnTop: true,
    show: false,
    title: 'GameSense Overlay',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false
    }
  })

  win.setAlwaysOnTop(true, 'screen-saver')
  win.setIgnoreMouseEvents(true, { forward: true })
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true })
  win.once('ready-to-show', () => win.showInactive())

  if (isDev && process.env.ELECTRON_RENDERER_URL) {
    void win.loadURL(`${process.env.ELECTRON_RENDERER_URL}/overlay.html`)
  } else {
    void win.loadFile(join(__dirname, '../renderer/overlay.html'))
  }
  return win
}

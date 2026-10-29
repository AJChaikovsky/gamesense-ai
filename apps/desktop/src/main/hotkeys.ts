import { BrowserWindow, globalShortcut } from 'electron'
import { DEFAULT_HOTKEYS, type Hotkey, IPC } from '../shared/bridge'

/** Registers global hotkeys and forwards presses to every renderer. */
export function registerHotkeys(): Record<Hotkey, string> {
  const active = {} as Record<Hotkey, string>
  for (const [name, accelerator] of Object.entries(DEFAULT_HOTKEYS) as [Hotkey, string][]) {
    const ok = globalShortcut.register(accelerator, () => {
      for (const win of BrowserWindow.getAllWindows()) win.webContents.send(IPC.hotkey, name)
    })
    if (ok) active[name] = accelerator
    else console.warn(`[hotkeys] could not register ${accelerator} for ${name} (in use?)`)
  }
  return active
}

export function unregisterHotkeys(): void {
  globalShortcut.unregisterAll()
}

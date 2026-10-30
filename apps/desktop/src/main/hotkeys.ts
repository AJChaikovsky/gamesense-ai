import { BrowserWindow, globalShortcut } from 'electron'
import { DEFAULT_HOTKEYS, type Hotkey, type HotkeyStatus, IPC } from '../shared/bridge'

/** Default shortcuts, with GAMESENSE_HOTKEY_<NAME> environment overrides. */
export function resolveHotkeys(env: NodeJS.ProcessEnv = process.env): Record<Hotkey, string> {
  const keys = { ...DEFAULT_HOTKEYS }
  for (const name of Object.keys(keys) as Hotkey[]) {
    const override = env[`GAMESENSE_HOTKEY_${name.toUpperCase()}`]?.trim()
    if (override) keys[name] = override
  }
  return keys
}

/** Registers global hotkeys and forwards presses to every renderer. Returns what the OS accepted. */
export function registerHotkeys(): Record<Hotkey, HotkeyStatus> {
  const status = {} as Record<Hotkey, HotkeyStatus>
  for (const [name, accelerator] of Object.entries(resolveHotkeys()) as [Hotkey, string][]) {
    let ok = false
    try {
      ok = globalShortcut.register(accelerator, () => {
        console.log(`[hotkeys] ${accelerator} pressed (${name})`)
        for (const win of BrowserWindow.getAllWindows()) win.webContents.send(IPC.hotkey, name)
      })
    } catch (err) {
      console.warn(`[hotkeys] invalid shortcut ${accelerator} for ${name}: ${String(err)}`)
    }
    status[name] = { accelerator, registered: ok }
    if (ok) console.log(`[hotkeys] registered ${accelerator} for ${name}`)
    else console.warn(`[hotkeys] could not register ${accelerator} for ${name} (in use?)`)
  }
  return status
}

export function unregisterHotkeys(): void {
  globalShortcut.unregisterAll()
}

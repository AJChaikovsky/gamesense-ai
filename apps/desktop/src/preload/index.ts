import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'
import {
  type AppMetrics,
  type EngineConnection,
  type GameSenseBridge,
  type Hotkey,
  type HotkeyStatus,
  IPC
} from '../shared/bridge'

const bridge: GameSenseBridge = {
  platform: process.platform,
  getEngineConnection: () => ipcRenderer.invoke(IPC.engineConnection) as Promise<EngineConnection>,
  getAppMetrics: () => ipcRenderer.invoke(IPC.appMetrics) as Promise<AppMetrics>,
  setOverlayVisible: (visible) => ipcRenderer.invoke(IPC.overlayVisible, visible) as Promise<void>,
  onHotkey: (listener) => {
    const handler = (_event: IpcRendererEvent, hotkey: Hotkey): void => listener(hotkey)
    ipcRenderer.on(IPC.hotkey, handler)
    return () => ipcRenderer.removeListener(IPC.hotkey, handler)
  },
  getHotkeyStatus: () =>
    ipcRenderer.invoke(IPC.hotkeyStatus) as Promise<Record<Hotkey, HotkeyStatus>>
}

contextBridge.exposeInMainWorld('gamesense', bridge)

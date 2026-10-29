import { contextBridge, ipcRenderer } from 'electron'
import { type EngineConnection, type GameSenseBridge, IPC } from '../shared/bridge'

const bridge: GameSenseBridge = {
  platform: process.platform,
  getEngineConnection: () => ipcRenderer.invoke(IPC.engineConnection) as Promise<EngineConnection>
}

contextBridge.exposeInMainWorld('gamesense', bridge)

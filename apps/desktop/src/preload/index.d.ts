import type { GameSenseBridge } from '../shared/bridge'

declare global {
  interface Window {
    gamesense: GameSenseBridge
  }
}

export {}

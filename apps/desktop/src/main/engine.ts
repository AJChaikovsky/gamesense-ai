import { type ChildProcess, spawn } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { existsSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { createInterface } from 'node:readline'
import type { EngineConnection } from '../shared/bridge'

interface EngineOptions {
  /** Repository root (dev) used to locate the Python workspace and sample clips. */
  repoRoot: string
  isDev: boolean
  resourcesPath: string
}

/**
 * Launches the Python engine as a child process and reports how to connect to it.
 *
 * The engine binds to 127.0.0.1 on a free port and prints one JSON "ready" line;
 * we pass it a fresh per-launch token so no other local process can use its API.
 */
export class EngineProcess {
  private child: ChildProcess | null = null
  private state: EngineConnection = { status: 'starting' }
  private readonly token = randomBytes(24).toString('base64url')
  private readonly waiters: Array<(c: EngineConnection) => void> = []

  constructor(private readonly options: EngineOptions) {}

  start(): void {
    const { command, args, cwd } = this.command()
    const replay = this.replayPath()
    if (replay) args.push('--replay', replay)

    console.log(`[engine] starting: ${command} ${args.join(' ')}`)
    const child = spawn(command, args, {
      cwd,
      env: { ...process.env, GAMESENSE_TOKEN: this.token, PYTHONUNBUFFERED: '1' },
      stdio: ['ignore', 'pipe', 'pipe'],
      // Own process group on POSIX so stop() also ends uv's python child.
      detached: process.platform !== 'win32',
      windowsHide: true
    })
    this.child = child

    createInterface({ input: child.stdout! }).on('line', (line) => this.onStdout(line))
    child.stderr!.on('data', (chunk: Buffer) => process.stderr.write(`[engine] ${chunk}`))
    child.on('error', (err) => this.settle({ status: 'failed', error: err.message }))
    child.on('exit', (code, signal) => {
      this.child = null
      if (this.state.status !== 'failed') {
        this.settle({ status: 'failed', error: `engine exited (code ${code}, signal ${signal})` })
      }
    })
  }

  connection(): Promise<EngineConnection> {
    if (this.state.status !== 'starting') return Promise.resolve(this.state)
    return new Promise((res) => this.waiters.push(res))
  }

  stop(): void {
    const child = this.child
    if (!child?.pid) return
    this.child = null
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { windowsHide: true })
    } else {
      try {
        process.kill(-child.pid, 'SIGTERM')
      } catch {
        child.kill('SIGTERM')
      }
    }
  }

  private onStdout(line: string): void {
    try {
      const msg = JSON.parse(line) as { event?: string; port?: number }
      if (msg.event === 'ready' && typeof msg.port === 'number') {
        this.settle({ status: 'ready', url: `ws://127.0.0.1:${msg.port}/ws`, token: this.token })
        return
      }
    } catch {
      // not a control line
    }
    console.log(`[engine] ${line}`)
  }

  private settle(next: EngineConnection): void {
    this.state = next
    if (next.status !== 'starting') {
      console.log(`[engine] ${next.status}${next.status === 'failed' ? `: ${next.error}` : ''}`)
      this.waiters.splice(0).forEach((w) => w(next))
    }
  }

  private command(): { command: string; args: string[]; cwd: string } {
    const override = process.env.GAMESENSE_ENGINE_CMD
    if (override) {
      const [command, ...args] = override.split(' ').filter(Boolean)
      return { command, args, cwd: this.options.repoRoot }
    }
    if (this.options.isDev) {
      return {
        command: 'uv',
        args: ['run', '--project', this.options.repoRoot, 'gamesense-engine', '--port', '0'],
        cwd: this.options.repoRoot
      }
    }
    // Packaged builds ship a frozen engine binary (M7).
    const exe = process.platform === 'win32' ? 'gamesense-engine.exe' : 'gamesense-engine'
    return {
      command: join(this.options.resourcesPath, 'engine', exe),
      args: ['--port', '0'],
      cwd: this.options.resourcesPath
    }
  }

  private replayPath(): string | undefined {
    const fromEnv = process.env.GAMESENSE_REPLAY
    if (fromEnv) return resolve(fromEnv)
    if (!this.options.isDev) return undefined
    const sample = join(this.options.repoRoot, 'evals', 'clips', 'sample.mp4')
    return existsSync(sample) ? sample : undefined
  }
}

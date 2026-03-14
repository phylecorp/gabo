/**
 * @decision DEC-DESKTOP-WS-001
 * @title AnalysisWebSocket: callback-based wrapper without auto-reconnect for analysis runs
 * @status accepted
 * @rationale Analysis runs are one-shot: the WebSocket connection lives exactly
 *   as long as the run. Auto-reconnect is configurable but defaults to false for
 *   analysis runs — reconnecting to a completed run would produce stale events.
 *   A callback array (vs EventEmitter) keeps the code dependency-free and makes
 *   cleanup via the returned unsubscribe function explicit.
 */
import type { PipelineEventMessage } from './types'

type EventCallback = (event: PipelineEventMessage) => void

export class AnalysisWebSocket {
  private ws: WebSocket | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private callbacks: EventCallback[] = []
  private disconnectCallbacks: (() => void)[] = []

  constructor(
    private wsUrl: string,
    private autoReconnect: boolean = true
  ) {}

  connect(): void {
    this.ws = new WebSocket(this.wsUrl)

    this.ws.onmessage = (event) => {
      try {
        const msg: PipelineEventMessage = JSON.parse(event.data)
        this.callbacks.forEach(cb => cb(msg))
      } catch (e) {
        console.error('Failed to parse WS message:', e)
      }
    }

    this.ws.onclose = () => {
      // Fire disconnect callbacks before reconnect so listeners always see the close
      this.disconnectCallbacks.forEach(cb => cb())
      if (this.autoReconnect) {
        this.reconnectTimer = setTimeout(() => this.connect(), 2000)
      }
    }

    this.ws.onerror = (err) => {
      console.error('WebSocket error:', err)
    }
  }

  onEvent(callback: EventCallback): () => void {
    this.callbacks.push(callback)
    return () => {
      this.callbacks = this.callbacks.filter(cb => cb !== callback)
    }
  }

  onDisconnect(callback: () => void): () => void {
    this.disconnectCallbacks.push(callback)
    return () => {
      this.disconnectCallbacks = this.disconnectCallbacks.filter(cb => cb !== callback)
    }
  }

  disconnect(): void {
    this.autoReconnect = false
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
    }
    this.ws?.close()
    this.ws = null
    this.disconnectCallbacks = []
  }
}

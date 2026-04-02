/**
 * @decision DEC-DESKTOP-EVENT-LOG-001
 * @title EventLog: auto-scrolling monospace feed of pipeline events
 * @status accepted
 * @rationale Analysts need real-time visibility into what the pipeline is doing.
 *   A fixed-height scrollable log styled like a terminal output provides the
 *   right mental model — this is structured process output, not prose.
 *   Auto-scroll to bottom ensures the latest events are always visible.
 *   useEffect on events.length (not events reference) prevents thrash when the
 *   parent re-renders for unrelated reasons.
 */
import { useEffect, useRef } from 'react'
import type { PipelineEventMessage } from '../../api/types'

interface EventLogProps {
  events: PipelineEventMessage[]
}

function formatEvent(event: PipelineEventMessage): { text: string; colorClass: string } {
  const d = event.data
  switch (event.type) {
    case 'StageStarted':
      return {
        text: `▸ Starting ${d.technique_name || d.stage || d.technique_id || 'stage'}...`,
        colorClass: 'event-cyan',
      }
    case 'StageCompleted': {
      const dur = d.duration_seconds != null ? ` (${Number(d.duration_seconds).toFixed(1)}s)` : ''
      return {
        text: `✓ ${d.technique_name || d.stage || d.technique_id || 'stage'} completed${dur}`,
        colorClass: 'event-green',
      }
    }
    case 'ResearchStarted': {
      const providers = Array.isArray(d.provider_names) ? d.provider_names.join(', ') : ''
      return {
        text: `▸ Research: querying ${providers || 'providers'}...`,
        colorClass: 'event-cyan',
      }
    }
    case 'ProviderStarted':
      return {
        text: `  ▸ ${d.name}: connecting...`,
        colorClass: 'event-cyan',
      }
    case 'ProviderCompleted': {
      const count = d.citation_count != null ? ` ${d.citation_count} citations` : ''
      return {
        text: `  ✓ ${d.name}:${count}`,
        colorClass: 'event-green',
      }
    }
    case 'ProviderFailed':
      return {
        text: `  ✗ ${d.name}: failed — ${d.error || 'unknown error'}`,
        colorClass: 'event-red',
      }
    case 'ProviderPolling': {
      const pct = (d.max_attempts as number) > 0 ? Math.round(((d.attempt as number) / (d.max_attempts as number)) * 100) : 0
      const statusStr = d.status ? ` [${d.status}]` : ''
      return {
        text: `  ↻ ${d.name}: polling ${d.attempt}/${d.max_attempts} (${pct}%)${statusStr}`,
        colorClass: 'event-muted',
      }
    }
    case 'ResearchCompleted':
      return {
        text: `✓ Research phase complete`,
        colorClass: 'event-green',
      }
    case 'ArtifactWritten':
      return {
        text: `  → artifact: ${d.path || ''}`,
        colorClass: 'event-muted',
      }
    case 'run_completed':
      return {
        text: `✓ Analysis complete → ${d.output_dir || ''}`,
        colorClass: 'event-green',
      }
    case 'run_failed':
      return {
        text: `✗ FAILED: ${d.error || 'unknown error'}`,
        colorClass: 'event-red',
      }
    default:
      return {
        text: `  ${event.type}: ${JSON.stringify(d)}`,
        colorClass: 'event-muted',
      }
  }
}

function formatTimestamp(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return ts.slice(11, 19) || ''
  }
}

export default function EventLog({ events }: EventLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  return (
    <div className="event-log">
      <div className="event-log-header">
        <span className="event-log-title">PIPELINE LOG</span>
        <span className="event-log-count">{events.length} events</span>
      </div>
      <div className="event-log-feed">
        {events.length === 0 ? (
          <span className="event-log-empty">Waiting for pipeline events...</span>
        ) : (
          events.map((event, i) => {
            const { text, colorClass } = formatEvent(event)
            return (
              <div key={i} className={`event-log-row ${colorClass}`}>
                <span className="event-log-time">{formatTimestamp(event.timestamp)}</span>
                <span className="event-log-text">{text}</span>
              </div>
            )
          })
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}

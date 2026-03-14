/**
 * SourceInput — manages a list of evidence sources (local file paths and URLs).
 *
 * @decision DEC-UPLOAD-003
 * @title Single SourceInput component manages both files and URLs
 * @status accepted
 * @rationale Both are string paths/URLs that map to evidence_sources: list[str].
 *   Unified component avoids split state management. File dialog via Electron IPC
 *   (window.satAPI.openFileDialog). URL entry uses a text field + Enter/button.
 *   Deduplication is handled before calling onChange so parent state stays clean.
 */
import { useState, type ChangeEvent, type KeyboardEvent } from 'react'

interface SourceInputProps {
  sources: string[]
  onChange: (sources: string[]) => void
  disabled?: boolean
}

export default function SourceInput({ sources, onChange, disabled }: SourceInputProps) {
  const [urlInput, setUrlInput] = useState('')

  const addFiles = async () => {
    if (!window.satAPI) return
    const paths = await window.satAPI.openFileDialog()
    if (paths.length > 0) {
      const newSources = [...sources]
      for (const p of paths) {
        if (!newSources.includes(p)) newSources.push(p)
      }
      onChange(newSources)
    }
  }

  const addUrl = () => {
    const url = urlInput.trim()
    if (url && (url.startsWith('http://') || url.startsWith('https://')) && !sources.includes(url)) {
      onChange([...sources, url])
      setUrlInput('')
    }
  }

  const handleUrlKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addUrl()
    }
  }

  const removeSource = (index: number) => {
    onChange(sources.filter((_, i) => i !== index))
  }

  const displayName = (source: string): string => {
    if (source.startsWith('http://') || source.startsWith('https://')) return source
    // Show just filename for local paths (cross-platform)
    const parts = source.split(/[/\\]/)
    return parts[parts.length - 1] || source
  }

  const isUrl = (source: string): boolean =>
    source.startsWith('http://') || source.startsWith('https://')

  return (
    <div className="source-input">
      <div className="source-input-actions">
        <button
          type="button"
          className="btn-secondary btn-sm"
          onClick={addFiles}
          disabled={disabled}
        >
          + Add Files
        </button>
        <div className="source-input-url-row">
          <input
            type="text"
            className="input-field input-sm"
            placeholder="https://example.com/report.pdf"
            value={urlInput}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setUrlInput(e.target.value)}
            onKeyDown={handleUrlKeyDown}
            disabled={disabled}
          />
          <button
            type="button"
            className="btn-secondary btn-sm"
            onClick={addUrl}
            disabled={disabled || !urlInput.trim().startsWith('http')}
          >
            + Add URL
          </button>
        </div>
      </div>

      {sources.length > 0 && (
        <div className="source-input-list">
          {sources.map((source, i) => (
            <div key={source} className="source-input-item">
              <span className="source-input-icon">
                {isUrl(source) ? '🔗' : '📄'}
              </span>
              <span className="source-input-name text-sm" title={source}>
                {displayName(source)}
              </span>
              <button
                type="button"
                className="source-input-remove text-muted"
                onClick={() => removeSource(i)}
                disabled={disabled}
                title="Remove source"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

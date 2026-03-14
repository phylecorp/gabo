/**
 * @decision DEC-DESKTOP-STAGE-CARD-001
 * @title StageCard: current-stage detail with elapsed timer
 * @status accepted
 * @rationale While a technique is running the analyst wants to know which one
 *   and how long it's been running. The elapsed timer uses setInterval via
 *   useEffect — it starts when the component mounts (stage becomes active) and
 *   stops when it unmounts (stage completes or fails). The category badge uses
 *   the same color semantics as everywhere else in the app.
 */
import { useEffect, useRef, useState } from 'react'
import IntelBadge from '../common/IntelBadge'
import type { TechniqueInfo } from '../../api/types'

interface StageCardProps {
  techniqueName: string
  techniqueInfo?: TechniqueInfo
  stageName?: string
}

export default function StageCard({ techniqueName, techniqueInfo, stageName }: StageCardProps) {
  const [elapsed, setElapsed] = useState(0)
  const startRef = useRef(Date.now())

  useEffect(() => {
    startRef.current = Date.now()
    setElapsed(0)
    const timer = setInterval(() => {
      setElapsed(Math.floor((Date.now() - startRef.current) / 1000))
    }, 1000)
    return () => clearInterval(timer)
  }, [techniqueName])

  const category = techniqueInfo?.category ?? null

  return (
    <div className="stage-card">
      <div className="stage-card-indicator">
        <span className="stage-card-pulse" />
      </div>
      <div className="stage-card-body">
        <div className="stage-card-name">
          {stageName === 'research' ? 'Research Phase' : techniqueName}
        </div>
        <div className="stage-card-meta">
          {category && (
            <IntelBadge
              label={category}
              variant="category"
              category={category}
            />
          )}
          {!category && stageName === 'research' && (
            <IntelBadge label="research" variant="default" />
          )}
          <span className="stage-card-elapsed">{elapsed}s</span>
          <span className="stage-card-status">RUNNING</span>
        </div>
        {techniqueInfo?.description && (
          <p className="stage-card-desc">{techniqueInfo.description}</p>
        )}
      </div>
    </div>
  )
}

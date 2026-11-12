import { useEffect, useState } from 'react'
import { noticeCopy } from '../copy/notices'

// How long a request may wait before the page says the server is waking. Three
// seconds is longer than any warm response and much shorter than a cold start
// (Dermot, 12 November 2026).
const WAKE_NOTICE_DELAY_MS = 3000

// True once `waiting` has been true for the delay without interruption; false
// again the moment it stops. The flag is set only from the timer's callback and
// cleared in the effect's cleanup, so a wait that ends early never shows it.
function useWaitedLongerThan(waiting: boolean, delayMs: number): boolean {
  const [expired, setExpired] = useState(false)
  useEffect(() => {
    if (!waiting) return
    const id = setTimeout(() => setExpired(true), delayMs)
    return () => {
      clearTimeout(id)
      setExpired(false)
    }
  }, [waiting, delayMs])
  return waiting && expired
}

// One line, on every page that loads from the backend, for the wait a visitor
// would otherwise have to guess at: the deployed backend scales to zero when
// idle and its first answer afterwards can take half a minute. Rendered beside
// the page's own spinner; it appears after the delay and goes when the data
// arrives or the request fails (`waiting` turns false either way).
export function WakingNotice({ waiting }: { waiting: boolean }) {
  const show = useWaitedLongerThan(waiting, WAKE_NOTICE_DELAY_MS)
  if (!show) return null
  return (
    <p className="text-sm text-slate-500" role="status" data-testid="waking-notice">
      {noticeCopy.waking}
    </p>
  )
}

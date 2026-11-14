import { Link } from 'react-router-dom'
import type { Segment } from '../copy/claim'

// A sentence from the copy modules whose words include an in-app link, rendered
// so the link is a real <Link> and the rest is text (Prompt 30). The Guide has
// its own renderer because its segments also mark the interface's labels.
export function Sentence({ segments }: { segments: readonly Segment[] }) {
  return (
    <>
      {segments.map((segment, index) =>
        typeof segment === 'string' ? (
          <span key={index}>{segment}</span>
        ) : (
          <Link key={index} to={segment.to} className="text-blue-700 hover:underline">
            {segment.link}
          </Link>
        ),
      )}
    </>
  )
}

import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import type { PolicyPassage, PolicySection } from '../api/types'
import { Card, ErrorBanner, Spinner } from '../components/ui'
import { policyCopy } from '../copy/policy'
import { usePolicy } from '../hooks/queries'
import { typography } from '../styles/tokens'

// The policy as it is indexed: one card per section, one block per passage, each
// block anchored by its chunk id so a run page can point at the exact passage
// the Validator was shown. Counts and the model come from the endpoint, so the
// page cannot disagree with retrieval. All text lives in copy/policy.ts.
export function PolicyPage() {
  const policy = usePolicy()
  const highlighted = useAnchorHighlight(policy.data?.passage_count ?? 0)

  return (
    <div className="space-y-4">
      <h1 className={typography.pageTitle}>{policyCopy.title}</h1>
      <Card>
        <p className="text-sm text-slate-700">{policyCopy.opening}</p>
      </Card>

      {policy.isLoading && <Spinner label="Loading the policy…" />}
      {policy.error && <ErrorBanner message={policyCopy.loadFailed} />}

      {policy.data && policy.data.passage_count === 0 && (
        <p className="text-sm text-slate-600" data-testid="policy-empty">
          {policyCopy.empty}
        </p>
      )}

      {policy.data && policy.data.passage_count > 0 && (
        <>
          <p className={typography.caption} data-testid="policy-count">
            {policyCopy.countLine(
              policy.data.passage_count,
              policy.data.source,
              policy.data.embedding_model ?? 'an unrecorded model',
            )}
          </p>
          {policy.data.sections.map((section) => (
            <SectionCard key={section.name} section={section} highlighted={highlighted} />
          ))}
        </>
      )}
    </div>
  )
}

function SectionCard({
  section,
  highlighted,
}: {
  section: PolicySection
  highlighted: string | null
}) {
  return (
    <Card title={section.name}>
      <div className="space-y-3">
        {section.passages.map((passage) => (
          <PassageBlock
            key={passage.chunk_id}
            passage={passage}
            current={passage.chunk_id === highlighted}
          />
        ))}
      </div>
    </Card>
  )
}

// The anchor is the raw chunk id (a UUID is a valid element id), so a link of the
// form /policy#<chunk_id> is stable for as long as the index is.
function PassageBlock({ passage, current }: { passage: PolicyPassage; current: boolean }) {
  const frame = current
    ? 'rounded border-2 border-amber-400 bg-amber-50 p-3'
    : 'rounded border border-slate-200 p-3'
  return (
    <article id={passage.chunk_id} aria-current={current ? 'true' : undefined} className={frame}>
      <p className="mb-1 text-xs text-slate-500">
        {policyCopy.passageLabel(passage.section, passage.position, passage.section_size)}
      </p>
      <p className="whitespace-pre-wrap text-sm text-slate-700">{passage.text}</p>
    </article>
  )
}

// Which passage the URL's hash names, if any, scrolled into view once the
// passages have rendered. `scrollIntoView` is optional-called because jsdom (the
// test environment) does not implement it; the highlight is the tested part.
function useAnchorHighlight(renderedCount: number): string | null {
  const { hash } = useLocation()
  const target = hash.startsWith('#') ? decodeURIComponent(hash.slice(1)) : null
  useEffect(() => {
    if (!target || renderedCount === 0) return
    document.getElementById(target)?.scrollIntoView?.({ block: 'center' })
  }, [target, renderedCount])
  return target
}

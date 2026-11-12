import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import type { PolicyPassage, PolicySection } from '../api/types'
import { Card, CopyButton, ErrorBanner, Spinner } from '../components/ui'
import { WakingNotice } from '../components/WakingNotice'
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
  const anchorMissing =
    highlighted !== null &&
    policy.data !== undefined &&
    policy.data.passage_count > 0 &&
    !policy.data.sections.some((s) => s.passages.some((p) => p.chunk_id === highlighted))

  return (
    <div className="space-y-4">
      <h1 className={typography.pageTitle}>{policyCopy.title}</h1>
      <Card>
        <p className="text-sm text-slate-700">{policyCopy.opening}</p>
      </Card>

      {policy.isLoading && <Spinner label="Loading the policy…" />}
      <WakingNotice waiting={policy.isLoading} />
      {policy.error && <ErrorBanner message={policyCopy.loadFailed} />}

      {policy.data && policy.data.passage_count === 0 && (
        <p className="text-sm text-slate-600" data-testid="policy-empty">
          {policyCopy.empty}
        </p>
      )}

      {policy.data && policy.data.passage_count > 0 && (
        <>
          {anchorMissing && (
            <p
              className="rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800"
              data-testid="policy-missing-anchor"
            >
              {policyCopy.missingAnchor}
            </p>
          )}
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
  // scroll-mt keeps a passage reached by its anchor below the sticky navigation.
  const frame = current
    ? 'scroll-mt-20 rounded border-2 border-amber-400 bg-amber-50 p-3'
    : 'scroll-mt-20 rounded border border-slate-200 p-3'
  return (
    <article id={passage.chunk_id} aria-current={current ? 'true' : undefined} className={frame}>
      <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span>
          {policyCopy.passageLabel(passage.section, passage.position, passage.section_size)}
        </span>
        <span className="font-mono text-slate-400">{policyCopy.chunkLabel(passage.chunk_id)}</span>
        <CopyButton value={passage.chunk_id} label={policyCopy.copyChunkId} />
      </div>
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
    // block: 'start' with the article's scroll margin rests it just below the menu.
    document.getElementById(target)?.scrollIntoView?.({ block: 'start' })
  }, [target, renderedCount])
  return target
}

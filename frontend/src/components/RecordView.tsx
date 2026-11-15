import { useId, useState, type KeyboardEvent } from 'react'
import type { AuditEntry } from '../api/types'
import { auditCopy } from '../copy/audit'
import { extractPrompt, isDemoFixture } from '../pages/auditDerivation'
import { RecordTree } from './RecordTree'
import { CopyButton } from './ui'

type Tab = 'record' | 'instructions'

// One audit record, as a reader sees it (Prompt 32): the stored record as a
// tree and, when a model was called, the instructions it was sent, on two
// tabs, with Copy record copying the row as the API served it (plan D4). The
// record viewer's dialog wraps it on the Audit page; the run page's cards
// show it in place, so a record reads the same wherever it is opened.
export function RecordView({ entry }: { entry: AuditEntry }) {
  const [tab, setTab] = useState<Tab>('record')
  const prompt = extractPrompt(entry)
  return (
    <div data-testid="record-view">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <Tabs tab={tab} onChange={setTab} hasInstructions={prompt !== null} />
        <CopyButton value={JSON.stringify(entry, null, 2)} label={auditCopy.copyRecord} />
      </div>
      {tab === 'record' || prompt === null ? (
        <div role="tabpanel" aria-label={auditCopy.tabRecord}>
          {isDemoFixture(entry) && (
            <p className="mb-2 text-xs text-slate-600" data-testid="no-model-call">
              {auditCopy.noModelCall}
            </p>
          )}
          <RecordTree value={entry.payload} />
        </div>
      ) : (
        <Instructions system={prompt.system} user={prompt.user} />
      )}
    </div>
  )
}

interface TabsProps {
  tab: Tab
  onChange: (tab: Tab) => void
  hasInstructions: boolean
}

// Two tabs, or one when the record holds no model call. Left and Right move
// between them, as a tab list should. Ids are per instance, because several
// cards on the run page may be open at once.
function Tabs({ tab, onChange, hasInstructions }: TabsProps) {
  const id = useId()
  const tabs: Tab[] = hasInstructions ? ['record', 'instructions'] : ['record']
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
    const index = tabs.indexOf(tab)
    const next = tabs[(index + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]
    onChange(next)
    event.currentTarget.querySelector<HTMLElement>(`[id="${id}-${next}"]`)?.focus()
  }
  return (
    <div role="tablist" className="flex gap-1 text-xs" onKeyDown={onKeyDown}>
      {tabs.map((name) => (
        <button
          key={name}
          id={`${id}-${name}`}
          type="button"
          role="tab"
          aria-selected={tab === name}
          tabIndex={tab === name ? 0 : -1}
          onClick={() => onChange(name)}
          className={`rounded px-2 py-1 ${
            tab === name ? 'bg-slate-800 text-white' : 'text-slate-600 hover:bg-slate-100'
          }`}
        >
          {name === 'record' ? auditCopy.tabRecord : auditCopy.tabInstructions}
        </button>
      ))}
    </div>
  )
}

// The system instructions and the message, as readable text with their line
// breaks, under two plain headings.
function Instructions({ system, user }: { system: string; user: string }) {
  return (
    <div role="tabpanel" aria-label={auditCopy.tabInstructions} className="space-y-3 text-xs">
      <PromptBlock heading={auditCopy.systemHeading} body={system} />
      <PromptBlock heading={auditCopy.userHeading} body={user} />
    </div>
  )
}

function PromptBlock({ heading, body }: { heading: string; body: string }) {
  return (
    <div>
      <h3 className="mb-1 font-medium text-slate-600">{heading}</h3>
      <pre className="whitespace-pre-wrap break-words rounded bg-slate-50 p-2 text-slate-700">
        {body}
      </pre>
    </div>
  )
}

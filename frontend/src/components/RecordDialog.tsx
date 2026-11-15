import { useState, type KeyboardEvent } from 'react'
import type { AuditEntry } from '../api/types'
import { auditCopy } from '../copy/audit'
import { extractPrompt, isDemoFixture } from '../pages/auditDerivation'
import { Dialog } from './Dialog'
import { RecordTree } from './RecordTree'
import { CopyButton } from './ui'

type Tab = 'record' | 'instructions'

interface RecordDialogProps {
  entry: AuditEntry
  // The plain-words line naming the record (auditDerivation.recordHeader).
  header: string
  onClose: () => void
}

// The record viewer (Prompt 32): one record in a dialog, as a tree and, when a
// model was called, as the instructions it was sent; Copy record copies the
// row as the API served it, not the page's rendering of it (plan D4). Takes a
// record and its header line; nothing in it is the Audit page's, so the run
// page's cards and the Agents page can take it up later.
export function RecordDialog({ entry, header, onClose }: RecordDialogProps) {
  const [tab, setTab] = useState<Tab>('record')
  const prompt = extractPrompt(entry)
  return (
    <Dialog title={header} onClose={onClose}>
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
    </Dialog>
  )
}

interface TabsProps {
  tab: Tab
  onChange: (tab: Tab) => void
  hasInstructions: boolean
}

// Two tabs, or one when the record holds no model call. Left and Right move
// between them, as a tab list should.
function Tabs({ tab, onChange, hasInstructions }: TabsProps) {
  const tabs: Tab[] = hasInstructions ? ['record', 'instructions'] : ['record']
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return
    const index = tabs.indexOf(tab)
    const next = tabs[(index + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]
    onChange(next)
    ;(event.currentTarget.querySelector(`#tab-${next}`) as HTMLElement | null)?.focus()
  }
  return (
    <div role="tablist" className="flex gap-1 text-xs" onKeyDown={onKeyDown}>
      {tabs.map((name) => (
        <button
          key={name}
          id={`tab-${name}`}
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

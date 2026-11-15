import { useState } from 'react'
import { auditCopy } from '../copy/audit'

// The record's own keys and the level beneath them start open; deeper levels
// start closed (plan D3): the Validator's verdict reads at once, the retrieved
// chunks and the prompt are a click away.
const OPEN_DEPTH = 1
// A string longer than this is folded behind Show all.
const FOLD_CHARS = 240

// One kind of value, one colour (from the tokens' palette): a reader can tell a
// number from a string without the quotes.
const VALUE_CLASS = {
  string: 'text-green-700',
  number: 'text-blue-700',
  boolean: 'text-purple-700',
  null: 'italic text-slate-400',
} as const

// A stored record as a tree (Prompt 32): keys and values coloured by kind, each
// object and list collapsible, long text wrapped and folded. Takes any JSON
// value; nothing in it is the Audit page's.
export function RecordTree({ value }: { value: unknown }) {
  return (
    <div className="font-mono text-xs leading-5 text-slate-700" data-testid="record-tree">
      <Node value={value} depth={0} />
    </div>
  )
}

interface NodeProps {
  name?: string
  value: unknown
  depth: number
}

function Node({ name, value, depth }: NodeProps) {
  if (typeof value === 'object' && value !== null) {
    return <Branch name={name} value={value as object} depth={depth} />
  }
  return (
    <div className="flex flex-wrap gap-x-1 pl-3">
      {name !== undefined && <Key name={name} />}
      <Leaf value={value} />
    </div>
  )
}

// An object or a list: a disclosure button with the key and, when closed, how
// many keys or items it holds; when open, its children one level deeper.
function Branch({ name, value, depth }: NodeProps & { value: object }) {
  const [open, setOpen] = useState(depth <= OPEN_DEPTH)
  const isList = Array.isArray(value)
  const entries: [string, unknown][] = isList
    ? (value as unknown[]).map((item, index) => [String(index), item])
    : Object.entries(value)
  const count = entries.length
  const summary =
    count === 0 ? auditCopy.empty : isList ? auditCopy.items(count) : auditCopy.keys(count)
  const [openBracket, closeBracket] = isList ? ['[', ']'] : ['{', '}']
  return (
    <div className={depth === 0 ? '' : 'pl-3'}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex flex-wrap gap-x-1 rounded text-left hover:bg-slate-50"
      >
        <span aria-hidden="true" className="w-3 text-slate-400">
          {open ? '▾' : '▸'}
        </span>
        {name !== undefined && <Key name={name} />}
        <span className="text-slate-500">
          {open && count > 0 ? openBracket : `${openBracket}${summary}${closeBracket}`}
        </span>
      </button>
      {open && count > 0 && (
        <div className="border-l border-slate-100 pl-1">
          {entries.map(([key, child]) => (
            <Node key={key} name={key} value={child} depth={depth + 1} />
          ))}
          <span className="pl-3 text-slate-500">{closeBracket}</span>
        </div>
      )}
    </div>
  )
}

function Key({ name }: { name: string }) {
  return <span className="font-medium text-slate-700">{name}:</span>
}

function Leaf({ value }: { value: unknown }) {
  if (value === null || value === undefined) {
    return <span className={VALUE_CLASS.null}>null</span>
  }
  if (typeof value === 'string') return <Text text={value} />
  if (typeof value === 'number') return <span className={VALUE_CLASS.number}>{value}</span>
  if (typeof value === 'boolean') {
    return <span className={VALUE_CLASS.boolean}>{String(value)}</span>
  }
  return <span>{String(value)}</span>
}

// A string value, wrapped with its line breaks and never wider than the tree;
// a long one is folded behind Show all so a prompt or a reasoning does not
// push everything else off the screen.
function Text({ text }: { text: string }) {
  const [all, setAll] = useState(false)
  const long = text.length > FOLD_CHARS
  const shown = long && !all ? `${text.slice(0, FOLD_CHARS)}…` : text
  return (
    <span className="min-w-0 flex-1">
      <span className={`whitespace-pre-wrap break-words ${VALUE_CLASS.string}`}>“{shown}”</span>
      {long && (
        <button
          type="button"
          onClick={() => setAll((v) => !v)}
          className="ml-1 text-blue-700 hover:underline"
        >
          {all ? auditCopy.showLess : auditCopy.showAll}
        </button>
      )}
    </span>
  )
}

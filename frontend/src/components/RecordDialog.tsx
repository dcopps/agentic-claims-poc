import type { AuditEntry } from '../api/types'
import { Dialog } from './Dialog'
import { RecordView } from './RecordView'

interface RecordDialogProps {
  entry: AuditEntry
  // The plain-words line naming the record (auditDerivation.recordHeader).
  header: string
  onClose: () => void
}

// The record viewer as a dialog over the page (Prompt 32): the Audit page's
// way of opening a record. Takes a record and its header line; nothing in it
// is the Audit page's.
export function RecordDialog({ entry, header, onClose }: RecordDialogProps) {
  return (
    <Dialog title={header} onClose={onClose}>
      <RecordView entry={entry} />
    </Dialog>
  )
}

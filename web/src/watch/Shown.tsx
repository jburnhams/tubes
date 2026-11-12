// The watching side's pieces for a remote read, drawn in its own look. Every read goes through
// Strata's `DataView` (skeleton while it loads, `empty`, else the content); a failed read is drawn by
// `trouble` (DataView's `error`): a plain sentence with Try again, inside DataView's alert. DataView
// does the same for the admin area in Strata's look.
import type { ReactNode } from 'react'
import { Button, type LoadFailure } from 'strata-react'

/** DataView's `error` on the watching side. */
export const trouble = (failure: LoadFailure) => <Trouble {...failure} />

export function Trouble({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="grid justify-items-center gap-4 py-16 text-center">
      <p className="max-w-md text-tube-base text-tube-ink">{message}</p>
      {retry && <Pill onClick={retry}>Try again</Pill>}
    </div>
  )
}

/** A rounded grey button, the watching side's only button shape: Strata's secondary `Button`, drawn round and grey by the
 *  watching side's theme (tube.css, `.tube`). */
export function Pill({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return <Button variant="secondary" onClick={onClick}>{children}</Button>
}

/** A centred note for an empty list: what is missing and where it comes from. */
export function Nothing({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="grid justify-items-center gap-2 py-16 text-center">
      <p className="text-tube-lg font-medium text-tube-ink">{title}</p>
      <p className="max-w-md text-tube-sm text-tube-quiet">{children}</p>
    </div>
  )
}

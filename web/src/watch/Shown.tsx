// The watching side's way of showing a remote read (Strata's `Load`): its own skeleton while it
// loads, a plain sentence with Try again when it fails, an empty state that says where videos come
// from, else the content. DataView does the same for the admin area in Strata's look.
import type { ReactNode } from 'react'
import type { Load } from 'strata-react'

export function Shown<T>({ state, skeleton, isEmpty = () => false, empty = null, children }: { state: Load<T>; skeleton: ReactNode; isEmpty?: (data: T) => boolean; empty?: ReactNode; children: (data: T) => ReactNode }) {
  if (state.status === 'loading') return <>{skeleton}</>
  if (state.status === 'error') return <Trouble message={state.message} retry={state.retry} />
  return <>{isEmpty(state.data) ? empty : children(state.data)}</>
}

export function Trouble({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div role="alert" className="grid justify-items-center gap-4 py-16 text-center">
      <p className="max-w-md text-tube-base text-tube-ink">{message}</p>
      {retry && <Pill onClick={retry}>Try again</Pill>}
    </div>
  )
}

/** A rounded grey button, the watching side's only button shape. */
export function Pill({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex h-9 items-center gap-2 rounded-full bg-tube-chip px-4 text-tube-sm font-medium text-tube-ink transition-colors hover:bg-tube-chip-hover"
    >
      {children}
    </button>
  )
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

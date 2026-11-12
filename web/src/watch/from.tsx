// Where a click came from, so a play or a channel visit can be kept with it (src/tubes/viewing.py): which list
// (Home, Continue watching, a channel, a search, Up next...), which one, and the item's place in it. A list says
// what it is once, with <FromHere>; every link in it reads that and hands it on in the router's location
// state, which the watch page and the channel page send with the play or the visit. Location state rather than
// a query string, so the address stays clean to share; a shared or typed address then has none, and the
// server records it as `link`.
import { createContext, useContext, type ReactNode } from 'react'
import { useLocation } from 'react-router'
import type { From } from '../api'

const Here = createContext<From | null>(null)

/** Everything inside is in this list. */
export function FromHere({ source, detail, children }: { source: From['source']; detail?: string; children: ReactNode }) {
  return <Here value={{ source, detail }}>{children}</Here>
}

/** The list this is in, or null outside any. */
export function useHere(): From | null {
  return useContext(Here)
}

/** The location state a link hands on: the list, and the item's place in it when it has one. */
export function fromState(here: From | null, rank?: number): { from: From } | undefined {
  if (!here) return undefined
  return { from: rank === undefined ? here : { ...here, rank } }
}

/** Where the current page was opened from, if a link in the app opened it. */
export function useArrivedFrom(): From | null {
  const state: unknown = useLocation().state
  const from = state && typeof state === 'object' && 'from' in state ? (state as { from: unknown }).from : null
  return from && typeof from === 'object' && 'source' in from ? (from as From) : null
}

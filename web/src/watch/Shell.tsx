// The watching side's frame, as the old Tubes app laid it out: a fixed top bar (menu button, the
// mark, a search box in the middle), a left rail (Home, Channels, then every channel with its
// picture, then Admin) and the page. The menu button folds the rail to icons; on a phone it starts
// folded. The admin area has its own frame (screens/Layout.tsx) in Strata's look.
import { Home, Menu, Search, Settings, Tv } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useNavigate, useSearchParams } from 'react-router'
import { useLoad } from 'strata-react'
import { api, keys } from '../api'
import { Avatar } from './cards'
import { fromState } from './from'
import { useReconcile } from './missing'

export function Mark() {
  return (
    <Link to="/" className="flex items-center gap-1.5 px-1" aria-label="Tubes home">
      <span aria-hidden className="grid h-6 w-8 place-items-center rounded-tube-sm bg-tube-red text-tube-on-red"><Tv className="size-4" strokeWidth={2.5} /></span>
      <span className="text-tube-lg font-bold tracking-tight text-tube-ink">Tubes</span>
    </Link>
  )
}

export function SearchBox() {
  const [params] = useSearchParams()
  const [q, setQ] = useState(params.get('q') ?? '')
  const navigate = useNavigate()
  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (q.trim()) navigate(`/search?${new URLSearchParams({ q: q.trim() })}`)
  }
  return (
    <form role="search" onSubmit={onSubmit} className="flex min-w-0 flex-1 justify-center">
      <div className="flex w-full max-w-xl">
        <input
          type="search" value={q} onChange={e => setQ(e.target.value)} placeholder="Search" aria-label="Search titles" autoComplete="off"
          className="h-10 min-w-0 flex-1 rounded-l-full border border-tube-field-line bg-tube-field px-4 text-tube-base text-tube-ink placeholder:text-tube-quiet focus:border-tube-focus focus:outline-none"
        />
        <button type="submit" aria-label="Search" className="grid h-10 w-16 place-items-center rounded-r-full border border-l-0 border-tube-field-line bg-tube-chip text-tube-ink hover:bg-tube-chip-hover">
          <Search className="size-5" strokeWidth={1.75} />
        </button>
      </div>
    </form>
  )
}

function RailLink({ to, icon, label, wide, end, state }: { to: string; icon: ReactNode; label: string; wide: boolean; end?: boolean; state?: unknown }) {
  return (
    <NavLink
      to={to} end={end} state={state}
      className={({ isActive }) => `flex items-center rounded-tube-sm text-tube-ink hover:bg-tube-chip ${isActive ? 'bg-tube-chip font-medium' : ''} ${wide ? 'h-10 gap-6 px-3 text-tube-sm' : 'flex-col justify-center gap-1 py-4 text-tube-xs'}`}
    >
      {icon}<span className={wide ? 'truncate' : 'text-center'}>{label}</span>
    </NavLink>
  )
}

function Rail({ wide }: { wide: boolean }) {
  const channels = useLoad({ queryKey: keys.channels, queryFn: api.channels })
  const icon = 'size-6 shrink-0'
  return (
    <nav aria-label="Main" className={`fixed top-14 bottom-0 left-0 overflow-y-auto bg-tube-page px-1 py-2 ${wide ? 'w-60 px-3' : 'w-18'}`}>
      <RailLink to="/" end icon={<Home className={icon} strokeWidth={1.75} />} label="Home" wide={wide} />
      <RailLink to="/channels" end icon={<Tv className={icon} strokeWidth={1.75} />} label="Channels" wide={wide} />
      {wide && channels.status === 'ready' && channels.data.length > 0 && (
        <section aria-labelledby="rail-channels" className="mt-3 border-t border-tube-line pt-3">
          <h2 id="rail-channels" className="px-3 pb-1 text-tube-base font-medium text-tube-ink">Channels</h2>
          {channels.data.map((c, i) => <RailLink key={c.id} to={`/channels/${encodeURIComponent(c.id)}`} state={fromState({ source: 'rail' }, i)} icon={<Avatar channel={c} size="size-6" />} label={c.title} wide />)}
        </section>
      )}
      <div className={wide ? 'mt-3 border-t border-tube-line pt-3' : ''}>
        <RailLink to="/admin" icon={<Settings className={icon} strokeWidth={1.75} />} label="Admin" wide={wide} />
      </div>
    </nav>
  )
}

// Folded on a phone-width screen; wide where the browser cannot say (jsdom has no matchMedia).
const startsWide = () => typeof window.matchMedia !== 'function' || !window.matchMedia('(max-width: 768px)').matches

export function Shell() {
  const [wide, setWide] = useState(startsWide)
  useReconcile()
  return (
    <div className="min-h-screen bg-tube-page font-tube text-tube-ink">
      <header className="fixed inset-x-0 top-0 z-10 flex h-14 items-center gap-4 bg-tube-page px-4">
        <div className="flex shrink-0 items-center gap-2">
          <button type="button" onClick={() => setWide(w => !w)} aria-label={wide ? 'Fold the menu' : 'Open the menu'} aria-expanded={wide} className="grid size-10 place-items-center rounded-full hover:bg-tube-chip">
            <Menu className="size-6" strokeWidth={1.75} />
          </button>
          <Mark />
        </div>
        <SearchBox />
        <div className="hidden w-32 shrink-0 md:block" />
      </header>
      <Rail wide={wide} />
      <main className={`pt-14 ${wide ? 'pl-60' : 'pl-18'}`}>
        <div className="px-6 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

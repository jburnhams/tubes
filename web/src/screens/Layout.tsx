// The admin area's frame: Strata's AppShell (product name, side nav, main region) around the
// screens that run the server (Library, Suggestions, Cache, System, Settings), in Strata's look. The watching side has
// its own frame (watch/Shell.tsx) in the old Tubes look; the first nav item goes back to it.
import { HardDrive, History, Library, Server, Settings, Tv } from 'lucide-react'
import { Outlet } from 'react-router'
import { AppShell, type NavItem } from 'strata-react'

export const nav: NavItem[] = [
  { to: '/', label: 'Back to watching', icon: Tv, end: true },
  { to: '/admin/library', label: 'Library', icon: Library },
  { to: '/admin/suggestions', label: 'Suggestions', icon: History },
  { to: '/admin/cache', label: 'Cache', icon: HardDrive },
  { to: '/admin/system', label: 'System', icon: Server },
  { to: '/admin/settings', label: 'Settings', icon: Settings },
]

export const product = 'Tubes admin'

export function Layout() {
  return (
    <AppShell product={product} nav={nav}>
      <div className="grid max-w-6xl gap-8 pb-16">
        <Outlet />
      </div>
    </AppShell>
  )
}

// The one question: "How is the server set up, and how do I change it?" Three tabs whose choice
// lives in the URL (?tab=shown, ?tab=appearance). General is one form over the server's settings, grouped by
// what they decide (the cache, what is fetched, the tools); the fields start
// from what the server holds (rendered inside DataView's ready state, so never blank while
// loading), problems are said under their field, and saving is one AsyncButton. The server checks
// again and says why it refused, under the button. Shown videos is a second form, over what the
// watching side lists (kept in the server's database, not its settings file, so it has its own read
// and its own Save): the shortest and longest length, in minutes with empty for no limit, and which
// streams are left out. Its finding is how many videos the filters leave out now, which it says
// again after a save. Appearance is Strata's ColorSchemeChoice.
import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { AsyncButton, ColorSchemeChoice, DataView, EmptyState, Field, Input, NativeSelect, PageHeader, Skeleton, Tabs, format, useAsyncAction, useLoad } from 'strata-react'
import { api, describeError, folderProblem, keys, numberProblem, type Settings, type ShownFilters, type StreamFilter } from '../api'

const tabs = [
  { value: 'general', label: 'General' },
  { value: 'shown', label: 'Shown videos' },
  { value: 'appearance', label: 'Appearance' },
]

/** The heights a fetch can be capped at. */
export const heights = [720, 1080, 1440, 2160]

export function SettingsScreen() {
  return (
    <>
      <PageHeader title="Settings" scope="Kept on the server, for every browser that opens the app" />
      <Tabs param="tab" items={tabs} label="Settings">
        {tab => (tab === 'appearance' ? <Appearance /> : tab === 'shown' ? <Shown /> : <General />)}
      </Tabs>
    </>
  )
}

function General() {
  const load = useLoad({ queryKey: keys.settings, queryFn: api.settings })
  return (
    <DataView state={load} isEmpty={() => false} skeleton={<FormSkeleton />} empty={<EmptyState title="No settings">The server sent none.</EmptyState>}>
      {s => <SettingsForm current={s} />}
    </DataView>
  )
}

/** Mirrors the form: fields with hints, then the button. */
function FormSkeleton() {
  return (
    <div className="grid max-w-xl gap-6" aria-hidden>
      {[0, 1, 2, 3].map(i => (
        <div key={i} className="grid gap-1.5"><Skeleton className="h-4 w-32" /><Skeleton className="h-9 w-full" /><Skeleton className="h-4 w-3/4" /></div>
      ))}
      <Skeleton className="h-9 w-32" />
    </div>
  )
}

type Fields = Record<'cache_dir' | 'cache_limit_gb' | 'half_life_days' | 'protect_days' | 'max_height' | 'player_client' | 'cookies_from_browser' | 'ytdlp' | 'ffmpeg', string>

/** Every problem the form can see before sending, by field. */
export function settingsProblems(f: Fields): Partial<Record<keyof Fields, string>> {
  return {
    cache_dir: folderProblem(f.cache_dir),
    cache_limit_gb: numberProblem(f.cache_limit_gb, 'the limit'),
    half_life_days: numberProblem(f.half_life_days, 'the days'),
    protect_days: f.protect_days.trim() === '0' ? undefined : numberProblem(f.protect_days, 'the days'),
    ytdlp: f.ytdlp.trim() ? undefined : 'Enter the yt-dlp command, or its full path.',
    ffmpeg: f.ffmpeg.trim() ? undefined : 'Enter the ffmpeg command, or its full path.',
  }
}

export function SettingsForm({ current }: { current: Settings }) {
  const queryClient = useQueryClient()
  const [f, setF] = useState<Fields>({
    cache_dir: current.cache_dir, cache_limit_gb: String(current.cache_limit_gb), half_life_days: String(current.half_life_days), protect_days: String(current.protect_days),
    max_height: String(current.max_height), player_client: current.player_client, cookies_from_browser: current.cookies_from_browser, ytdlp: current.ytdlp, ffmpeg: current.ffmpeg,
  })
  const [problems, setProblems] = useState<ReturnType<typeof settingsProblems>>({})
  const set = (k: keyof Fields) => (e: { target: { value: string } }) => setF(old => ({ ...old, [k]: e.target.value }))

  const save = useAsyncAction(async () => {
    await api.saveSettings({
      cache_dir: f.cache_dir.trim(), cache_limit_gb: Number(f.cache_limit_gb), half_life_days: Number(f.half_life_days), protect_days: Number(f.protect_days),
      max_height: Number(f.max_height), player_client: f.player_client.trim(), cookies_from_browser: f.cookies_from_browser.trim(), ytdlp: f.ytdlp.trim(), ffmpeg: f.ffmpeg.trim(),
    })
    await Promise.all([keys.settings, keys.system, keys.cache].map(queryKey => queryClient.invalidateQueries({ queryKey })))
  }, { describeError })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    const found = settingsProblems(f)
    setProblems(found)
    if (!Object.values(found).some(Boolean)) void save.run()
  }

  return (
    <form onSubmit={onSubmit} noValidate className="grid max-w-xl gap-8">
      <fieldset className="grid gap-5">
        <legend className="mb-4 type-heading">Cache</legend>
        <Field label="Cache folder" hint="A full path, on a disk with room for the limit below. Each video gets a folder in it." error={problems.cache_dir}>
          <Input value={f.cache_dir} onChange={set('cache_dir')} autoComplete="off" spellCheck={false} />
        </Field>
        <Field label="Cache limit (GB)" hint="Trimming starts at 95% of this and stops under 90%." error={problems.cache_limit_gb}>
          <Input value={f.cache_limit_gb} onChange={set('cache_limit_gb')} inputMode="decimal" autoComplete="off" />
        </Field>
        <Field label="Half-life of a play (days)" hint="A play counts half as much this many days later. Lower keeps recent favourites; higher keeps old ones." error={problems.half_life_days}>
          <Input value={f.half_life_days} onChange={set('half_life_days')} inputMode="decimal" autoComplete="off" />
        </Field>
        <Field label="Keep unplayed copies for (days)" hint="A copy nobody has played yet is kept this long after it was fetched. 0 keeps none." error={problems.protect_days}>
          <Input value={f.protect_days} onChange={set('protect_days')} inputMode="decimal" autoComplete="off" />
        </Field>
      </fieldset>

      <fieldset className="grid gap-5">
        <legend className="mb-4 type-heading">Fetching</legend>
        <Field label="Highest quality" hint="The tallest picture fetched. A video offered only below it is fetched at its best.">
          <NativeSelect value={f.max_height} onChange={set('max_height')}>
            {heights.map(h => <option key={h} value={String(h)}>{h}p</option>)}
          </NativeSelect>
        </Field>
        <Field label="yt-dlp player client" hint="Which YouTube client yt-dlp asks as. visionos is fastest signed out; signed in, it is replaced by tv_downgraded. Empty lets yt-dlp choose.">
          <Input value={f.player_client} onChange={set('player_client')} autoComplete="off" spellCheck={false} />
        </Field>
        <Field label="Signed-in browser" hint="A browser on this server signed in to YouTube, such as chrome+gnomekeyring. A Premium account has no ad waits, so videos start sooner. Empty fetches signed out.">
          <Input value={f.cookies_from_browser} onChange={set('cookies_from_browser')} autoComplete="off" spellCheck={false} />
        </Field>
        <Field label="yt-dlp" hint="The command, or its full path." error={problems.ytdlp}>
          <Input value={f.ytdlp} onChange={set('ytdlp')} autoComplete="off" spellCheck={false} />
        </Field>
        <Field label="ffmpeg" hint="The command, or its full path." error={problems.ffmpeg}>
          <Input value={f.ffmpeg} onChange={set('ffmpeg')} autoComplete="off" spellCheck={false} />
        </Field>
      </fieldset>

      <div className="flex flex-wrap items-center gap-3">
        <AsyncButton type="submit" variant="default" phase={save.phase} error={save.error} labels={{ idle: 'Save settings', pending: 'Saving…', done: 'Saved' }} />
        {save.phase === 'error' && <p className="type-body-sm text-danger">{save.error} The settings were not changed.</p>}
      </div>
    </form>
  )
}

function Shown() {
  const load = useLoad({ queryKey: keys.shown, queryFn: api.shown })
  return (
    <DataView state={load} isEmpty={() => false} skeleton={<FormSkeleton />} empty={<EmptyState title="No filters">The server sent none.</EmptyState>}>
      {f => <ShownForm current={f} />}
    </DataView>
  )
}

/** The stream choices, in the words of what each leaves out. */
export const streamChoices: { value: StreamFilter; label: string }[] = [
  { value: 'current', label: 'Leave out streams live now or scheduled' },
  { value: 'all', label: 'Leave out every stream, past ones and premieres too' },
]

type ShownFields = { min: string; max: string; streams: StreamFilter }

const minutes = (seconds: number | null) => (seconds == null ? '' : String(Math.round((seconds / 60) * 100) / 100))
const seconds = (value: string) => (value.trim() ? Math.round(Number(value.trim()) * 60) : null)

/** What is wrong with the length fields, by field: each is empty (no limit) or minutes, 0 or more, and the shortest is not past the longest. */
export function shownProblems(f: ShownFields): Partial<Record<'min' | 'max', string>> {
  const one = (v: string, what: string) => {
    if (!v.trim()) return undefined
    const n = Number(v.trim())
    return Number.isFinite(n) && n >= 0 ? undefined : `Enter ${what} in minutes, or leave it empty for no limit.`
  }
  const found = { min: one(f.min, 'the shortest length'), max: one(f.max, 'the longest length') }
  if (!found.min && !found.max && f.min.trim() && f.max.trim() && Number(f.min) > Number(f.max)) found.max = 'Make this at least the shortest length.'
  return found
}

/** What the filters leave out now, as the finding under the form. */
export function describeShown(f: ShownFilters): string {
  return f.filtered ? `${format.count(f.filtered, 'video is', 'videos are')} left out by these now. They are still kept, and come back if the filters change.` : 'These leave no video out now.'
}

export function ShownForm({ current }: { current: ShownFilters }) {
  const queryClient = useQueryClient()
  const [f, setF] = useState<ShownFields>({ min: minutes(current.min_seconds), max: minutes(current.max_seconds), streams: current.streams })
  const [problems, setProblems] = useState<ReturnType<typeof shownProblems>>({})
  const set = (k: keyof ShownFields) => (e: { target: { value: string } }) => setF(old => ({ ...old, [k]: e.target.value }))

  const save = useAsyncAction(async () => {
    await api.saveShown({ min_seconds: seconds(f.min), max_seconds: seconds(f.max), streams: f.streams })
    // Every list and count on both sides reads through the filters.
    await Promise.all([keys.shown, keys.library, keys.channels, keys.videos, keys.system].map(queryKey => queryClient.invalidateQueries({ queryKey })))
  }, { describeError })

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    const found = shownProblems(f)
    setProblems(found)
    if (!Object.values(found).some(Boolean)) void save.run()
  }

  return (
    <form onSubmit={onSubmit} noValidate className="grid max-w-xl gap-8">
      <p className="type-body text-muted-foreground">{describeShown(current)}</p>
      <fieldset className="grid gap-5">
        <legend className="mb-4 type-heading">Length</legend>
        <Field label="Shortest video (minutes)" hint="Shorter videos are left out of every list. 3 leaves out most Shorts. Empty for no limit." error={problems.min}>
          <Input value={f.min} onChange={set('min')} inputMode="decimal" autoComplete="off" />
        </Field>
        <Field label="Longest video (minutes)" hint="Longer videos are left out of every list. Empty for no limit. A video whose length is not known is always shown." error={problems.max}>
          <Input value={f.max} onChange={set('max')} inputMode="decimal" autoComplete="off" />
        </Field>
      </fieldset>
      <fieldset className="grid gap-5">
        <legend className="mb-4 type-heading">Streams</legend>
        <Field label="Live streams" hint="A stream live now or scheduled cannot be played, so it is always left out until it ends. A past stream is checked daily in case its recording goes.">
          <NativeSelect value={f.streams} onChange={set('streams')}>
            {streamChoices.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
          </NativeSelect>
        </Field>
      </fieldset>
      <div className="flex flex-wrap items-center gap-3">
        <AsyncButton type="submit" variant="default" phase={save.phase} error={save.error} labels={{ idle: 'Save filters', pending: 'Saving…', done: 'Saved' }} />
        {save.phase === 'error' && <p className="type-body-sm text-danger">{save.error} The filters were not changed.</p>}
      </div>
    </form>
  )
}

function Appearance() {
  return (
    <div className="grid max-w-xl gap-3">
      <ColorSchemeChoice legend="Colour scheme" />
      <p className="type-body-sm text-muted-foreground">Kept in this browser only.</p>
    </div>
  )
}

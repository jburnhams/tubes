// The one question: "How is the server set up, and how do I change it?" Five tabs whose choice
// lives in the URL (?tab=skipping, ?tab=shown, ?tab=breaks, ?tab=appearance). General is one form over the server's settings, grouped by
// what they decide (the cache, what is fetched, the tools, the sound: whether every video plays at one loudness, and which); the fields start
// from what the server holds (rendered inside DataView's ready state, so never blank while
// loading), problems are said under their field, and saving is one AsyncButton. The server checks
// again and says why it refused, under the button. Skipping is one ChoiceGroup per kind of segment
// (Off, Ask, Skip: what the player does in it, src/tubes/segments.py), saved the same way.
// Shown videos is a third form, over what the watching side lists (kept in the server's database,
// not its settings file, so it has its own read and its own Save): the shortest and longest length,
// in minutes with empty for no limit, which streams are left out, the country the server watches from
// (YouTube's region limits; a video a fetch was refused for here is hidden whatever this says), the
// spoken languages shown (a Checkbox per language the library has, with its count, so the choice is
// among real ones) and whether only videos with the uploader's captions are shown. Dubbed audio tracks
// are not offered: the Data API does not list them. Its finding is how many videos the filters leave
// out now, which it says again after a save. Breaks is a form over the break_* settings: whether the Watch page
// pauses every so many minutes of playing to show another page over the picture (src/watch/break.tsx), which
// page, how often and the longest a break lasts; it says how the page ends a break, for whoever writes one.
// Appearance is Strata's ColorSchemeChoice.
import { useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { AsyncButton, Checkbox, ChoiceGroup, ColorSchemeChoice, DataView, EmptyState, Field, Input, NativeSelect, PageHeader, Skeleton, Tabs, format, useAsyncAction, useLoad, type Choice } from 'strata-react'
import { api, describeError, folderProblem, keys, numberProblem, type SegmentKind, type Settings, type ShownFilters, type SkipMode, type StreamFilter } from '../api'

const tabs = [
  { value: 'general', label: 'General' },
  { value: 'skipping', label: 'Skipping' },
  { value: 'shown', label: 'Shown videos' },
  { value: 'breaks', label: 'Breaks' },
  { value: 'appearance', label: 'Appearance' },
]

/** The heights a fetch can be capped at. */
export const heights = [720, 1080, 1440, 2160]

export function SettingsScreen() {
  return (
    <>
      <PageHeader title="Settings" scope="Kept on the server, for every browser that opens the app" />
      <Tabs param="tab" items={tabs} label="Settings">
        {tab => (tab === 'appearance' ? <Appearance /> : tab === 'skipping' ? <Skipping /> : tab === 'shown' ? <Shown /> : tab === 'breaks' ? <Breaks /> : <General />)}
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

type Fields = Record<'cache_dir' | 'cache_limit_gb' | 'half_life_days' | 'protect_days' | 'max_height' | 'player_client' | 'cookies_from_browser' | 'ytdlp' | 'ffmpeg' | 'loudness_target', string>

/** The loudness every video can be brought to (LUFS), with what each is like. */
export const loudnessTargets = [
  { value: '-14', label: '-14 LUFS: as loud as YouTube plays music' },
  { value: '-16', label: '-16 LUFS: the usual streaming level' },
  { value: '-18', label: '-18 LUFS' },
  { value: '-20', label: '-20 LUFS' },
  { value: '-23', label: '-23 LUFS: broadcast television' },
]

/** Every problem the form can see before sending, by field. */
export function settingsProblems(f: Omit<Fields, 'loudness_target'>): Partial<Record<keyof Fields, string>> {
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
    loudness_target: String(current.loudness_target),
  })
  const [even, setEven] = useState(current.loudness_on === 'true')
  const [problems, setProblems] = useState<ReturnType<typeof settingsProblems>>({})
  const set = (k: keyof Fields) => (e: { target: { value: string } }) => setF(old => ({ ...old, [k]: e.target.value }))

  const save = useAsyncAction(async () => {
    await api.saveSettings({
      cache_dir: f.cache_dir.trim(), cache_limit_gb: Number(f.cache_limit_gb), half_life_days: Number(f.half_life_days), protect_days: Number(f.protect_days),
      max_height: Number(f.max_height), player_client: f.player_client.trim(), cookies_from_browser: f.cookies_from_browser.trim(), ytdlp: f.ytdlp.trim(), ffmpeg: f.ffmpeg.trim(),
      loudness_on: even ? 'true' : 'false', loudness_target: Number(f.loudness_target),
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

      <fieldset className="grid gap-5">
        <legend className="mb-4 type-heading">Sound</legend>
        <Checkbox label="Play every video at the same loudness" detail="Each copy is measured on this server. A quiet video is raised only as far as its loudest moment allows, so nothing clips; 100% on the player is this level, and Louder goes on to 200%." checked={even} onCheckedChange={setEven} />
        <Field label="Loudness" hint="Lower leaves more room to raise quiet videos without reaching their peaks.">
          <NativeSelect value={f.loudness_target} onChange={set('loudness_target')} disabled={!even}>
            {/* A level set another way (`tubes set loudness_target -17`) is offered too, so the form never changes it unasked. */}
            {(loudnessTargets.some(t => t.value === f.loudness_target) ? loudnessTargets : [...loudnessTargets, { value: f.loudness_target, label: `${f.loudness_target} LUFS` }]).map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </NativeSelect>
        </Field>
      </fieldset>

      <div className="flex flex-wrap items-center gap-3">
        <AsyncButton type="submit" variant="default" phase={save.phase} error={save.error} labels={{ idle: 'Save settings', pending: 'Saving…', done: 'Saved' }} />
        {save.phase === 'error' && <p className="type-body-sm text-danger">{save.error} The settings were not changed.</p>}
      </div>
    </form>
  )
}

/** What the player can do in a kind of segment. */
export const skipChoices: Choice[] = [
  { value: 'off', label: 'Off', detail: 'Play it as it is, and leave it off the timeline.' },
  { value: 'ask', label: 'Ask', detail: 'Show a Skip button over the picture while it plays.' },
  { value: 'auto', label: 'Skip', detail: 'Skip it as it starts, with Undo for a few seconds.' },
]

function Skipping() {
  const load = useLoad({ queryKey: keys.skipping, queryFn: api.skipping })
  return (
    <DataView state={load} isEmpty={kinds => kinds.length === 0} skeleton={<FormSkeleton />} empty={<EmptyState title="Nothing to skip">The server names no kinds of segment.</EmptyState>}>
      {kinds => <SkippingForm kinds={kinds} />}
    </DataView>
  )
}

/** One ChoiceGroup per kind of segment (SponsorBlock's categories; iPlayer's intros and credits come in as Intro and Credits), saved together. */
export function SkippingForm({ kinds }: { kinds: SegmentKind[] }) {
  const queryClient = useQueryClient()
  const [modes, setModes] = useState<Record<string, SkipMode>>(() => Object.fromEntries(kinds.map(k => [k.id, k.mode])))
  const save = useAsyncAction(async () => {
    await api.saveSettings(Object.fromEntries(Object.entries(modes).map(([id, mode]) => [`skip_${id}`, mode])) as Partial<Settings>)
    await Promise.all([keys.skipping, keys.settings, ['segments']].map(queryKey => queryClient.invalidateQueries({ queryKey })))
  }, { describeError })
  return (
    <form onSubmit={e => { e.preventDefault(); void save.run() }} noValidate className="grid max-w-xl gap-8">
      <p className="type-body text-muted-foreground">
        What the player does in each kind of segment. YouTube videos get theirs from SponsorBlock, which viewers mark up; iPlayer marks its own intros and credits.
      </p>
      {kinds.map(k => (
        <div key={k.id} className="grid gap-2">
          <ChoiceGroup legend={k.label} name={`skip_${k.id}`} choices={skipChoices} value={modes[k.id]} onChange={v => setModes(old => ({ ...old, [k.id]: v as SkipMode }))} />
          <p className="type-body-sm text-muted-foreground">{k.detail}</p>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-3">
        <AsyncButton type="submit" variant="default" phase={save.phase} error={save.error} labels={{ idle: 'Save skipping', pending: 'Saving…', done: 'Saved' }} />
        {save.phase === 'error' && <p className="type-body-sm text-danger">{save.error} Nothing was changed.</p>}
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

type ShownFields = { min: string; max: string; streams: StreamFilter; region: string; languages: string[]; unknown: 'show' | 'hide'; captions: 'any' | 'only'; clips: 'show' | 'hide'; promos: 'show' | 'hide' }

/** A language's name in English (`fr` is French), else its code. */
export function languageName(code: string): string {
  try { return String(new Intl.DisplayNames(['en'], { type: 'language', fallback: 'code' }).of(code)) } catch { return code }      // an ill-formed code throws
}

const minutes = (seconds: number | null) => (seconds == null ? '' : String(Math.round((seconds / 60) * 100) / 100))
const seconds = (value: string) => (value.trim() ? Math.round(Number(value.trim()) * 60) : null)

/** What is wrong with the length fields, by field: each is empty (no limit) or minutes, 0 or more, and the shortest is not past the longest. */
export function shownProblems(f: ShownFields): Partial<Record<'min' | 'max' | 'region', string>> {
  const one = (v: string, what: string) => {
    if (!v.trim()) return undefined
    const n = Number(v.trim())
    return Number.isFinite(n) && n >= 0 ? undefined : `Enter ${what} in minutes, or leave it empty for no limit.`
  }
  const found: Partial<Record<'min' | 'max' | 'region', string>> = { min: one(f.min, 'the shortest length'), max: one(f.max, 'the longest length') }
  if (f.region.trim() && !/^[A-Za-z]{2}$/.test(f.region.trim())) found.region = 'Enter the country as two letters, such as GB, or leave it empty.'
  if (!found.min && !found.max && f.min.trim() && f.max.trim() && Number(f.min) > Number(f.max)) found.max = 'Make this at least the shortest length.'
  return found
}

/** What the filters leave out now, as the finding under the form. */
export function describeShown(f: ShownFilters): string {
  return f.filtered ? `${format.count(f.filtered, 'video is', 'videos are')} left out by these now. They are still kept, and come back if the filters change.` : 'These leave no video out now.'
}

export function ShownForm({ current }: { current: ShownFilters }) {
  const queryClient = useQueryClient()
  const [f, setF] = useState<ShownFields>({
    min: minutes(current.min_seconds), max: minutes(current.max_seconds), streams: current.streams, region: current.region ?? '',
    languages: current.languages, unknown: current.unknown_language, captions: current.captions, clips: current.clips, promos: current.promos,
  })
  const counts = current.language_counts
  const known = counts.filter((c): c is { code: string; videos: number } => c.code != null)
  // A chosen language the library no longer has stays listed, so it can be cleared.
  const offered = [...known, ...f.languages.filter(l => !known.some(c => c.code === l)).map(code => ({ code, videos: 0 }))]
  const unknownCount = counts.find(c => c.code == null)?.videos ?? 0
  const toggle = (code: string, on: boolean) => setF(old => ({ ...old, languages: on ? [...old.languages, code].sort() : old.languages.filter(l => l !== code) }))
  const [problems, setProblems] = useState<ReturnType<typeof shownProblems>>({})
  const set = (k: Exclude<keyof ShownFields, 'languages'>) => (e: { target: { value: string } }) => setF(old => ({ ...old, [k]: e.target.value }))

  const save = useAsyncAction(async () => {
    await api.saveShown({
      min_seconds: seconds(f.min), max_seconds: seconds(f.max), streams: f.streams, region: f.region.trim().toUpperCase() || null,
      languages: f.languages, unknown_language: f.unknown, captions: f.captions, clips: f.clips, promos: f.promos,
    })
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
      <fieldset className="grid gap-5">
        <legend className="mb-4 type-heading">Clips and promos</legend>
        <Field label="Clips" hint={`Part of something longer: a scene, a moment, a short cut from an episode. ${format.count(current.known_clips, 'video is', 'videos are')} known to be one. Several episodes joined are not clips, and a video nothing is known of is always shown. A channel’s own page shows its clips whatever is chosen here.`}>
          <NativeSelect value={f.clips} onChange={set('clips')}>
            <option value="show">Show them</option>
            <option value="hide">Leave them out</option>
          </NativeSelect>
        </Field>
        <Field label="Promos" hint={`Trailers, adverts and announcements. ${format.count(current.known_promos, 'video is', 'videos are')} known to be one. A channel’s own page shows them too.`}>
          <NativeSelect value={f.promos} onChange={set('promos')}>
            <option value="show">Show them</option>
            <option value="hide">Leave them out</option>
          </NativeSelect>
        </Field>
      </fieldset>
      <fieldset className="grid gap-5">
        <legend className="mb-4 type-heading">Country</legend>
        <Field label="Country the server watches from" hint="Two letters, such as GB. Videos YouTube says do not play there are left out. Empty does not check. A video YouTube refuses to fetch as not available here is always left out." error={problems.region}>
          <Input value={f.region} onChange={set('region')} autoComplete="off" spellCheck={false} maxLength={2} />
        </Field>
      </fieldset>
      <fieldset className="grid gap-3">
        <legend className="mb-4 type-heading">Languages</legend>
        <p className="type-body-sm text-muted-foreground">
          {offered.length ? 'Only videos spoken in the chosen languages are shown; none chosen shows every language. A video that does not say its language goes by its channel’s.' : 'No video in the library says its language yet. Syncs and rechecks fill it in.'}
        </p>
        {offered.map(c => (
          <Checkbox key={c.code} label={languageName(c.code)} detail={format.count(c.videos, 'video')} checked={f.languages.includes(c.code)} onCheckedChange={on => toggle(c.code, on)} />
        ))}
        <Field label="Videos whose language is not known" hint={`${format.count(unknownCount, 'video says', 'videos say')} no language, nor does its channel. Used only while a language is chosen.`}>
          <NativeSelect value={f.unknown} onChange={set('unknown')}>
            <option value="show">Show them</option>
            <option value="hide">Leave them out</option>
          </NativeSelect>
        </Field>
      </fieldset>
      <fieldset className="grid gap-5">
        <legend className="mb-4 type-heading">Subtitles</legend>
        <Field label="Subtitles" hint="YouTube lists only captions the uploader added, not its automatic ones, and does not list dubbed audio. iPlayer does not say, so its episodes are always kept.">
          <NativeSelect value={f.captions} onChange={set('captions')}>
            <option value="any">Show every video</option>
            <option value="only">Only videos with subtitles the uploader added</option>
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

function Breaks() {
  const load = useLoad({ queryKey: keys.settings, queryFn: api.settings })
  return (
    <DataView state={load} isEmpty={() => false} skeleton={<FormSkeleton />} empty={<EmptyState title="No settings">The server sent none.</EmptyState>}>
      {s => <BreaksForm current={s} />}
    </DataView>
  )
}

/** Whether `url` is a path on this server (not `//host`) or an http(s) link a browser can parse, with a host and no spaces (settings.py `page_url`). */
export function pageLink(url: string): boolean {
  if (/\s/.test(url)) return false
  if (url.startsWith('/')) return !url.startsWith('//')
  try {
    const u = new URL(url)
    return (u.protocol === 'http:' || u.protocol === 'https:') && u.hostname !== ''
  } catch { return false }
}

type BreakFields = { on: boolean; url: string; minutes: string; limit: string }

/** What is wrong with the break fields, by field: the page is an http(s) link or a path on this server (needed while breaks are on), the
 *  minutes are numbers in the server's ranges (settings.py). */
export function breakProblems(f: BreakFields): Partial<Record<'url' | 'minutes' | 'limit', string>> {
  const url = f.url.trim()
  const between = (v: string, lo: number, hi: number, what: string) => {
    const n = Number(v.trim())
    return v.trim() && Number.isFinite(n) && n >= lo && n <= hi ? undefined : `Enter ${what} in minutes, from ${lo} to ${hi}.`
  }
  return {
    url: url ? (pageLink(url) ? undefined : 'Enter a link starting http:// or https://, or a path on this server starting with /.') : f.on ? 'Enter the page to show, or turn breaks off.' : undefined,
    minutes: between(f.minutes, 1, 1440, 'the time between breaks'),
    limit: between(f.limit, 1, 240, 'the longest break'),
  }
}

export function BreaksForm({ current }: { current: Settings }) {
  const queryClient = useQueryClient()
  const [f, setF] = useState<BreakFields>({ on: current.break_on === 'true', url: current.break_url, minutes: String(current.break_minutes), limit: String(current.break_limit_minutes) })
  const [problems, setProblems] = useState<ReturnType<typeof breakProblems>>({})
  const set = (k: 'url' | 'minutes' | 'limit') => (e: { target: { value: string } }) => setF(old => ({ ...old, [k]: e.target.value }))
  const save = useAsyncAction(async () => {
    await api.saveSettings({ break_on: f.on ? 'true' : 'false', break_url: f.url.trim(), break_minutes: Number(f.minutes), break_limit_minutes: Number(f.limit) })
    await Promise.all([keys.settings, keys.break].map(queryKey => queryClient.invalidateQueries({ queryKey })))
  }, { describeError })
  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    const found = breakProblems(f)
    setProblems(found)
    if (!Object.values(found).some(Boolean)) void save.run()
  }
  return (
    <form onSubmit={onSubmit} noValidate className="grid max-w-xl gap-8">
      <p className="type-body text-muted-foreground">
        Every so many minutes of playing, the video pauses and another page, such as a short game, is shown over the picture until it is done. Only time spent playing counts, in each browser across videos.
      </p>
      <fieldset className="grid gap-5">
        <legend className="mb-4 type-heading">Break</legend>
        <Checkbox label="Take breaks" detail="Off keeps the page below for next time." checked={f.on} onCheckedChange={on => setF(old => ({ ...old, on }))} />
        <Field label="Page to show" hint="An http(s) link, or a path on this server such as /games/play. It fills the picture, so a page made for that size works best." error={problems.url}>
          <Input value={f.url} onChange={set('url')} autoComplete="off" spellCheck={false} />
        </Field>
        <Field label="Minutes of playing between breaks" error={problems.minutes}>
          <Input value={f.minutes} onChange={set('minutes')} inputMode="decimal" autoComplete="off" />
        </Field>
        <Field label="Longest break (minutes)" hint="The video plays on after this even if the page never says it is done, so a page that fails to load cannot hold it." error={problems.limit}>
          <Input value={f.limit} onChange={set('limit')} inputMode="decimal" autoComplete="off" />
        </Field>
      </fieldset>
      <p className="type-body-sm text-muted-foreground">
        The page ends the break by sending <code>{"{ type: 'tubes:done' }"}</code> to its parent with <code>postMessage</code>. There is no close button. A page on another server must allow being shown in a frame.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <AsyncButton type="submit" variant="default" phase={save.phase} error={save.error} labels={{ idle: 'Save breaks', pending: 'Saving…', done: 'Saved' }} />
        {save.phase === 'error' && <p className="type-body-sm text-danger">{save.error} The breaks were not changed.</p>}
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

import { useCallback, useEffect, useState } from 'react'
import { apiGet, errorText } from './client'

/**
 * One in-flight request per URL, one cached body per URL, shared by every
 * card and every hub (v17h §2).
 *
 * Not a loader. The cards keep their own effects, their own error slots and
 * their own reloads — v17h §0 rules all three deliberate — and this module
 * owns only the wire underneath them. What it buys is that four JobButtons
 * asking whether a run is in flight is one request, that the hub and the Why
 * panel share one decomposition, and that navigating away from This Week and
 * back does not ask the server the same settled question a third time.
 */

interface Entry {
  /** Set once resolved. `undefined` means "not held"; `null` is a 204. */
  body?: unknown
  /** The request in flight, so a second caller joins rather than starts. */
  promise?: Promise<unknown>
  /** Mounted readers, told to re-request when the URL is invalidated. */
  subscribers: Set<() => void>
}

const entries = new Map<string, Entry>()

function entryFor(path: string): Entry {
  const held = entries.get(path)
  if (held !== undefined) return held
  const fresh: Entry = { subscribers: new Set() }
  entries.set(path, fresh)
  return fresh
}

function request(path: string): Promise<unknown> {
  const entry = entryFor(path)
  if (entry.promise !== undefined) return entry.promise
  const promise: Promise<unknown> = apiGet<unknown>(path)
    .then((body) => {
      // Only if this is still the question being asked. An invalidate that
      // lands mid-flight has already declared the answer stale, and a card
      // that just ran a job would otherwise be handed the artifact as it
      // stood before the run — the one bug this module could introduce that
      // the per-card fetching it replaces could not.
      if (entry.promise === promise) {
        entry.body = body
        entry.promise = undefined
      }
      return body
    })
    .catch((e) => {
      // Never cached. A cold-start failure that stuck would turn one bad
      // moment into a permanently dead card, which is the opposite of the
      // isolation this module exists to keep. The entry itself survives so
      // its subscribers do; only the promise goes, and only if it is still
      // ours to clear.
      if (entry.promise === promise) entry.promise = undefined
      throw e
    })
  entry.promise = promise
  return promise
}

/**
 * Drop a URL's body and re-request it for every reader mounted on it.
 *
 * Refetches rather than merely forgetting: a card that has already painted
 * must not keep a body the job it just ran has replaced. Readers all join the
 * one promise `request` holds, so an invalidate is one request however many
 * cards are watching.
 */
export function invalidate(path: string): void {
  const entry = entries.get(path)
  if (entry === undefined) return
  entry.body = undefined
  entry.promise = undefined
  // Over a copy, because a reader told to re-request may unmount before the
  // next one is reached — a job that finishes as the user leaves the tab —
  // and a set mutated under its own iteration would drop whoever came after.
  for (const notify of [...entry.subscribers]) notify()
}

/** Put bodies in the cache without a request. For tests. */
export function seedPageData(bodies: Record<string, unknown>): void {
  for (const [path, body] of Object.entries(bodies)) {
    entryFor(path).body = body
  }
}

/**
 * Forget everything. For tests only.
 *
 * Module state outlives a component, a test case and a test file alike —
 * which is the point in a browser and a leak in a runner, exactly as
 * `useJob`'s remembered slots are. The shared vitest setup calls it before
 * each test.
 */
export function resetPageData(): void {
  entries.clear()
}

export interface PageData<T> {
  data: T | null
  error: string | null
  reload: () => void
}

/**
 * @param path The URL to read, or `null` to read nothing at all — which is
 *   how a card waits for a gameweek or a code list without inventing a URL it
 *   does not yet mean.
 */
export function usePageData<T>(path: string | null): PageData<T> {
  // Read from the cache before the first paint, not in an effect: a card
  // remounting under a Radix tab with a warm entry then renders its body
  // immediately, with no empty frame and no request.
  const [data, setData] = useState<T | null>(() => {
    const held = path === null ? undefined : entries.get(path)?.body
    return held === undefined ? null : held as T
  })
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // A new URL inherits neither the old one's body nor its error. State
    // survives the path change; the answer to the previous question must not
    // be painted under this one.
    setError(null)
    if (path === null) {
      setData(null)
      return
    }
    // Closed over by `ask`, so a response can only reach the reader that is
    // still mounted on this path. Cleanup runs before the next effect, so a
    // remount or a path change leaves the outgoing closure dead and the
    // incoming one alive.
    let alive = true
    // Counts this reader's asks, so only the last one's answer is painted.
    // An invalidate lands while the first request is still in flight — a job
    // finishing during a cold start is exactly that — and the older answer,
    // which is the artifact as it stood before the run, settles second and
    // would otherwise be the one left on screen.
    let asked = 0
    const ask = () => {
      if (!alive) return
      const mine = ++asked
      const current = () => alive && mine === asked
      request(path)
        .then((body) => {
          if (!current()) return
          setData(body as T)
          setError(null)
        })
        .catch((e) => {
          if (!current()) return
          setData(null)
          setError(errorText(e))
        })
    }
    const entry = entryFor(path)
    entry.subscribers.add(ask)
    if (entry.body !== undefined) {
      setData(entry.body as T)
      setError(null)
    } else {
      setData(null)
      ask()
    }
    return () => {
      alive = false
      entry.subscribers.delete(ask)
    }
  }, [path])

  const reload = useCallback(() => {
    if (path !== null) invalidate(path)
  }, [path])

  return { data, error, reload }
}

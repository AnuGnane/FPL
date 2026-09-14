// The module itself, not the kit barrel: the barrel pulls in cards and
// modals that read through this layer, and `api/` importing all of it back
// is a cycle for the sake of one function.
import { toast } from '../kit/Toast'
import { apiPost, errorText } from './client'
import { invalidate, invalidatePrefix } from './pageData'

/**
 * Write one setting, then clear the cached reads it disturbs.
 *
 * One copy of "POST `/api/settings` then invalidate", which was written three
 * times — `League.tsx:141`, `LadderCard.tsx:212` and `SettingsTab.tsx:145` —
 * and cut out in v18f §2.1. Every write of a setting clears `/api/settings`
 * itself, because the ladder card and the Model hub's Settings tab both hold
 * that panel (v17h §5); what differs between the three is the *other* URL a
 * particular row disturbs, so those are the caller's to name and they stay
 * literal at the call site, where `api/invalidation.test.tsx` can read them.
 *
 * What a refusal *says* also stays with the caller: two of the three print it
 * next to the control rather than in a toast, and a toast for all three would
 * have been a visible change dressed as a refactor. So `onError` is the
 * caller's when it has one, and the toast — spec D3's sentence, `Could not
 * <what> — <why>` — is the default for the one that wants it.
 */
export interface SettingWriteOptions {
  /** Exact URLs to clear besides `/api/settings`. A function of the key when
   *  the caller writes rows that do not all disturb the same reads — the
   *  Settings tab reaches the leagues overview through its whitelist only. */
  also?: readonly string[] | ((key: string) => readonly string[])
  /** Prefixes to sweep besides those URLs. The League hub's case: its race,
   *  rivals and sim URLs carry the league id, which is the very thing a focus
   *  write changes, so there is no single URL to name (v18e §2.5). */
  alsoPrefix?: readonly string[]
  /** What a refusal does when it is not a toast. The key is handed back with
   *  it because the Settings tab files the message under the row that failed. */
  onError?: (e: unknown, key: string) => void
}

/**
 * `true` when the write landed, so a caller with something to do next — the
 * ladder card rebuilds — can tell a refusal from a save without catching the
 * exception the hook has already reported.
 */
export type SettingWriter = (key: string, value: unknown,
                             what?: string) => Promise<boolean>

export function useSettingWrite(options: SettingWriteOptions = {}):
SettingWriter {
  const { also, alsoPrefix = [], onError } = options
  return async (key: string, value: unknown, what?: string) => {
    try {
      await apiPost('/api/settings', { key, value })
    } catch (e) {
      if (onError) onError(e, key)
      else toast('negative', `Could not ${what} — ${errorText(e)}`)
      return false
    }
    // The panel first, then whatever else the row moved: the settings entry
    // is the one every caller shares, and a reader of it is on screen in two
    // hubs at once.
    invalidate('/api/settings')
    const urls = typeof also === 'function' ? also(key) : (also ?? [])
    for (const url of urls) invalidate(url)
    for (const prefix of alsoPrefix) invalidatePrefix(prefix)
    return true
  }
}

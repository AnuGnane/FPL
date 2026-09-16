import * as Dialog from '@radix-ui/react-dialog'
import { useState } from 'react'
import { usePageData } from '../api/pageData'
import type { PlayerExplain } from '../types'
import Bar from './Bar'
import { buttonClass } from './Button'
import Callout from './Callout'
import Chip from './Chip'
import PosBadge from './PosBadge'
import { fmtNum, fmtPct } from './format'
import { TABLE_CLASS, TR_CLASS, tdClass } from './table'
import useOpener from './useOpener'

// One modal, reachable from every player name on every page (spec §3.6).
export default function ExplainModal(
  { code, onClose }: { code: number; onClose: () => void },
) {
  // v18e §2.3. Every caller mounts this modal only while it is open — the
  // name, the player card and the three hubs all render it behind an `open`
  // or a non-null code — so the hook is handed a path only when the modal
  // exists, and a closed modal reads nothing. The ask counter inside it is
  // what the `live` flag here used to be: a second click while the first
  // request is in flight cannot repaint the modal with the player the user
  // has already moved off.
  const page = usePageData<PlayerExplain>(`/api/players/${code}/explain`)
  const data = page.data
  const error = page.error
  // Not a src swap to a local placeholder: the backend already answers a dead
  // upstream with the bundled silhouette (v9a), so reaching this means the
  // *fallback* failed too, and the honest response is no picture.
  const [photoFailed, setPhotoFailed] = useState(false)
  const returnFocus = useOpener()

  // A new player is a new photo, and the previous one's failure says nothing
  // about it.
  //
  // v19h §2.1: a guarded render-phase set, not a `key` at the call site — the
  // modal is mounted only while it is open and a remount would re-run the
  // focus handling Radix and `useOpener` own between them.
  const [seenCode, setSeenCode] = useState(code)
  if (seenCode !== code) {
    setSeenCode(code)
    setPhotoFailed(false)
  }

  // v18f §2.2. Radix owns the modal behaviour that was three hand-rolled
  // effects: the focus trap, the return of focus to whatever opened it,
  // Escape, the overlay click, and the `aria-hidden` it puts over the page
  // behind. The caller mounts this only while it is open, so `open` is the
  // constant `true` and closing is an unmount.
  return (
    <Dialog.Root open onOpenChange={(next) => { if (!next) onClose() }}>
      <Dialog.Portal>
        {/* Content nests inside the overlay because the overlay is also the
            scroll container: a breakdown taller than the window scrolls the
            scrim with it, exactly as it did before Radix. */}
        <Dialog.Overlay
          className="fixed inset-0 z-50 flex items-start justify-center
                     overflow-y-auto bg-scrim p-4 sm:p-8"
          data-testid="modal-backdrop"
        >
          <Dialog.Content
            className="w-full max-w-2xl rounded-ctl border border-border bg-base"
            aria-label="Expected points explained"
            // Radix marks the page behind with `aria-hidden` and leaves this
            // off; the attribute was on the hand-rolled dialog and costs
            // nothing beside it, so the modal keeps saying it is one.
            aria-modal="true"
            // The heading below is the *player*, and it is "Expected points"
            // until his payload lands — so the dialog would be announced by two
            // different names a second apart. `aria-labelledby` is unset so the
            // stable sentence above is the name, as it was before Radix; the
            // Title stays because it is the visible heading, and because Radix
            // asks for one. Nothing describes the dialog in a sentence, so the
            // description is unset rather than pointed at a number.
            aria-labelledby={undefined}
            aria-describedby={undefined}
            onCloseAutoFocus={returnFocus}
          >
            <header className="flex items-start justify-between gap-3 border-b
                               border-divider px-4 py-3">
              <div className="flex items-start gap-3">
                {!photoFailed && (
                  <img
                    data-testid="explain-photo"
                    src={`/api/assets/photo/${code}`}
                    // Requested while `data` is still loading, deliberately: the
                    // photo depends only on `code`, so it lands before the
                    // breakdown and the header stops reflowing when it arrives.
                    //
                    // Decorative: the name is beside it in an h2, and a screen
                    // reader reading "photo of Haaland" before the heading that
                    // says Haaland is one statement too many.
                    alt=""
                    width={44}
                    height={56}
                    onError={() => setPhotoFailed(true)}
                    className="rounded-ctl border border-border bg-raised"
                  />
                )}
                <div>
                  {data
                    ? (
                      <>
                        <Dialog.Title
                          className="flex items-center gap-2 text-base text-text"
                        >
                          <PosBadge pos={data.position} />
                          {data.name}
                        </Dialog.Title>
                        <p className="label mt-1">
                          {data.team_name} · {fmtNum(data.ep_next)} xPts ·{' '}
                          {/* v12 W4 §5.4. The one place a player's *code* is
                              printed. data/set_pieces.toml is keyed by code —
                              element ids are remapped every summer and codes are
                              not — and until this line there was nowhere in the
                              app to read one off, which made the override file
                              unwritable without a detour through the API. */}
                          <span className="text-text-muted">code {data.code}</span>
                        </p>
                      </>
                      )
                    : <Dialog.Title className="label">Expected points</Dialog.Title>}
                </div>
              </div>
              <Dialog.Close className={buttonClass('ghost')}>
                Close
              </Dialog.Close>
            </header>
            <div className="flex flex-col gap-4 p-4">
              {error && <p className="text-down">{error}</p>}
              {!data && !error && <p className="text-text-muted">Loading…</p>}
              {data && (
                <>
                  {/* A double gameweek arrives as two fixture blocks; the sum is
                      the number that decides a captaincy, so state it. */}
                  {Object.entries(
                    data.fixtures.reduce<Record<number, number[]>>(
                      (acc, fixture) => {
                        acc[fixture.gw] = [...(acc[fixture.gw] ?? []), fixture.ep]
                        return acc
                      }, {}),
                  )
                    .filter(([, eps]) => eps.length > 1)
                    .map(([gw, eps]) => (
                      <Callout key={gw} className="tn">
                        GW{gw} total:{' '}
                        {Math.round(eps.reduce((a, b) => a + b, 0) * 100) / 100}
                        {' '}xPts across {eps.length} fixtures
                      </Callout>
                    ))}
                  {data.fixtures.map((fixture, index) => (
                    // A double can be two fixtures against the same opponent, so
                    // the index is part of the key.
                    <section key={`${fixture.gw}-${fixture.opponent}-${index}`}>
                      <h3 className="label mb-2">
                        GW{fixture.gw} {fixture.home ? 'vs' : 'at'}{' '}
                        {fixture.opponent} — {fmtNum(fixture.ep)} xPts
                      </h3>
                      <div className="overflow-x-auto">
                      <table className={TABLE_CLASS}>
                        <tbody>
                          {fixture.components.map((component) => (
                            <tr key={component.label} className={TR_CLASS}>
                              <td className={`${tdClass()} text-text-secondary`}>
                                {component.label}
                              </td>
                              <td className={`${tdClass(true)} w-16 text-text`}>
                                {fmtNum(component.points)}
                              </td>
                              <td className={`${tdClass()} w-1/2`}>
                                {/* Against a fixed 12-point scale so bars compare
                                    between two players, not only within one. */}
                                <Bar width="full"
                                     fraction={Math.abs(component.points) / 12}
                                     tone={component.points < 0 ? 'down' : 'up'} />
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      </div>
                      <p className="mt-2 text-text-muted">
                        Minutes: P(play) {fmtPct(fixture.minutes.p_play)},
                        P(60+) {fmtPct(fixture.minutes.p60)} · calibration{' '}
                        <span className="tn">
                          {fixture.calibration_delta >= 0 ? '+' : ''}
                          {fixture.calibration_delta}
                        </span>
                      </p>
                      <p className="mt-1 text-text-muted">
                        {fixture.odds.weight > 0
                          ? `Odds blend ${Math.round(fixture.odds.weight * 100)}%: `
                            + `clean sheet ${fixture.odds.p_cs_model} (model) → `
                            + `${fixture.odds.p_cs_blended} (blended), goals `
                            + `against ${fixture.odds.e_gc_model} → `
                            + `${fixture.odds.e_gc_blended}`
                          : 'No market odds for this fixture — model output only. '
                            + 'Add an odds key for market-implied numbers.'}
                      </p>
                    </section>
                  ))}
                  <section>
                    <h3 className="label mb-2">Next fixtures</h3>
                    <ul className="flex flex-wrap gap-2">
                      {data.next_fixtures.map((fixture) => (
                        <li key={`${fixture.gw}-${fixture.opponent}`}>
                          <Chip>
                            <span className="tn">GW{fixture.gw}</span>{' '}
                            {fixture.home ? 'vs' : 'at'} {fixture.opponent}
                          </Chip>
                        </li>
                      ))}
                    </ul>
                  </section>
                  <p className="text-text-muted">
                    <span className="label">Set pieces</span>{' '}
                    penalties <span className="tn">
                      {data.set_pieces.penalties ?? '–'}
                    </span>, free kicks <span className="tn">
                      {data.set_pieces.free_kicks ?? '–'}
                    </span>, corners <span className="tn">
                      {data.set_pieces.corners ?? '–'}
                    </span>
                    {/* v12 W4 §5.4. The three numbers above are FPL's unless the
                        user's data/set_pieces.toml named him, and a reader who
                        corrected a taker is entitled to see that his correction
                        reached the panel. Read through `?? []` because the field
                        is default-empty on the server: a payload that predates it
                        means "nothing overridden", and a missing badge is a
                        better answer than a modal that throws. */}
                    {(data.set_pieces_manual ?? []).length > 0 && (
                      <>
                        {' '}
                        <Chip title={'Your override: '
                                + (data.set_pieces_manual ?? []).join(', ')}>
                          manual
                        </Chip>
                      </>
                    )}
                  </p>
                </>
              )}
            </div>
          </Dialog.Content>
        </Dialog.Overlay>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

import Chip from './Chip'
import { fmtNum } from './format'
import { difficultyTone } from './scale'
import type { NextFixture } from '../types'

/**
 * One player, drawn as FPL draws him: the shirt, the name, the club, the
 * number, and who he plays next.
 *
 * Kit-level and sized rather than hub-level and fixed (spec D4), because
 * every lane that mentions a player wants the same object at a different
 * scale — the pitch draws him large, and v9b's Live rows, league compare and
 * review lanes want him small. Building the small size now and leaving it
 * unused is cheaper than discovering in v9b that the large one hard-codes a
 * pitch.
 *
 * Every image comes from `/api/assets/`, never from premierleague.com: the
 * frontend speaks only to this backend (spec D1), and a hotlinked shirt would
 * be the one request on the page that tells a third party who is reading it.
 *
 * A player with no `teamCode` is not asked about at all. The endpoint's
 * allowlist is the banked bootstrap, so a request for shirt 0 is a 404 by
 * design and *has* to stay one — the pitch's answer to "no team" is drawn
 * here instead, from the same plain shirt the backend serves when the CDN is
 * down. The two failures the reader can hit — no team code, and a request
 * that fails on the wire — therefore land on the same picture rather than on
 * a gap where a shirt should be.
 */

export type PlayerCardSize = 'pitch' | 'chip'

export interface PlayerCardProps {
  code: number
  name: string
  position: string
  teamShort: string | null
  teamCode: number | null
  /** `null` where the surface genuinely has no expected-points number for
   *  this player — Live once his match is over, a review miss, a rival's
   *  squad list. `fmtNum` prints an em dash for it (plan A3). */
  ep: number | null
  fixture?: NextFixture | null
  /** `'C'`, `'V'`, or nothing. The plan's armbands, not a judgement. */
  armband?: 'C' | 'V' | null
  /** The multiplier the chip implies, when the payload already names one.
   *  Nothing new is plumbed for this (spec D3) — it is drawn if it arrives. */
  multiplier?: number | null
  news?: string
  chanceOfPlaying?: number | null
  size?: PlayerCardSize
  /** Where this player puts you against the field, or null.
   *
   * `shield` (owned and heavily owned), `sword` (owned and rare), `threat`
   * (the field owns him and you do not) — `routers/players.py:105`'s
   * vocabulary, which is imported rather than restated on both sides of the
   * wire. Null and absent are the same thing and both mean "no claim", which
   * is the third of the game the classifier deliberately says nothing about.
   */
  fieldClass?: 'shield' | 'sword' | 'threat' | null
  /** v14: the EO lens. Field effective ownership, 0–100, when the lens is
   *  on; the tile background is tinted by it (rule 7 as a tint, not a bar).
   *  Null or absent draws no tint. `fieldClass` then only names the class in
   *  the title — never a colour, because a colour would be a verdict. */
  lensEo?: number | null
  onSelect?: (code: number) => void
}

/** The bundled plain shirt, inline.
 *
 *  The same drawing `src/gaffer/assets/shirt_fallback.svg` serves, carried as
 *  a data URI so that it needs no request of its own: the states it stands in
 *  for are "no team" and "that request failed", and neither is improved by
 *  depending on another fetch. Mid-grey on a transparent ground, legible on
 *  the green pitch and on a card in either theme. */
export const PLAIN_SHIRT
  = 'data:image/svg+xml;utf8,'
  + encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 66 66" width="66"'
    + ' height="66" role="img" aria-label="shirt unavailable">'
    + '<path d="M23 8 L13 13 L8 27 L17 30 L17 58 L49 58 L49 30 L58 27 L53 13'
    + ' L43 8 L38 14 Q33 18 28 14 Z" fill="#8d939c" stroke="#6b7178"'
    + ' stroke-width="1.5" stroke-linejoin="round"/></svg>',
  )

/** Where this player's shirt comes from.
 *
 *  A null `teamCode` never reaches the API: the endpoint allowlists the
 *  banked bootstrap, shirt 0 is a deliberate 404, and asking anyway would
 *  spend a request to be told what we already know. The keeper's kit is a
 *  different file at the same team code. */
function shirtSrc(teamCode: number | null, position: string): string {
  if (teamCode === null || teamCode === undefined) return PLAIN_SHIRT
  return position === 'GKP'
    ? `/api/assets/shirt/${teamCode}?keeper=true`
    : `/api/assets/shirt/${teamCode}`
}

/** Day and time in the reader's own zone.
 *
 *  The server sends UTC and refuses to guess a timezone, which is correct;
 *  this is the only place that knows one. An unparseable stamp reads as TBC
 *  rather than as `Invalid Date`. */
function kickoffLabel(iso: string | null): string {
  if (!iso) return 'TBC'
  const when = new Date(iso)
  if (Number.isNaN(when.getTime())) return 'TBC'
  return when.toLocaleString(undefined, {
    weekday: 'short', hour: '2-digit', minute: '2-digit',
  })
}

/** The lens tint: more owned, more of the text colour mixed into the base.
 *  A token mix rather than a hex so it is right in both themes. */
export function lensBackground(eo: number): string {
  const pct = Math.round(Math.min(Math.max(eo, 0), 100) * 0.28)
  return `color-mix(in srgb, var(--color-text) ${pct}%, var(--color-base))`
}

function FixtureChip({ fixture }: { fixture: NextFixture | null }) {
  // A blank gameweek is a word, not an empty box: the reader has to be able
  // to tell "he does not play" from "we failed to load his fixture".
  if (!fixture) {
    return (
      <span data-testid="fixture-chip" data-tone="neutral"
            className="mt-1 inline-flex rounded-chip border border-border
                       px-1.5 text-[10px] leading-4 text-text-muted">
        Blank
      </span>
    )
  }
  const side = fixture.home ? 'H' : 'A'
  const tone = difficultyTone(fixture.difficulty)
  const rating = fixture.difficulty === null
    ? 'No difficulty rating available for this fixture'
    : `Fixture difficulty ${fixture.difficulty.toFixed(2)} — the ticker's `
      + 'odds-implied rating, not FPL\'s FDR'
  // The kickoff moved into the title (plan R3): the tile is not where a
  // captain is chosen, and the mockup's tile carries none. The wrapper
  // holds the test id, the tone and the title because `Chip` is a closed
  // primitive that takes no arbitrary attributes; it draws the tint.
  return (
    <span data-testid="fixture-chip" data-tone={tone} className="mt-1"
          title={`${kickoffLabel(fixture.kickoff_utc)} · ${rating}`}>
      <Chip tone={tone}>
        {`${fixture.opponent_short ?? '???'} (${side})`}
      </Chip>
    </span>
  )
}

export default function PlayerCard({
  code, name, position, teamShort, teamCode, ep, fixture = null,
  armband = null, multiplier = null, news = '', chanceOfPlaying = null,
  size = 'pitch', fieldClass = null, lensEo = null, onSelect,
}: PlayerCardProps) {
  const pitch = size === 'pitch'
  const shirtPx = pitch ? 26 : 20

  const shirt = (
    <img
      src={shirtSrc(teamCode, position)}
      alt={teamShort ? `${teamShort} shirt` : 'shirt'}
      width={shirtPx}
      height={shirtPx}
      // A request that fails on the wire falls back to the same plain shirt
      // a missing team code gets. The guard stops the swap retriggering if
      // the data URI itself somehow fails.
      onError={(e) => {
        if (e.currentTarget.getAttribute('src') !== PLAIN_SHIRT) {
          e.currentTarget.setAttribute('src', PLAIN_SHIRT)
        }
      }}
      className={pitch ? 'mx-auto mb-1 block' : 'block shrink-0'}
    />
  )

  // C: a white square tag after the name; V: the same tag in grey (spec §5).
  const tag = armband && (
    <span
      title={armband === 'C' ? 'Captain' : 'Vice-captain'}
      className="ml-1 inline-flex h-3 min-w-3 shrink-0 items-center
                 justify-center rounded-chip px-0.5 text-[9px] font-bold
                 leading-none"
      style={{
        background: armband === 'C' ? 'var(--color-text)'
                                    : 'var(--color-text-muted)',
        color: 'var(--color-base)',
      }}
    >
      {armband}
    </span>
  )

  const nameLine = (
    <span className={'flex min-w-0 items-center text-[11.5px] font-semibold '
      + `text-text ${pitch ? 'justify-center' : ''}`}>
      <span className="truncate">{name}</span>
      {tag}
      {news && (
        <Chip tone="warn" title={news} className="ml-1">
          {chanceOfPlaying === null ? 'News' : `${chanceOfPlaying}%`}
        </Chip>
      )}
    </span>
  )

  const metaLine = (
    <span className={'tn flex items-center gap-1 text-[10.5px] text-text-muted '
      + (pitch ? 'justify-center' : '')}>
      {teamShort && <span>{teamShort}</span>}
      {teamShort && <span aria-hidden>·</span>}
      <span>{fmtNum(ep)}</span>
      {/* Drawn only when the payload already named a chip (D3). */}
      {multiplier !== null && multiplier > 1 && (
        <span className="text-up">{`×${multiplier}`}</span>
      )}
    </span>
  )

  const body = pitch
    ? <>{shirt}{nameLine}{metaLine}<FixtureChip fixture={fixture} /></>
    : (
      <>
        {shirt}
        <span className="flex min-w-0 flex-col">{nameLine}{metaLine}</span>
      </>
      )

  const className = pitch
    ? 'flex w-[92px] flex-col items-center rounded-ctl border border-border '
      + 'bg-base px-1.5 py-1.5 text-center'
    // No fixed width: a chip sits in a table cell, a list row and a wrapping
    // strip, and each of those knows its own width better than the card does.
    : 'inline-flex max-w-full items-center gap-1.5 rounded-ctl border '
      + 'border-border bg-base px-1.5 py-1 text-left'

  // `undefined` rather than an empty object so an untinted card carries no
  // inline style at all.
  const style = lensEo !== null && lensEo !== undefined
    ? { backgroundColor: lensBackground(lensEo) }
    : undefined
  const title = lensEo !== null && lensEo !== undefined
    ? `field EO ${fmtNum(lensEo, 1)}%${fieldClass ? ` · ${fieldClass}` : ''}`
    : undefined

  // A div unless something is listening: a button nothing responds to is a
  // focus stop that lies about being interactive.
  return onSelect
    ? (
      <button type="button" data-code={code} className={className}
              style={style} title={title} onClick={() => onSelect(code)}>
        {body}
      </button>
      )
    : (
      <div data-code={code} className={className} style={style} title={title}>
        {body}
      </div>
      )
}

import { PlayerCard } from '../../kit'
import type { SquadRow } from './SquadTable'

/**
 * The XI on a pitch and the bench underneath it, the way FPL draws its own.
 *
 * Four formation rows read off the XI's positions rather than a formation
 * string, because the solver does not emit one and inferring "3-5-2" from
 * eleven positions only to expand it back into rows would be a round trip
 * through a number nobody needs. A line nobody is playing is omitted rather
 * than drawn empty, and a player the artifact gave no position lands in one
 * unstructured row at the bottom — losing him off the pitch entirely would be
 * worse than an ugly extra row, and advice written before v3.1 has no
 * positions at all.
 *
 * The bench is a labelled row on the page surface under the turf, in the
 * order the payload lists it (GK first, then outfield in bench order),
 * because that order is the substitution priority and re-sorting it would
 * destroy the only information the sequence carries.
 *
 * Every card is `kit/PlayerCard`; nothing about a player is drawn here.
 */

const LINES = ['GKP', 'DEF', 'MID', 'FWD'] as const

export interface SquadPitchProps {
  xi: SquadRow[]
  bench: SquadRow[]
  captain: number
  vice: number
  /** v10b §F1c: the EO lens. The *pitch* decides whether the lens is on, not
   *  the card — the card only knows how to draw a class it is handed. Off by
   *  default, and no new prop for the rows themselves: the pitch and the
   *  table render from the same SquadRow objects. */
  lens?: boolean
  onSelect?: (code: number) => void
}

function armbandFor(code: number, captain: number,
                    vice: number): 'C' | 'V' | null {
  if (code === captain) return 'C'
  if (code === vice) return 'V'
  return null
}

export default function SquadPitch(
  { xi, bench, captain, vice, lens = false, onSelect }: SquadPitchProps,
) {
  const loose = xi.filter((p) => !LINES.includes(p.position as never))
  const rows: Array<[string, SquadRow[]]> = [
    ...LINES.map((line) =>
      [line, xi.filter((p) => p.position === line)] as [string, SquadRow[]]),
    ['OTHER', loose] as [string, SquadRow[]],
  ].filter(([, players]) => players.length > 0)

  const card = (player: SquadRow) => (
    <PlayerCard
      key={player.code}
      code={player.code}
      name={player.name}
      position={player.position}
      teamShort={player.teamShort}
      teamCode={player.teamCode}
      ep={player.ep}
      fixture={player.nextFixture}
      armband={armbandFor(player.code, captain, vice)}
      news={player.news}
      chanceOfPlaying={player.chanceOfPlaying}
      lensEo={lens ? player.fieldEo ?? null : null}
      fieldClass={player.fieldClass ?? null}
      onSelect={onSelect}
    />
  )

  return (
    <div>
      <div
        data-testid="turf"
        className="relative flex flex-col justify-between gap-3 rounded-ctl
                   bg-turf px-2 py-4"
      >
        {/* Hairline markings: an inner rectangle and the halfway line, in
            the turf-line token — no texture, no gradient (spec §5). */}
        <div aria-hidden data-turf-line
             className="pointer-events-none absolute inset-2 rounded-chip
                        border border-turf-line" />
        <div aria-hidden data-turf-line
             className="pointer-events-none absolute inset-x-2 top-1/2
                        border-t border-turf-line" />
        {rows.map(([line, players]) => (
          <div key={line} data-testid={`pitch-row-${line}`}
               className="relative flex flex-wrap justify-center gap-2">
            {players.map(card)}
          </div>
        ))}
      </div>
      {bench.length > 0 && (
        <div data-testid="bench-strip" className="mt-3">
          <p className="label mb-1.5">Bench · in order</p>
          <div className="flex flex-wrap gap-2">
            {bench.map(card)}
          </div>
        </div>
      )}
    </div>
  )
}

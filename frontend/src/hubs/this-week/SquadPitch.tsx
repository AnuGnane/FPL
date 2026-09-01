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
 * The bench is a strip below the grass in the order the payload lists it
 * (GK first, then outfield in bench order), because that order is the
 * substitution priority and re-sorting it would destroy the only information
 * the sequence carries.
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
      fieldClass={lens ? player.fieldClass ?? null : null}
      onSelect={onSelect}
    />
  )

  return (
    <div>
      <div
        className="flex flex-col justify-between gap-3 rounded-card px-2 py-3"
        // The grass. A gradient rather than a flat green so the four bands
        // read as depth, and a token-free literal because this is the one
        // surface on the page that is not part of the palette — a pitch is
        // green in both themes.
        style={{
          background:
            'linear-gradient(to bottom, #1f6b3a 0%, #2a8049 55%, #1f6b3a 100%)',
        }}
      >
        {rows.map(([line, players]) => (
          <div key={line} data-testid={`pitch-row-${line}`}
               className="flex flex-wrap justify-center gap-1.5">
            {players.map(card)}
          </div>
        ))}
      </div>
      {bench.length > 0 && (
        <div data-testid="bench-strip"
             className="mt-2 rounded-card border border-border bg-surface
                        px-2 py-2">
          <p className="label mb-1">Bench</p>
          <div className="flex flex-wrap justify-center gap-1.5">
            {bench.map(card)}
          </div>
        </div>
      )}
    </div>
  )
}

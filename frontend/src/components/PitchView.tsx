import type { PlayerRef } from '../types'
import PlayerName from './PlayerName'

const ROWS = ['GKP', 'DEF', 'MID', 'FWD']

export default function PitchView(
  { xi, captain, vice }: { xi: PlayerRef[]; captain: number; vice: number },
) {
  // Advice written before v3.1 has no `position`, and a pitch that filters
  // every line to empty renders as nothing at all. Anything the lines cannot
  // claim goes into one unstructured row underneath them.
  const loose = xi.filter((p) => !p.position || !ROWS.includes(p.position))
  const lines = ROWS.map((row) => xi.filter((p) => p.position === row))
    .concat([loose])
    .filter((line) => line.length > 0)
  return (
    <div className="pitch">
      {lines.map((line) => (
        <div className="pitch-row" key={line[0].code}>
          {line.map((player) => (
            <div className="pitch-player" key={player.code}>
              <PlayerName code={player.code} name={player.name} />
              {player.code === captain && <span title="Captain">C</span>}
              {player.code === vice && <span title="Vice-captain">V</span>}
              <span className="muted">{player.ep}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

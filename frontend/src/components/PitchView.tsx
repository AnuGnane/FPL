import type { PlayerRef } from '../types'
import PlayerName from './PlayerName'

const ROWS = ['GKP', 'DEF', 'MID', 'FWD']

export default function PitchView(
  { xi, captain, vice }: { xi: PlayerRef[]; captain: number; vice: number },
) {
  return (
    <div className="pitch">
      {ROWS.map((row) => {
        const line = xi.filter((player) => player.position === row)
        if (line.length === 0) return null
        return (
          <div className="pitch-row" key={row}>
            {line.map((player) => (
              <div className="pitch-player" key={player.code}>
                <PlayerName code={player.code} name={player.name} />
                {player.code === captain && <span title="Captain">C</span>}
                {player.code === vice && <span title="Vice-captain">V</span>}
                <span className="muted">{player.ep}</span>
              </div>
            ))}
          </div>
        )
      })}
    </div>
  )
}

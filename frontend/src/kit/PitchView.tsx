import { fmtNum } from './format'
import { posColor } from './PosBadge'

export interface PitchPlayer {
  code: number
  name: string
  position: string
  ep: number
}

const LINES = ['GKP', 'DEF', 'MID', 'FWD']

export interface PitchViewProps {
  xi: PitchPlayer[]
  captain: number
  vice: number
  onSelect?: (code: number) => void
}

export default function PitchView(
  { xi, captain, vice, onSelect }: PitchViewProps,
) {
  // Advice written before v3.1 has no `position`; anything the lines cannot
  // claim goes into one unstructured row underneath them rather than vanishing.
  const loose = xi.filter((p) => !p.position || !LINES.includes(p.position))
  const rows: Array<[string, PitchPlayer[]]> = [
    ...LINES.map((line) =>
      [line, xi.filter((p) => p.position === line)] as [string, PitchPlayer[]]),
    ['OTHER', loose] as [string, PitchPlayer[]],
  ].filter(([, players]) => players.length > 0)

  return (
    <div className="relative flex w-full flex-col gap-3 rounded-ctl bg-turf
                    px-2 py-4">
      {rows.map(([line, players]) => (
        <div key={line} data-testid={`pitch-row-${line}`}
             className="flex flex-wrap justify-center gap-2">
          {players.map((player) => (
            <button
              key={player.code}
              type="button"
              onClick={() => onSelect?.(player.code)}
              data-position={player.position || undefined}
              className="flex w-[92px] flex-col items-center rounded-ctl
                         border bg-base px-1.5 py-1.5"
              // Identity, not judgement: the ring says which line he is on.
              // A player the artifact gave no position keeps the plain border.
              style={{
                borderColor: posColor(player.position)
                  ?? 'var(--color-border)',
              }}
            >
              <span className="flex items-center gap-1 text-text">
                {player.name}
                {player.code === captain && (
                  <span
                    title="Captain"
                    className="rounded-chip px-0.5 text-[9px] font-bold
                               leading-none"
                    style={{ background: 'var(--color-text)',
                             color: 'var(--color-base)' }}
                  >C</span>
                )}
                {player.code === vice && (
                  <span
                    title="Vice-captain"
                    className="rounded-chip px-0.5 text-[9px] font-bold
                               leading-none"
                    style={{ background: 'var(--color-text-muted)',
                             color: 'var(--color-base)' }}
                  >V</span>
                )}
              </span>
              <span className="tn text-[10.5px] text-text-muted">
                {fmtNum(player.ep)}
              </span>
            </button>
          ))}
        </div>
      ))}
    </div>
  )
}

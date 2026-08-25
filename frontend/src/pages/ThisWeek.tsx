import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import { useJob } from '../api/useJob'
import Countdown from '../components/Countdown'
import PitchView from '../components/PitchView'
import PlayerName from '../components/PlayerName'
import StalenessBanner from '../components/StalenessBanner'
import type { AdviceLatest, ChipPlanRow } from '../types'

export default function ThisWeek() {
  const [data, setData] = useState<AdviceLatest | null>(null)
  const [chips, setChips] = useState<ChipPlanRow[] | null>(null)
  const [chipsError, setChipsError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const job = useJob()

  const load = () => {
    apiGet<AdviceLatest>('/api/advice/latest').then(setData)
      .catch((e: Error) => setError(e.message))
    // The chip plan runs a MILP per chip per gameweek, so it can take a while
    // and it can fail on its own. It loads beside the advice, never in front
    // of it: the rest of the page renders while this card is still thinking.
    setChips(null)
    setChipsError(null)
    apiGet<{ chips: ChipPlanRow[] }>('/api/chips/plan')
      .then((body) => setChips(body.chips))
      .catch((e: Error) => setChipsError(e.message))
  }

  useEffect(load, [])
  useEffect(() => { if (job.status === 'done') load() }, [job.status])

  if (error) return <p className="bad">{error}</p>
  if (!data) return <p className="muted">Loading…</p>

  const advice = data.advice
  return (
    <>
      <h2>
        GW{data.gw} · {advice.expected_pts} xPts ·{' '}
        <Countdown deadline={data.deadline} />
      </h2>
      <StalenessBanner
        staleness={data.staleness}
        onRerun={() => job.start('/api/advice/rerun')}
        busy={job.status === 'queued' || job.status === 'running'}
      />
      {job.status === 'error' && <p className="bad">{job.error}</p>}
      {advice.strategy && (
        <div className="card">
          <h2>League context</h2>
          <p>
            {advice.strategy.stance === 'chase'
              ? `${advice.strategy.gap} points behind `
                + `${advice.strategy.rival_name} with `
                + `${advice.strategy.weeks_left} gameweeks left — chasing, so `
                + 'the plan leans to differentials.'
              : advice.strategy.stance === 'defend'
                ? `${advice.strategy.gap} points ahead of `
                  + `${advice.strategy.rival_name} — defending, so the plan `
                  + 'mirrors rival ownership.'
                : 'The gap is inside the noise — plain points-max plan.'}
          </p>
        </div>
      )}
      <div className="card">
        <h2>Starting XI</h2>
        <PitchView
          xi={advice.xi}
          captain={advice.captain.code}
          vice={advice.vice.code}
        />
        <h3>Bench</h3>
        <div className="bench-strip">
          {advice.bench.map((player) => (
            <span key={player.code}>
              <PlayerName code={player.code} name={player.name} />{' '}
              <span className="muted">{player.ep}</span>
            </span>
          ))}
        </div>
      </div>
      <div className="card">
        <h2>Transfers</h2>
        {advice.scenarios && (
          <p className="muted">
            {advice.scenarios.completed}/{advice.scenarios.n} scenarios solved
            (seed {advice.scenarios.seed}) — the single-solve optimum{' '}
            {advice.raw_optimum_agrees ? 'agreed' : 'differed'}.
          </p>
        )}
        {advice.buys.length === 0 && advice.sells.length === 0 && (
          <p className="muted">No transfers — bank the free transfer.</p>
        )}
        <table>
          {advice.scenarios && (
            <thead>
              <tr>
                <th />
                <th>Player</th>
                <th>xPts</th>
                <th>% of sims</th>
                <th />
              </tr>
            </thead>
          )}
          <tbody>
            {advice.buys.map((player) => (
              <tr key={`in-${player.code}`}>
                <td>IN</td>
                <td><PlayerName code={player.code} name={player.name} /></td>
                <td>{player.ep}</td>
                {advice.scenarios && (
                  <td>
                    {player.frequency === undefined
                      ? '—'
                      : `${Math.round(player.frequency * 100)}%`}
                  </td>
                )}
                <td>
                  {player.tag && (
                    <span className={`tag tag-${player.tag}`}>{player.tag}</span>
                  )}
                </td>
              </tr>
            ))}
            {advice.sells.map((player) => (
              <tr key={`out-${player.code}`}>
                <td>OUT</td>
                <td><PlayerName code={player.code} name={player.name} /></td>
                <td>{player.ep}</td>
                {advice.scenarios && (
                  <td>
                    {player.frequency === undefined
                      ? '—'
                      : `${Math.round(player.frequency * 100)}%`}
                  </td>
                )}
                <td />
              </tr>
            ))}
          </tbody>
        </table>
        {advice.hits > 0 && (
          <p className="bad">{advice.hits} hit(s): -{advice.hits * 4} pts</p>
        )}
      </div>
      <div className="card">
        <h2>Chips</h2>
        {chipsError && (
          <p className="muted">
            Could not work out the chip weeks — {chipsError}
          </p>
        )}
        {!chipsError && chips === null && (
          <p className="muted">Working out the best chip weeks…</p>
        )}
        {chips !== null && chips.length === 0 && (
          <p className="muted">No chips available.</p>
        )}
        <ul>
          {(chips ?? []).map((chip) => (
            <li key={chip.chip}>
              {/* "best week" on its own reads as best week of the season; it
                  is only ever the best of the horizon that was scored. And a
                  wildcard's total counts every week it covers, so its weeks
                  are comparable only per week. */}
              {chip.chip}: GW{chip.best_gw} — best of the next{' '}
              {chip.weeks_scored} GW{chip.weeks_scored === 1 ? '' : 's'}{' '}
              (+{chip.best_gain}
              {chip.best_gain_per_week !== chip.best_gain
                && `, +${chip.best_gain_per_week}/wk`})
              {chip.play_now_delta !== null && chip.play_now_delta < 0
                && ` — playing now costs ${Math.abs(chip.play_now_delta)}`}
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}

import { useGetCallsPerDayQuery } from '../../api/api'
import LineChart from '../charts/LineChart'

const WEEKDAY_NAMES = {
    Mon: 'Monday',
    Tue: 'Tuesday',
    Wed: 'Wednesday',
    Thu: 'Thursday',
    Fri: 'Friday',
    Sat: 'Saturday',
    Sun: 'Sunday',
}

/** Long date for the tooltip, from the server's local ISO date (no timezone shift). */
const longDate = (iso, weekday) => {
    const [y, m, d] = iso.split('-').map(Number)
    const date = new Date(y, m - 1, d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    return `${WEEKDAY_NAMES[weekday] ?? weekday}, ${date}`
}

/** Number of calls made by the user's agent on each of the last seven days, by day of the week. */
export default function CallsGraph({ uid }) {
    const { data, isError } = useGetCallsPerDayQuery(uid)
    const days = data?.days ?? []
    const total = days.reduce((a, d) => a + d.calls, 0)
    return (
        <section className="graph-box" aria-labelledby="calls-graph-title">
            <div className="graph-bar">
                <h2 id="calls-graph-title" className="graph-title">
                    Calls made by your agent
                </h2>
                {data && (
                    <span className="muted">
                        Last 7 days · {total} {total === 1 ? 'call' : 'calls'}
                    </span>
                )}
            </div>
            <div className="graph-body">
                {isError && (
                    <p role="alert" className="muted">
                        Could not load the call data.
                    </p>
                )}
                {data && (
                    <LineChart
                        labels={days.map((d) => d.weekday)}
                        tooltipTitles={days.map((d) => longDate(d.date, d.weekday))}
                        series={[
                            {
                                id: 'calls',
                                name: 'Calls per day',
                                color: 'var(--chart-1)',
                                points: days.map((d) => d.calls),
                            },
                        ]}
                        integer
                        minMax={4}
                        highlightIndex={days.length - 1}
                        formatValue={(v) => `${v} ${v === 1 ? 'call' : 'calls'}`}
                        xTitle="Day of the week"
                        yTitle="Number of calls"
                        ariaLabel={`Number of calls made by your agent per day, last 7 days: ${days
                            .map((d) => `${d.weekday} ${d.calls}`)
                            .join(', ')}`}
                    />
                )}
                {!data && !isError && <p className="muted">Loading…</p>}
            </div>
        </section>
    )
}

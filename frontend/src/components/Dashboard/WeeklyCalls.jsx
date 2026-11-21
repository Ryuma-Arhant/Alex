const WEEKDAY_NAMES = {
    Mon: 'Monday',
    Tue: 'Tuesday',
    Wed: 'Wednesday',
    Thu: 'Thursday',
    Fri: 'Friday',
    Sat: 'Saturday',
    Sun: 'Sunday',
}
// Chart geometry (SVG user units): bars sit on BASE and grow up to TOP; gridlines every 40 units.
const BASE = 200
const TOP = 32
const GRID = [40, 80, 120, 160, 200]
const SLOT = 74
const BAR = 40

/** Calls made by the user's agent on each of the last seven days (oldest first, today last and highlighted). */
export default function WeeklyCalls({ days }) {
    const total = days.reduce((a, d) => a + d.calls, 0)
    const max = Math.max(...days.map((d) => d.calls), 0)
    const busiest = max > 0 ? days.find((d) => d.calls === max) : null
    const h = (v) => (max > 0 ? Math.round(((BASE - TOP) * v) / max) : 0)
    return (
        <section className="dash-card" aria-labelledby="weekly-calls-title">
            <div className="dash-card-head">
                <h2 id="weekly-calls-title">Calls in the last 7 days</h2>
                <p className="muted">
                    {total} {total === 1 ? 'call' : 'calls'}
                    {busiest ? ` · busiest on ${WEEKDAY_NAMES[busiest.weekday] ?? busiest.weekday}` : ''}
                </p>
            </div>
            <svg
                className="dash-bars"
                viewBox="0 0 580 232"
                width="100%"
                role="img"
                aria-label={`Calls per day, last 7 days: ${days.map((d) => `${d.weekday} ${d.calls}`).join(', ')}`}
            >
                {GRID.map((y) => (
                    <line key={y} x1="30" x2="560" y1={y} y2={y} className="dash-grid" />
                ))}
                {days.map((d, i) => {
                    const x = 40 + i * SLOT
                    const height = h(d.calls)
                    const today = i === days.length - 1
                    return (
                        <g key={d.date}>
                            {height > 0 && (
                                <rect
                                    x={x}
                                    y={BASE - height}
                                    width={BAR}
                                    height={height}
                                    rx={Math.min(8, height / 2)}
                                    className={`dash-bar ${today ? 'today' : ''}`}
                                />
                            )}
                            <text x={x + BAR / 2} y="222" textAnchor="middle" className="dash-axis">
                                {d.weekday}
                            </text>
                            <text
                                x={x + BAR / 2}
                                y={BASE - height - 8}
                                textAnchor="middle"
                                className="dash-value"
                            >
                                {d.calls}
                            </text>
                        </g>
                    )
                })}
            </svg>
        </section>
    )
}

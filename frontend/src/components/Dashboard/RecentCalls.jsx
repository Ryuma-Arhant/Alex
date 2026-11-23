import { NOT_CONNECTED } from '../../lib/callOutcome'
import Pill from './Pill'

// call_outcome values the summariser uses (contracts/summary_prompt.txt) -> what the table shows.
const OUTCOMES = {
    completed: { label: 'Completed', tone: 'teal', icon: 'check' },
    no_resolution: { label: 'No resolution', tone: 'blue', icon: 'clock' },
    escalated: { label: 'Escalate', tone: 'red', icon: 'warn' },
    caller_hung_up: { label: 'Hung up', tone: 'neutral' },
    abandoned: { label: 'No answer', tone: 'neutral' },
    failed: { label: 'Failed', tone: 'neutral' },
}

/** What the Outcome column shows for one call. A promise to pay, or a need for a person, says more than the
 * generic outcome, so they come first. */
export function outcomeOf(call) {
    if (call.status === 'live') return { label: 'Live', tone: 'teal' }
    if (NOT_CONNECTED[call.end_reason]) {
        const tone =
            call.end_reason === 'busy' ? 'amber' : call.end_reason === 'invalid_number' ? 'red' : 'neutral'
        return { label: NOT_CONNECTED[call.end_reason], tone }
    }
    if (call.status === 'summarising') return { label: 'Summarising…', tone: 'neutral' }
    if (call.promise_to_pay) return { label: 'Promise to pay', tone: 'teal', icon: 'check' }
    if (call.escalation_needed) return OUTCOMES.escalated
    return (
        OUTCOMES[call.outcome] ?? {
            label: call.outcome ? call.outcome.replace(/_/g, ' ') : 'No summary',
            tone: 'neutral',
        }
    )
}

const sameDay = (a, b) => a.toDateString() === b.toDateString()

/** "11:42" today; "18 Nov, 11:42" on other days. */
export function callTime(iso, now = new Date()) {
    const d = new Date(iso)
    const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    return sameDay(d, now)
        ? time
        : `${d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}, ${time}`
}

/** "₹12,000" for whole amounts, "₹12,000.50" otherwise, in the loan's currency. */
export function shortAmount(amount, currency) {
    const n = Number(amount)
    try {
        return new Intl.NumberFormat(undefined, {
            style: 'currency',
            currency: currency || 'INR',
            maximumFractionDigits: Number.isInteger(n) ? 0 : 2,
        }).format(n)
    } catch {
        return `${amount} ${currency ?? ''}`.trim()
    }
}

const length = (s) => (s == null ? '—' : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`)
const mood = (s) => (!s || s.toLowerCase() === 'unknown' ? '—' : s.charAt(0).toUpperCase() + s.slice(1))

/** The agent's five most recent calls. */
export default function RecentCalls({ calls }) {
    return (
        <section className="dash-card" aria-labelledby="recent-calls-title">
            <div className="dash-card-head row">
                <h2 id="recent-calls-title">Recent calls</h2>
                <span className="dash-soon-link" aria-disabled="true">
                    View all <span className="nav-badge">Soon</span>
                </span>
            </div>
            {calls.length === 0 ? (
                <p className="muted">No calls yet. Start one from “Start a call”.</p>
            ) : (
                <div className="dash-table-wrap">
                    <table className="dash-table">
                        <thead>
                            <tr>
                                <th scope="col">Time</th>
                                <th scope="col">Borrower</th>
                                <th scope="col" className="num">
                                    Pending
                                </th>
                                <th scope="col">Outcome</th>
                                <th scope="col">Mood</th>
                                <th scope="col" className="num">
                                    Length
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {calls.map((c) => {
                                const o = outcomeOf(c)
                                return (
                                    <tr key={c.call_id}>
                                        <td>{callTime(c.at)}</td>
                                        <td>
                                            {c.phone_last4 ? (
                                                <span
                                                    className="mono"
                                                    aria-label={`Phone ending ${c.phone_last4}`}
                                                >
                                                    •••• {c.phone_last4}
                                                </span>
                                            ) : (
                                                '—'
                                            )}
                                        </td>
                                        <td className="num">
                                            {c.amount ? shortAmount(c.amount, c.currency) : '—'}
                                        </td>
                                        <td>
                                            <Pill tone={o.tone} icon={o.icon}>
                                                {o.label}
                                            </Pill>
                                        </td>
                                        <td>{mood(c.sentiment)}</td>
                                        <td className="num">
                                            {c.status === 'live' ? '—' : length(c.length_seconds)}
                                        </td>
                                    </tr>
                                )
                            })}
                        </tbody>
                    </table>
                </div>
            )}
        </section>
    )
}

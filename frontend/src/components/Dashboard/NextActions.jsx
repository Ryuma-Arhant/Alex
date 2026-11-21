import { useState } from 'react'
import { errorMessage, useSetNextActionDoneMutation } from '../../api/api'

const AGENT_OWNERS = new Set(['agent', 'assistant', 'ai', 'ai agent', 'voice agent'])
const BORROWER_OWNERS = new Set(['caller', 'borrower', 'customer', 'user', 'client'])

/** Who does it: the summary's owner ("agent", "caller", ...) in the words the user knows. */
export function ownerLabel(owner, agentName) {
    const o = (owner || '').trim().toLowerCase()
    if (AGENT_OWNERS.has(o)) return agentName || 'Your agent'
    if (BORROWER_OWNERS.has(o)) return 'Borrower'
    return owner ? owner.charAt(0).toUpperCase() + owner.slice(1) : ''
}

/** Next actions from today's call summaries; ticking one off is saved for the user. */
export default function NextActions({ uid, actions, agentName }) {
    const [setDone] = useSetNextActionDoneMutation()
    const [error, setError] = useState(null)
    const toggle = async (a, done) => {
        setError(null)
        try {
            await setDone({ uid, callId: a.call_id, index: a.index, done }).unwrap()
        } catch (err) {
            setError(errorMessage(err, 'Could not save that. Please try again.'))
        }
    }
    return (
        <section className="dash-card" aria-labelledby="next-actions-title">
            <div className="dash-card-head">
                <h2 id="next-actions-title">Next actions</h2>
                <p className="muted">From today's call summaries</p>
            </div>
            {error && (
                <div className="banner error" role="alert">
                    {error}
                </div>
            )}
            {actions.length === 0 ? (
                <p className="muted">No next actions from today's calls yet.</p>
            ) : (
                <ul className="dash-actions">
                    {actions.map((a) => {
                        const meta = [ownerLabel(a.owner, agentName), a.done ? 'done' : a.due].filter(Boolean)
                        return (
                            <li key={`${a.call_id}-${a.index}`}>
                                <input
                                    type="checkbox"
                                    checked={a.done}
                                    onChange={(e) => void toggle(a, e.target.checked)}
                                    aria-label={a.action}
                                />
                                <div>
                                    <span className={a.done ? 'done' : ''}>{a.action}</span>
                                    {meta.length > 0 && (
                                        <span className="muted small">{meta.join(' · ')}</span>
                                    )}
                                </div>
                            </li>
                        )
                    })}
                </ul>
            )}
        </section>
    )
}

import { useEffect, useState } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router-dom'
import { useGetAgentQuery, useGetCallsPerDayQuery, useGetDashboardQuery } from '../api/api'
import { useAppSelector } from '../app/hooks'
import { IndividualCallModal } from '../components/CallAgent/CallAgent'
import { LIVE } from '../components/CallControls/CallControls'
import NextActions from '../components/Dashboard/NextActions'
import Pill from '../components/Dashboard/Pill'
import RecentCalls from '../components/Dashboard/RecentCalls'
import WeeklyCalls from '../components/Dashboard/WeeklyCalls'
import { Orb } from '../components/Navbar/Navbar'

const POLL_MS = 15_000 // keeps today's figures and the recent calls current while the page is open
export const REPLY_TARGET_S = 2 // the "Avg reply time" card compares against this

export function greeting(hour) {
    if (hour < 12) return 'Good morning'
    if (hour < 17) return 'Good afternoon'
    return 'Good evening'
}

const initials = (name) =>
    name
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((w) => w[0].toUpperCase())
        .join('') || '?'

const clock = (ms) => {
    const s = Math.max(0, Math.floor(ms / 1000))
    const m = Math.floor(s / 60)
    return m >= 60
        ? `${Math.floor(m / 60)}:${String(m % 60).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
        : `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

/** "Live · 02:14 · Return to call", only while a call is running in this tab. */
function LivePill({ uid }) {
    const { status, connectedAt } = useAppSelector((s) => s.call)
    const live = LIVE.includes(status)
    const [now, setNow] = useState(() => Date.now())
    useEffect(() => {
        if (!live) return undefined
        const t = setInterval(() => setNow(Date.now()), 1000)
        return () => clearInterval(t)
    }, [live])
    if (!live) return null
    return (
        <Link to={`/call/${uid}`} className="dash-live">
            <Orb size={28} />
            <span className="strong">
                {connectedAt ? `Live · ${clock(now - connectedAt)}` : 'Connecting…'}
            </span>
            <span className="muted">Return to call</span>
        </Link>
    )
}

function Stat({ label, value, children }) {
    return (
        <section className="dash-card dash-stat" aria-label={label}>
            <span className="muted">{label}</span>
            <span className="dash-stat-value">{value}</span>
            {children}
        </section>
    )
}

function Stats({ dash, days }) {
    const today = days.at(-1)?.calls ?? dash.calls_today
    const diff = days.length >= 2 ? today - days.at(-2).calls : null
    const { promised, of } = dash.promises
    const reply = dash.reply_seconds
    return (
        <div className="dash-stats">
            <Stat label="Calls today" value={today}>
                {diff === null ? null : diff > 0 ? (
                    <Pill tone="teal">+{diff} vs yesterday</Pill>
                ) : diff < 0 ? (
                    <Pill>−{-diff} vs yesterday</Pill>
                ) : (
                    <Pill>Same as yesterday</Pill>
                )}
            </Stat>
            <Stat label="Promise-to-pay rate" value={of > 0 ? `${Math.round((100 * promised) / of)}%` : '—'}>
                {of > 0 ? (
                    <Pill tone="teal">
                        {promised} of {of} {of === 1 ? 'call' : 'calls'}
                    </Pill>
                ) : (
                    <Pill>No summarised calls today</Pill>
                )}
            </Stat>
            <Stat label="Avg reply time" value={reply === null ? '—' : `${reply.toFixed(1)} s`}>
                {reply === null ? (
                    <Pill>No replies today</Pill>
                ) : reply > REPLY_TARGET_S ? (
                    <Pill tone="amber">Target under {REPLY_TARGET_S} s</Pill>
                ) : (
                    <Pill tone="teal">Within the {REPLY_TARGET_S} s target</Pill>
                )}
            </Stat>
            <Stat label="Need a person" value={dash.need_person}>
                {dash.need_person > 0 ? <Pill tone="red">Review now</Pill> : <Pill>All clear</Pill>}
            </Stat>
        </div>
    )
}

/** "Start a call": the agent's state and the way into an individual call (the same pop-up as on Your Agent). */
function StartCall({ uid, agent }) {
    const live = useAppSelector((s) => LIVE.includes(s.call.status))
    const [open, setOpen] = useState(false)
    let body
    if (!agent) {
        body = (
            <>
                <p className="muted">Create your agent to start calling.</p>
                <Link className="button primary dash-cta" to={`/agent/${uid}`}>
                    Create your agent
                </Link>
            </>
        )
    } else if (live) {
        body = (
            <>
                <p className="muted">{agent.name} is on a call.</p>
                <Link className="button primary dash-cta" to={`/call/${uid}`}>
                    Return to call
                </Link>
            </>
        )
    } else {
        body = (
            <>
                <p className="muted">
                    {agent.status === 'busy' ? `${agent.name} is on a call.` : `${agent.name} is ready.`}
                </p>
                <button type="button" className="primary dash-cta" onClick={() => setOpen(true)}>
                    <svg
                        width="17"
                        height="17"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                    >
                        <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z" />
                    </svg>
                    New individual call
                </button>
            </>
        )
    }
    return (
        <section className="dash-card" aria-labelledby="start-call-title">
            <div className="dash-card-head">
                <h2 id="start-call-title">Start a call</h2>
            </div>
            {body}
            {open && <IndividualCallModal uid={uid} voice={agent?.voice} onClose={() => setOpen(false)} />}
        </section>
    )
}

export default function Dashboard() {
    const { me } = useOutletContext()
    const navigate = useNavigate()
    const dash = useGetDashboardQuery(me.uid, { pollingInterval: POLL_MS })
    const perDay = useGetCallsPerDayQuery(me.uid, { pollingInterval: POLL_MS })
    const { data: agent } = useGetAgentQuery(me.uid)
    const now = new Date()
    const failed = dash.isError || perDay.isError
    return (
        <main className="dash">
            <header className="dash-header">
                <div className="dash-hello">
                    <h1>
                        {greeting(now.getHours())}, {me.username}
                    </h1>
                    <p className="muted">
                        {now.toLocaleDateString(undefined, {
                            weekday: 'long',
                            day: 'numeric',
                            month: 'long',
                        })}
                    </p>
                </div>
                <LivePill uid={me.uid} />
                <button type="button" className="dash-search" disabled aria-label="Search (coming soon)">
                    <svg
                        width="17"
                        height="17"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                    >
                        <circle cx="11" cy="11" r="7" />
                        <path d="m20 20-4-4" />
                    </svg>
                    <span>Search</span>
                    <span className="nav-badge">Soon</span>
                </button>
                <button
                    type="button"
                    className="dash-avatar"
                    aria-label="Open your profile"
                    onClick={() => navigate(`/profile/${me.uid}`)}
                >
                    {me.avatar_url ? <img src={me.avatar_url} alt="" /> : initials(me.username)}
                </button>
            </header>

            {failed && (
                <div className="banner error" role="alert">
                    Could not load the dashboard.{' '}
                    <button
                        onClick={() => {
                            void dash.refetch()
                            void perDay.refetch()
                        }}
                    >
                        Retry
                    </button>
                </div>
            )}
            {!failed && (!dash.data || !perDay.data) && <p className="muted">Loading…</p>}
            {dash.data && perDay.data && (
                <>
                    <Stats dash={dash.data} days={perDay.data.days} />
                    <div className="dash-columns">
                        <div className="dash-main">
                            <WeeklyCalls days={perDay.data.days} />
                            <RecentCalls calls={dash.data.recent_calls} />
                        </div>
                        <div className="dash-side">
                            <NextActions
                                uid={me.uid}
                                actions={dash.data.next_actions}
                                agentName={agent?.name}
                            />
                            <StartCall uid={me.uid} agent={agent ?? null} />
                        </div>
                    </div>
                </>
            )}
        </main>
    )
}

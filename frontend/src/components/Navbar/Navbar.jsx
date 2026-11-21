import { NavLink } from 'react-router-dom'
import { useGetAgentQuery } from '../../api/api'
import { useAppSelector } from '../../app/hooks'
import { LIVE } from '../CallControls/CallControls'

const ICON = {
    dashboard: (
        <>
            <rect x="3" y="3" width="7" height="7" rx="1.5" />
            <rect x="14" y="3" width="7" height="7" rx="1.5" />
            <rect x="3" y="14" width="7" height="7" rx="1.5" />
            <rect x="14" y="14" width="7" height="7" rx="1.5" />
        </>
    ),
    agent: (
        <>
            <circle cx="12" cy="12" r="8" />
            <path d="M4.5 10c3 1.6 12 1.6 15 0M4.5 14c3 1.6 12 1.6 15 0" />
        </>
    ),
    calls: (
        <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z" />
    ),
    bulk: (
        <>
            <path d="m12 3 9 5-9 5-9-5 9-5z" />
            <path d="m3 13 9 5 9-5" />
        </>
    ),
    profile: (
        <>
            <circle cx="12" cy="8" r="4" />
            <path d="M4 21a8 8 0 0 1 16 0" />
        </>
    ),
    settings: (
        <>
            <circle cx="12" cy="12" r="3" />
            <path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1" />
        </>
    ),
}

/** `path` null: shown but not available yet (no page behind it). `badge`: a small tag after the label. */
export const NAV_ITEMS = [
    { label: 'Dashboard', path: 'dashboard', icon: 'dashboard' },
    { label: 'Your agent', path: 'agent', icon: 'agent' },
    { label: 'Calls', path: null, icon: 'calls', badge: 'Soon' },
    { label: 'Bulk calling', path: 'bulk-calling', icon: 'bulk', badge: 'Soon' },
    { label: 'Profile', path: 'profile', icon: 'profile' },
    { label: 'Settings', path: 'settings', icon: 'settings' },
]

function NavIcon({ name }) {
    return (
        <svg
            className="nav-icon"
            width="19"
            height="19"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
        >
            {ICON[name]}
        </svg>
    )
}

/** The voice orb: the app's mark, and the agent's avatar in the card at the bottom. */
export function Orb({ size = 28, glow = false }) {
    return (
        <span
            className={`orb ${glow ? 'glow' : ''}`}
            style={{ width: size, height: size }}
            aria-hidden="true"
        />
    )
}

/** The agent at the bottom of the navbar: its name and whether it is on a call right now. */
function AgentCard({ uid }) {
    const { data: agent } = useGetAgentQuery(uid)
    const live = useAppSelector((s) => LIVE.includes(s.call.status))
    if (agent === undefined) return null // still loading
    const status = !agent ? 'No agent yet' : live || agent.status === 'busy' ? 'In a call' : 'Free'
    return (
        <div className="nav-agent">
            <Orb size={36} />
            <div className="nav-agent-text">
                <span className="nav-agent-name">{agent ? agent.name : 'Your agent'}</span>
                <span className="muted">{status}</span>
            </div>
        </div>
    )
}

/** The one vertical navbar shared by every signed-in page. */
export default function Navbar({ uid }) {
    return (
        <nav className="navbar" aria-label="Main">
            <div className="nav-brand">
                <Orb glow />
                <span>Alex</span>
            </div>
            {NAV_ITEMS.map((i) => {
                const inner = (
                    <>
                        <NavIcon name={i.icon} />
                        <span>{i.label}</span>
                        {i.badge && <span className="nav-badge">{i.badge}</span>}
                    </>
                )
                return i.path ? (
                    <NavLink
                        key={i.label}
                        to={`/${i.path}/${uid}`}
                        className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                    >
                        {inner}
                    </NavLink>
                ) : (
                    <span key={i.label} className="nav-link disabled" aria-disabled="true">
                        {inner}
                    </span>
                )
            })}
            <AgentCard uid={uid} />
        </nav>
    )
}

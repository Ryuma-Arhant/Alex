import { NavLink } from 'react-router-dom'

export const NAV_ITEMS = [
    { label: 'Dashboard', path: 'dashboard' },
    { label: 'Your Agent', path: 'agent' },
    { label: 'Bulk Calling', path: 'bulk-calling' },
    { label: 'My Profile', path: 'profile' },
    { label: 'Settings', path: 'settings' },
]

/** The one vertical navbar shared by every signed-in page. */
export default function Navbar({ uid }) {
    return (
        <nav className="navbar" aria-label="Main">
            {NAV_ITEMS.map((i) => (
                <NavLink
                    key={i.path}
                    to={`/${i.path}/${uid}`}
                    className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}
                >
                    {i.label}
                </NavLink>
            ))}
        </nav>
    )
}

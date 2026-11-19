import { useNavigate, useOutletContext } from 'react-router-dom'
import CallsGraph from '../components/Dashboard/CallsGraph'
import ProfileIcon from '../components/Auth/ProfileIcon'

export default function Dashboard() {
    const { me } = useOutletContext()
    const navigate = useNavigate()
    return (
        <div className="page-column">
            <div className="page-top">
                <h1 className="page-title">Welcome back, {me.username}!</h1>
                <button
                    className="icon-button"
                    aria-label="Open your profile"
                    onClick={() => navigate(`/profile/${me.uid}`)}
                >
                    <ProfileIcon user={me} />
                </button>
            </div>
            <div className="page-body">
                <CallsGraph uid={me.uid} />
            </div>
        </div>
    )
}

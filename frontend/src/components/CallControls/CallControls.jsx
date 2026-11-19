import { useState } from 'react'
import { Link } from 'react-router-dom'
import { errorMessage } from '../../api/api'
import { useAppSelector } from '../../app/hooks'
import { useCall } from '../../features/call/CallProvider'
const LABEL = {
    idle: 'Not connected',
    connecting: 'Connecting…',
    waiting_for_agent: 'Waiting for the agent…',
    connected: 'Connected',
    reconnecting: 'Reconnecting…',
    ended: 'Call ended',
    failed: 'Call failed',
}
export const LIVE = ['connecting', 'waiting_for_agent', 'connected', 'reconnecting']
export default function CallControls({ backTo }) {
    const { status, muted, error } = useAppSelector((s) => s.call)
    const { client, start, end, setMuted } = useCall()
    const [restartError, setRestartError] = useState(null)
    const [restarting, setRestarting] = useState(false)
    const live = LIVE.includes(status)
    const callAgain = async () => {
        setRestartError(null)
        setRestarting(true)
        try {
            await start(client)
        } catch (err) {
            setRestartError(errorMessage(err, 'Could not start the call. Please try again.'))
        } finally {
            setRestarting(false)
        }
    }
    const shownError = restartError ?? error
    return (
        <div className="controls">
            {shownError && (
                <div className="banner error" role="alert">
                    {shownError}
                </div>
            )}
            <div className="row">
                <span className={`dot ${status}`} aria-hidden />{' '}
                <span aria-live="polite">{LABEL[status]}</span>
            </div>
            <div className="row">
                {!live && (
                    <>
                        <Link className="button" to={backTo}>
                            Back to Your Agent
                        </Link>
                        {client && (
                            <button
                                className="primary"
                                onClick={() => void callAgain()}
                                disabled={restarting}
                            >
                                {restarting ? 'Starting…' : 'Call again'}
                            </button>
                        )}
                    </>
                )}
                {live && (
                    <>
                        <button onClick={() => void setMuted(!muted)} aria-pressed={muted}>
                            {muted ? 'Unmute' : 'Mute'}
                        </button>
                        <button className="danger" onClick={() => void end()}>
                            End call
                        </button>
                    </>
                )}
            </div>
        </div>
    )
}

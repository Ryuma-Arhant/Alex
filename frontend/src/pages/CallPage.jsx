import { useEffect, useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { useGetCallQuery } from '../api/api'
import { useAppSelector } from '../app/hooks'
import CallControls from '../components/CallControls/CallControls'
import ChatBox from '../components/ChatBox/ChatBox'
import Sphere, { sphereMode } from '../components/Sphere/Sphere'
import SummaryPanel from '../components/SummaryCard/SummaryPanel'
import { useCall } from '../features/call/CallProvider'
import { selectEntries } from '../features/transcript/slice'
import { formatAmount } from '../lib/money'
import { usePrefersReducedMotion } from '../lib/usePrefersReducedMotion'
import { NOT_CONNECTED } from '../lib/callOutcome'

const SUMMARY_POLL_MS = 2500 // the agent writes the summary a few seconds after the call ends

/** "+91 •••• ••5678": enough to recognise the client without putting the full number on screen. */
const maskPhone = (phone) => {
    const digits = phone.replace(/[^\d+]/g, '')
    return digits.length > 4 ? `${digits.slice(0, -4).replace(/\d/g, '•')}${digits.slice(-4)}` : digits
}

/**
 * The individual call with the user's Loan-Recovery Agent: the same page the Manager used. Conversation and the
 * shape-shifting sphere in the middle; once the call ends, the summary opens on the right.
 */
export default function CallPage() {
    const { me } = useOutletContext()
    const { status, agentState, currentCallId, mode } = useAppSelector((s) => s.call)
    const entries = useAppSelector(selectEntries)
    const { manager, client } = useCall()
    const reduced = usePrefersReducedMotion()
    const ended = status === 'ended'
    const [waiting, setWaiting] = useState(true) // poll until the summary is written or has failed
    const { data: call } = useGetCallQuery(currentCallId ?? '', {
        skip: !ended || !currentCallId,
        pollingInterval: waiting ? SUMMARY_POLL_MS : 0,
    })
    const summaryStatus = call?.summary_status ?? 'PENDING'
    useEffect(() => setWaiting(summaryStatus === 'PENDING'), [summaryStatus])
    const backTo = `/agent/${me.uid}`
    if (status === 'idle' || !client)
        return (
            <div className="page-column">
                <div className="page-top">
                    <h1 className="page-title">Call</h1>
                </div>
                <div className="page-body">
                    <p className="muted">
                        No call is in progress. Start one from Your Agent with “Call Agent”.
                    </p>
                    <CallControls backTo={backTo} />
                </div>
            </div>
        )
    return (
        <div className={`call-layout ${ended ? 'with-summary' : ''}`}>
            <section className="call-main">
                <header className="call-head">
                    <h1 className="call-title">{mode === 'phone' ? 'Phone call' : 'Individual call'}</h1>
                    <p className="muted call-client">
                        <span className="mono">{maskPhone(client.phone)}</span> · Pending{' '}
                        {formatAmount(client.amount, client.currency)}
                    </p>
                    {ended && NOT_CONNECTED[call?.end_reason] && (
                        <p className="banner notice" role="status">
                            The call did not connect: {NOT_CONNECTED[call.end_reason]}.
                        </p>
                    )}
                </header>
                <Sphere
                    mode={sphereMode(status, agentState)}
                    getLevels={() => manager.getLevels()}
                    reducedMotion={reduced}
                />
                <ChatBox bubbles={entries} />
                <CallControls backTo={backTo} />
            </section>
            {/* The summary panel opens the moment the call ends and fills in when the summary is ready. */}
            {ended && <SummaryPanel summary={call?.summary ?? null} status={summaryStatus} />}
        </div>
    )
}

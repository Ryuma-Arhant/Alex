import { useState } from 'react'
import { useOutletContext, useSearchParams } from 'react-router-dom'
import {
    errorMessage,
    useCreateAgentMutation,
    useDeleteAgentMutation,
    useGetAgentQuery,
    useRenameAgentMutation,
} from '../api/api'
import CallAgent from '../components/CallAgent/CallAgent'
import Modal from '../components/Modal/Modal'
import { VOICES, voiceLabel } from '../lib/voice'

const POLL_MS = 15_000 // keeps the Free / In-Call state current while the page is open
const STATUS = { free: 'Free', busy: 'In-Call' }

function NameModal({ title, label, initial = '', submitLabel, busyLabel, onSubmit, onClose }) {
    const [name, setName] = useState(initial)
    const [error, setError] = useState(null)
    const [busy, setBusy] = useState(false)
    const trimmed = name.trim()
    const submit = async (e) => {
        e.preventDefault()
        setError(null)
        setBusy(true)
        try {
            await onSubmit(trimmed)
        } catch (err) {
            setError(errorMessage(err))
            setBusy(false)
        }
    }
    return (
        <Modal title={title} onClose={onClose} busy={busy}>
            <form className="modal-form" onSubmit={(e) => void submit(e)}>
                {error && (
                    <div className="banner error" role="alert">
                        {error}
                    </div>
                )}
                <label>
                    {label}
                    <input
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        onFocus={(e) => e.target.select()}
                        required
                        maxLength={80}
                        autoComplete="off"
                    />
                </label>
                <div className="box-actions">
                    <button type="button" onClick={onClose} disabled={busy}>
                        Cancel
                    </button>
                    <button className="primary" disabled={busy || trimmed === '' || trimmed === initial}>
                        {busy ? busyLabel : submitLabel}
                    </button>
                </div>
            </form>
        </Modal>
    )
}

/** Creating an agent asks for its name and its voice; Create stays disabled until both are given. */
function CreateAgentModal({ onSubmit, onClose }) {
    const [name, setName] = useState('')
    const [voice, setVoice] = useState(null)
    const [error, setError] = useState(null)
    const [busy, setBusy] = useState(false)
    const trimmed = name.trim()
    const submit = async (e) => {
        e.preventDefault()
        if (!trimmed || !voice) return
        setError(null)
        setBusy(true)
        try {
            await onSubmit({ name: trimmed, voice })
        } catch (err) {
            setError(errorMessage(err))
            setBusy(false)
        }
    }
    return (
        <Modal title="Create your agent" onClose={onClose} busy={busy}>
            <form className="modal-form" onSubmit={(e) => void submit(e)}>
                {error && (
                    <div className="banner error" role="alert">
                        {error}
                    </div>
                )}
                <label>
                    Name
                    <input
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        required
                        maxLength={80}
                        autoComplete="off"
                    />
                </label>
                <div className="voice-field">
                    <span id="agent-voice-label">Voice</span>
                    <div
                        role="radiogroup"
                        aria-labelledby="agent-voice-label"
                        aria-required="true"
                        className="swatch-row"
                    >
                        {VOICES.map((v) => (
                            <button
                                key={v.value}
                                type="button"
                                role="radio"
                                aria-checked={voice === v.value}
                                onClick={() => setVoice(v.value)}
                                disabled={busy}
                            >
                                {v.label}
                            </button>
                        ))}
                    </div>
                </div>
                <div className="box-actions">
                    <button type="button" onClick={onClose} disabled={busy}>
                        Cancel
                    </button>
                    <button className="primary" disabled={busy || trimmed === '' || !voice}>
                        {busy ? 'Creating…' : 'Create'}
                    </button>
                </div>
            </form>
        </Modal>
    )
}

function DeleteModal({ onConfirm, onClose }) {
    const [error, setError] = useState(null)
    const [busy, setBusy] = useState(false)
    const confirm = async () => {
        setError(null)
        setBusy(true)
        try {
            await onConfirm()
        } catch (err) {
            setError(errorMessage(err))
            setBusy(false)
        }
    }
    return (
        <Modal title="Are you sure you want to delete the agent?" onClose={onClose} busy={busy}>
            {error && (
                <div className="banner error" role="alert">
                    {error}
                </div>
            )}
            <div className="box-actions">
                <button type="button" onClick={onClose} disabled={busy}>
                    Cancel
                </button>
                <button type="button" className="danger" onClick={() => void confirm()} disabled={busy}>
                    {busy ? 'Deleting…' : 'Yes, delete the agent'}
                </button>
            </div>
        </Modal>
    )
}

function StatusDot({ status }) {
    return <span className={`status-dot ${status}`} aria-hidden />
}

/** The agent holder: an empty "+" slot with a create button (no agent yet), or the agent's square tile. */
function AgentHolder({ uid, agent, onOpen }) {
    const [creating, setCreating] = useState(false)
    const [createAgent] = useCreateAgentMutation()
    if (!agent)
        return (
            <section className="agent-holder" aria-label="Your agent">
                <div className="agent-slot empty" role="img" aria-label="No agent yet">
                    <svg viewBox="0 0 24 24" width="56" height="56" aria-hidden>
                        <path
                            d="M12 4v16M4 12h16"
                            stroke="currentColor"
                            strokeWidth="1.6"
                            strokeLinecap="round"
                        />
                    </svg>
                </div>
                <button className="primary" onClick={() => setCreating(true)}>
                    + Create Agent
                </button>
                {creating && (
                    <CreateAgentModal
                        onClose={() => setCreating(false)}
                        onSubmit={async ({ name, voice }) => {
                            await createAgent({ uid, name, voice }).unwrap()
                            setCreating(false)
                        }}
                    />
                )}
            </section>
        )
    return (
        <section className="agent-holder" aria-label="Your agent">
            <div className="agent-row">
                <button
                    type="button"
                    className="agent-slot agent-tile"
                    onClick={onOpen}
                    aria-label={`${agent.name}, ${STATUS[agent.status]}. Open agent details`}
                >
                    <span className="agent-tile-dot">
                        <StatusDot status={agent.status} />
                    </span>
                    <span className="agent-tile-name">{agent.name}</span>
                    <span className={`agent-tile-status ${agent.status}`}>{STATUS[agent.status]}</span>
                </button>
                <CallAgent uid={uid} voice={agent.voice} />
            </div>
        </section>
    )
}

/** Replaces the holder when the tile is clicked: the agent's name, its system prompt, rename and delete. */
function AgentDetails({ uid, agent, onBack }) {
    const [dialog, setDialog] = useState(null) // 'rename' | 'delete' | null
    const [renameAgent] = useRenameAgentMutation()
    const [deleteAgent] = useDeleteAgentMutation()
    const close = () => setDialog(null)
    return (
        <section className="agent-details" aria-labelledby="agent-details-name">
            <div className="agent-details-head">
                <button type="button" onClick={onBack}>
                    ← Back
                </button>
                <span className={`agent-tile-status ${agent.status}`}>
                    <StatusDot status={agent.status} /> {STATUS[agent.status]}
                </span>
            </div>
            <div className="field">
                <span className="field-label">Name</span>
                <h2 id="agent-details-name" className="agent-details-name">
                    {agent.name}
                </h2>
                <span className="muted">{agent.role}</span>
            </div>
            <div className="field">
                <span className="field-label">Voice</span>
                <span>{voiceLabel(agent.voice)}</span>
            </div>
            <div className="field">
                <span className="field-label" id="system-prompt-label">
                    System prompt
                </span>
                <pre
                    className="readonly-field system-prompt"
                    aria-labelledby="system-prompt-label"
                    tabIndex={0}
                >
                    {agent.system_prompt}
                </pre>
            </div>
            <div className="agent-details-actions">
                <button type="button" onClick={() => setDialog('rename')}>
                    Rename Agent
                </button>
                <button type="button" className="danger" onClick={() => setDialog('delete')}>
                    Delete Agent
                </button>
            </div>
            {dialog === 'rename' && (
                <NameModal
                    title="Rename agent"
                    label="New Name"
                    initial={agent.name}
                    submitLabel="Rename"
                    busyLabel="Renaming…"
                    onClose={close}
                    onSubmit={async (name) => {
                        await renameAgent({ uid, name }).unwrap()
                        close()
                    }}
                />
            )}
            {dialog === 'delete' && (
                <DeleteModal
                    onClose={close}
                    onConfirm={async () => {
                        await deleteAgent(uid).unwrap()
                        close()
                        onBack()
                    }}
                />
            )}
        </section>
    )
}

export default function YourAgent() {
    const { me } = useOutletContext()
    const [params, setParams] = useSearchParams()
    const {
        data: agent,
        isLoading,
        isError,
        refetch,
    } = useGetAgentQuery(me.uid, { pollingInterval: POLL_MS })
    const showDetails = params.get('view') === 'details' && !!agent
    const open = () => setParams({ view: 'details' })
    const back = () => setParams({}, { replace: true })
    return (
        <div className="page-column">
            <div className="page-top">
                <h1 className="page-title">Your Agent</h1>
            </div>
            <div className="page-body">
                {isLoading ? (
                    <p className="muted">Loading…</p>
                ) : isError ? (
                    <div className="banner error" role="alert">
                        Could not load your agent. <button onClick={() => void refetch()}>Retry</button>
                    </div>
                ) : showDetails ? (
                    <AgentDetails uid={me.uid} agent={agent} onBack={back} />
                ) : (
                    <AgentHolder uid={me.uid} agent={agent ?? null} onOpen={open} />
                )}
            </div>
        </div>
    )
}

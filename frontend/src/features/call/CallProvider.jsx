import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useAppDispatch } from '../../app/hooks'
import { useCreateAgentCallMutation, useEndCallMutation } from '../../api/api'
import { CallRoomManager } from '../../lib/livekit/roomManager'
import { segmentUpserted, transcriptCleared } from '../transcript/slice'
import { agentStateChanged, callEnded, callFailed, callStarting, muteChanged, statusChanged } from './slice'
const Ctx = createContext(null)

/**
 * Owns the one LiveKit room for the signed-in user's Loan-Recovery Agent. Mounted by AppLayout, so a call keeps
 * running while the user moves between pages; it is only torn down on sign-out (layout unmount).
 */
export function CallProvider({ children, uid }) {
    const dispatch = useAppDispatch()
    const [createAgentCall] = useCreateAgentCallMutation()
    const [endCallApi] = useEndCallMutation()
    const [manager] = useState(() => new CallRoomManager())
    const callId = useRef(null)
    const ended = useRef(false)
    const busy = useRef(false) // a call is being created or is live: blocks duplicate starts
    const [client, setClient] = useState(null) // the details of the current / last call, for display and "Call again"
    const finish = useCallback(() => {
        busy.current = false
        if (ended.current) return
        ended.current = true
        dispatch(callEnded(callId.current ?? undefined))
    }, [dispatch])

    /**
     * Creates the call on the server (which writes the client details into this call's own agent prompt), then joins
     * the room. Resolves once the call exists, with its id, so the caller can show the Call Page while the room
     * connects; rejects with the API error when the server refuses (bad input, no agent), so the caller can show it.
     * Resolves null if a call is already starting or live.
     */
    const start = useCallback(
        async (details) => {
            if (busy.current) return null
            busy.current = true
            let r
            try {
                r = await createAgentCall({ uid, ...details }).unwrap()
            } catch (err) {
                busy.current = false
                throw err
            }
            ended.current = false
            callId.current = r.call_id
            setClient(details)
            dispatch(transcriptCleared())
            dispatch(callStarting(r.call_id))
            void manager
                .connect(r.livekit_url, r.token, {
                    onStatus: (s) => dispatch(statusChanged(s)),
                    onAgentState: (s) => dispatch(agentStateChanged(s)),
                    onSegment: (u) => dispatch(segmentUpserted(u)),
                    onError: (m) => dispatch(callFailed(m)),
                    onDisconnected: finish,
                })
                .catch(() => {
                    dispatch(callFailed('Could not connect the call. Please try again.'))
                    finish()
                })
            return r.call_id
        },
        [createAgentCall, uid, dispatch, finish, manager],
    )
    const end = useCallback(async () => {
        const id = callId.current
        await manager.disconnect()
        finish()
        if (id) void endCallApi(id)
    }, [endCallApi, finish, manager])
    const setMuted = useCallback(
        async (m) => {
            await manager.setMuted(m)
            dispatch(muteChanged(m))
        },
        [dispatch, manager],
    )
    useEffect(() => () => void manager.disconnect(), [manager])
    const value = useMemo(
        () => ({ manager, client, start, end, setMuted }),
        [manager, client, start, end, setMuted],
    )
    return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
export function useCall() {
    const c = useContext(Ctx)
    if (!c) throw new Error('useCall outside CallProvider')
    return c
}

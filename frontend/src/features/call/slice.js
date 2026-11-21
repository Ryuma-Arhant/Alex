import { createSlice } from '@reduxjs/toolkit'
export const initialState = {
  status: 'idle',
  agentState: 'idle',
  muted: false,
  currentCallId: null,
  error: null,
  connectedAt: null, // ms timestamp of the first 'connected' of this call (the Live timer counts from it)
}
export const callSlice = createSlice({
  name: 'call',
  initialState,
  reducers: {
    callStarting: (_s, a) => ({
      ...initialState,
      status: 'connecting',
      currentCallId: a.payload,
    }),
    statusChanged: {
      reducer: (s, a) => {
        s.status = a.payload
        if (a.payload === 'connected' && s.connectedAt === null) s.connectedAt = a.meta.at
      },
      prepare: (status) => ({ payload: status, meta: { at: Date.now() } }),
    },
    agentStateChanged: (s, a) => {
      s.agentState = a.payload
    },
    muteChanged: (s, a) => {
      s.muted = a.payload
    },
    callFailed: (s, a) => {
      s.status = 'failed'
      s.error = a.payload
      s.agentState = 'idle'
    },
    callEnded: (s, _a) => {
      s.status = 'ended'
      s.agentState = 'idle'
    },
    callReset: () => initialState,
  },
})
export const {
  callStarting,
  statusChanged,
  agentStateChanged,
  muteChanged,
  callFailed,
  callEnded,
  callReset,
} = callSlice.actions
export default callSlice.reducer

import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'

export const readCookie = (name) => {
  try {
    const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
    return m ? decodeURIComponent(m[1]) : null
  } catch {
    return null
  }
}

const raw = fetchBaseQuery({
  baseUrl: `${location.origin}/api/v1`,
  credentials: 'include',
  prepareHeaders: (headers) => {
    const csrf = readCookie('csrf_token')
    if (csrf) headers.set('X-CSRF-Token', csrf)
    return headers
  },
})

// Endpoints whose 401 is an expected answer rather than an expired session.
const AUTH_QUIET = new Set(['me', 'login', 'register'])

const baseQuery = async (args, api, extra) => {
  const result = await raw(args, api, extra)
  if (result.error?.status === 401 && !AUTH_QUIET.has(api.endpoint)) {
    if (location.pathname !== '/checkin') location.assign('/checkin')
  }
  return result
}

const browserTimeZone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined
  } catch {
    return undefined
  }
}

const serverDown = (err) =>
  err?.status === 'FETCH_ERROR' || err?.status === 'PARSING_ERROR' || err?.status >= 500

export const errorMessage = (err, fallback = 'Something went wrong. Please try again.') =>
  err?.data?.error?.message ??
  (Array.isArray(err?.data?.detail) ? err.data.detail[0]?.msg : undefined) ??
  (serverDown(err) ? 'Cannot reach the server. Please make sure the backend is running.' : fallback)

export const api = createApi({
  reducerPath: 'api',
  baseQuery,
  tagTypes: ['Me', 'Agent', 'CallsPerDay', 'ScreenTime', 'Call', 'Dashboard', 'Bulk'],
  endpoints: (b) => ({
    // --- auth / user ---
    authConfig: b.query({ query: () => '/auth/config' }),
    me: b.query({ query: () => '/auth/me', providesTags: ['Me'] }),
    register: b.mutation({
      query: (body) => ({ url: '/auth/register', method: 'POST', body }),
      invalidatesTags: ['Me'],
    }),
    login: b.mutation({
      query: (body) => ({ url: '/auth/login', method: 'POST', body }),
      invalidatesTags: ['Me'],
    }),
    logout: b.mutation({ query: () => ({ url: '/auth/logout', method: 'POST' }) }),
    uploadAvatar: b.mutation({
      query: ({ uid, file }) => ({
        url: `/users/${uid}/avatar`,
        method: 'PUT',
        body: file,
        headers: { 'Content-Type': file.type || 'application/octet-stream' },
      }),
      invalidatesTags: ['Me'],
    }),
    // --- the user's single agent (null when there is none) ---
    getAgent: b.query({ query: (uid) => `/users/${uid}/agent`, providesTags: ['Agent'] }),
    createAgent: b.mutation({
      query: ({ uid, name, voice }) => ({
        url: `/users/${uid}/agent`,
        method: 'POST',
        body: { name, voice },
      }),
      invalidatesTags: ['Agent', 'Me', 'CallsPerDay', 'Dashboard'],
    }),
    renameAgent: b.mutation({
      query: ({ uid, name }) => ({ url: `/users/${uid}/agent`, method: 'PUT', body: { name } }),
      invalidatesTags: ['Agent'],
    }),
    deleteAgent: b.mutation({
      query: (uid) => ({ url: `/users/${uid}/agent`, method: 'DELETE' }),
      invalidatesTags: ['Agent', 'Me', 'CallsPerDay', 'Dashboard'],
    }),
    // --- calls made by the agent ---
    /** Individual call: phone, amount and client context in; a LiveKit room the browser joins out. The context is
     * written into this call's own Loan-Recovery prompt on the server, so the agent has it before it speaks. */
    createAgentCall: b.mutation({
      query: ({ uid, ...body }) => ({ url: `/users/${uid}/collections/calls`, method: 'POST', body }),
      invalidatesTags: ['Agent', 'CallsPerDay', 'Dashboard'],
    }),
    getCall: b.query({ query: (id) => `/calls/${id}`, providesTags: (_r, _e, id) => [{ type: 'Call', id }] }),
    endCall: b.mutation({
      query: (id) => ({ url: `/calls/${id}/end`, method: 'POST' }),
      invalidatesTags: ['Agent', 'Dashboard'],
    }),
    // --- dashboard / screen time ---
    getCallsPerDay: b.query({
      query: (uid) => ({ url: `/users/${uid}/stats/calls-per-day`, params: { tz: browserTimeZone() } }),
      providesTags: ['CallsPerDay'],
    }),
    /** Today's figures, the agent's recent calls and today's next actions (all from real calls). */
    getDashboard: b.query({
      query: (uid) => ({ url: `/users/${uid}/dashboard`, params: { tz: browserTimeZone() } }),
      providesTags: ['Dashboard'],
    }),
    /** Ticks a next action off (or back on). The list updates at once and rolls back if the server refuses. */
    setNextActionDone: b.mutation({
      query: ({ uid, callId, index, done }) => ({
        url: `/users/${uid}/dashboard/next-actions/${callId}/${index}`,
        method: 'PUT',
        body: { done },
      }),
      async onQueryStarted({ uid, callId, index, done }, { dispatch, queryFulfilled }) {
        const patch = dispatch(
          api.util.updateQueryData('getDashboard', uid, (d) => {
            const a = d.next_actions.find((x) => x.call_id === callId && x.index === index)
            if (a) a.done = done
          }),
        )
        try {
          await queryFulfilled
        } catch {
          patch.undo()
        }
      },
    }),
    getScreenTime: b.query({
      query: ({ uid, weekStart }) => ({
        url: `/users/${uid}/screen-time`,
        params: { tz: browserTimeZone(), ...(weekStart ? { week_start: weekStart } : {}) },
      }),
      providesTags: ['ScreenTime'],
    }),
    sendHeartbeat: b.mutation({
      query: ({ uid, seconds }) => ({
        url: `/users/${uid}/screen-time/heartbeat`,
        method: 'POST',
        body: { seconds, tz: browserTimeZone() },
      }),
    }),
    // --- bulk calling ---
    /** Starts phoning the file's valid rows, one at a time (needs phone calls set up). */
    startBulkCall: b.mutation({
      query: ({ uid, file }) => ({
        url: `/users/${uid}/bulk-calls`,
        method: 'POST',
        params: { file_name: file.name },
        body: file,
        headers: { 'Content-Type': 'text/csv' },
      }),
      invalidatesTags: ['Bulk', 'Agent', 'Dashboard'],
    }),
    /** The latest bulk run (null when there has been none), each borrower with only the last 4 digits. */
    getBulkCall: b.query({ query: (uid) => `/users/${uid}/bulk-calls/current`, providesTags: ['Bulk'] }),
    controlBulkCall: b.mutation({
      query: ({ uid, jobId, action }) => ({
        url: `/users/${uid}/bulk-calls/${jobId}/${action}`,
        method: 'POST',
      }),
      invalidatesTags: ['Bulk'],
    }),
    previewBulkCsv: b.mutation({
      query: ({ uid, file }) => ({
        url: `/users/${uid}/bulk-calls/preview`,
        method: 'POST',
        body: file,
        headers: { 'Content-Type': 'text/csv' },
      }),
    }),
  }),
})

export const {
  useAuthConfigQuery,
  useMeQuery,
  useRegisterMutation,
  useLoginMutation,
  useLogoutMutation,
  useUploadAvatarMutation,
  useGetAgentQuery,
  useCreateAgentMutation,
  useRenameAgentMutation,
  useDeleteAgentMutation,
  useCreateAgentCallMutation,
  useGetCallQuery,
  useEndCallMutation,
  useGetCallsPerDayQuery,
  useGetDashboardQuery,
  useSetNextActionDoneMutation,
  useGetScreenTimeQuery,
  usePreviewBulkCsvMutation,
  useStartBulkCallMutation,
  useGetBulkCallQuery,
  useControlBulkCallMutation,
} = api

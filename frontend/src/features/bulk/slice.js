import { createSlice } from '@reduxjs/toolkit'

/**
 * The CSV queue: the file uploaded on the Bulk Calling page and its server-validated rows. It lives in the store (not
 * in the page) so it survives navigation and the Your Agent page can check it before a bulk call. It is kept for this
 * browser session only; the server stores nothing (see bulk_service.parse_csv).
 */
export const initialState = { files: [] } // [{ fileName, uploadedAt, result }]

export const bulkSlice = createSlice({
  name: 'bulk',
  initialState,
  reducers: {
    // One file at a time for now: a new upload replaces the previous one.
    csvUploaded: (s, a) => {
      s.files = [a.payload]
    },
    csvCleared: () => initialState,
  },
})
export const { csvUploaded, csvCleared } = bulkSlice.actions
export default bulkSlice.reducer

export const selectCsvFiles = (st) => st.bulk.files
/** Files with at least one row that passed validation: what a bulk call could actually use. */
export const selectReadyCsvFiles = (st) => st.bulk.files.filter((f) => f.result.valid > 0)

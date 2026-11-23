/**
 * The uploaded CSV files themselves, for starting a bulk call. Kept outside Redux (a File is not serializable) and
 * only in memory, for this browser session, like the preview in the bulk slice. Keyed by the upload's `uploadedAt`.
 * The exact bytes are sent, so files saved by Excel in any encoding are read the same way as by the preview.
 */
const files = new Map()

export const rememberCsvFile = (uploadedAt, file) => {
  files.clear() // one file at a time, like the bulk slice
  files.set(uploadedAt, file)
}
export const csvFileFor = (uploadedAt) => files.get(uploadedAt) ?? null
export const forgetCsvFiles = () => files.clear()

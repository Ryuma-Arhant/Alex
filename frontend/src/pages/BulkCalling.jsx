import { useState } from 'react'
import { useOutletContext } from 'react-router-dom'
import { errorMessage, usePreviewBulkCsvMutation } from '../api/api'
import { useAppDispatch, useAppSelector } from '../app/hooks'
import { csvCleared, csvUploaded, selectCsvFiles } from '../features/bulk/slice'
import { formatAmount } from '../lib/money'

export const MAX_BYTES = 1024 * 1024 // the server enforces the same limit

const SAMPLE = [
    'name,phone,amount_due,deadline,lender,loan_reference,notes',
    'Ravi Kumar,+919876543210,5200.50,2026-12-05,Sunrise Bank,LN-10234,',
    'Asha Rao,+919812345678,12000,10/12/2026,Sunrise Bank,LN-10571,Prefers Hindi',
].join('\n')

const COLUMNS = [
    { name: 'name', note: 'Name of the person to call', required: true },
    { name: 'phone', note: 'Mobile number, with country code (e.g. +919876543210)', required: true },
    { name: 'amount_due', note: 'Amount overdue, e.g. 5200 or 5200.50', required: true },
    { name: 'deadline', note: 'Date to pay by: 2026-12-05 or 05/12/2026 (day first)', required: true },
    { name: 'lender', note: 'Bank or lender name' },
    { name: 'currency', note: '3-letter code; INR if left out' },
    { name: 'loan_reference', note: 'Loan or account reference' },
    { name: 'notes', note: 'Anything else about this borrower' },
]

const formatDate = (iso) => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso)
    if (!m) return iso
    return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])).toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
    })
}

/** Client-side checks before upload; the server re-checks everything. */
export function checkFile(file) {
    if (!/\.csv$/i.test(file.name)) return 'Please choose a .csv file.'
    if (file.size === 0) return 'The file is empty.'
    if (file.size > MAX_BYTES) return 'The file must be 1 MB or smaller.'
    return null
}

function downloadSample() {
    const url = URL.createObjectURL(new Blob([SAMPLE + '\n'], { type: 'text/csv' }))
    const a = document.createElement('a')
    a.href = url
    a.download = 'bulk-calling-sample.csv'
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 0)
}

function PreviewTable({ result, fileName, onClear }) {
    const [onlyProblems, setOnlyProblems] = useState(false)
    const rows = onlyProblems ? result.rows.filter((r) => !r.valid || r.warnings.length > 0) : result.rows
    return (
        <section className="bulk-preview" aria-labelledby="bulk-preview-title">
            <div className="bulk-preview-head">
                <div>
                    <h2 id="bulk-preview-title">Preview</h2>
                    <p className="muted">{fileName}</p>
                </div>
                <button type="button" onClick={onClear}>
                    Choose another file
                </button>
            </div>
            <ul className="bulk-stats" aria-label="Summary">
                <li>
                    <strong>{result.total}</strong> {result.total === 1 ? 'person' : 'people'}
                </li>
                <li className="ok">
                    <strong>{result.valid}</strong> ready
                </li>
                <li className={result.invalid ? 'bad' : ''}>
                    <strong>{result.invalid}</strong> with errors
                </li>
            </ul>
            {result.ignored_columns.length > 0 && (
                <p className="muted">Ignored column(s): {result.ignored_columns.join(', ')}</p>
            )}
            {result.invalid > 0 && (
                <p className="muted">
                    Rows with errors will be skipped. Fix them in the file and upload it again.
                </p>
            )}
            <label className="inline-check">
                <input
                    type="checkbox"
                    checked={onlyProblems}
                    onChange={(e) => setOnlyProblems(e.target.checked)}
                />
                Show only rows that need attention
            </label>
            <div className="table-wrap" tabIndex={0} role="region" aria-label="Borrowers in the file">
                <table className="bulk-table">
                    <thead>
                        <tr>
                            <th scope="col">Line</th>
                            <th scope="col">Name</th>
                            <th scope="col">Phone</th>
                            <th scope="col">Amount due</th>
                            <th scope="col">Deadline</th>
                            <th scope="col">Lender</th>
                            <th scope="col">Loan ref.</th>
                            <th scope="col">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((r) => (
                            <tr key={r.line} className={r.valid ? '' : 'invalid'}>
                                <td className="num">{r.line}</td>
                                <td>{r.name || '—'}</td>
                                <td className="mono">{r.phone || '—'}</td>
                                <td className="num">
                                    {r.valid ? formatAmount(r.amount, r.currency) : r.amount || '—'}
                                </td>
                                <td>{r.valid ? formatDate(r.deadline) : r.deadline || '—'}</td>
                                <td>{r.lender || '—'}</td>
                                <td>{r.loan_reference || '—'}</td>
                                <td>
                                    {r.valid ? (
                                        <span className="row-ok">Ready</span>
                                    ) : (
                                        <ul className="row-errors">
                                            {r.errors.map((e) => (
                                                <li key={e}>{e}</li>
                                            ))}
                                        </ul>
                                    )}
                                    {r.warnings.map((w) => (
                                        <div key={w} className="row-warning">
                                            {w}
                                        </div>
                                    ))}
                                </td>
                            </tr>
                        ))}
                        {rows.length === 0 && (
                            <tr>
                                <td colSpan={8} className="muted center">
                                    Every row is ready.
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </section>
    )
}

export default function BulkCalling() {
    const { me } = useOutletContext()
    const [error, setError] = useState(null)
    const [dragging, setDragging] = useState(false)
    const dispatch = useAppDispatch()
    const preview = useAppSelector(selectCsvFiles)[0] ?? null // { fileName, uploadedAt, result }
    const [upload, { isLoading }] = usePreviewBulkCsvMutation()

    const handle = async (file) => {
        if (!file) return
        setError(null)
        const problem = checkFile(file)
        if (problem) return setError(problem)
        try {
            const result = await upload({ uid: me.uid, file }).unwrap()
            dispatch(csvUploaded({ fileName: file.name, uploadedAt: new Date().toISOString(), result }))
        } catch (err) {
            setError(errorMessage(err, 'Could not read the file.'))
        }
    }
    const clear = () => {
        dispatch(csvCleared())
        setError(null)
    }

    return (
        <div className="page-column">
            <div className="page-top">
                <h1 className="page-title">Bulk Calling</h1>
            </div>
            <div className="page-body bulk-body">
                {!preview && (
                    <>
                        <p className="lead">
                            Upload a CSV file with one person per row. Each row is checked and shown below
                            before anything happens; nothing is called yet.
                        </p>
                        <label
                            className={`file-drop ${dragging ? 'dragging' : ''} ${isLoading ? 'busy' : ''}`}
                            onDragOver={(e) => {
                                e.preventDefault()
                                setDragging(true)
                            }}
                            onDragLeave={() => setDragging(false)}
                            onDrop={(e) => {
                                e.preventDefault()
                                setDragging(false)
                                void handle(e.dataTransfer.files?.[0])
                            }}
                        >
                            <svg viewBox="0 0 24 24" width="32" height="32" aria-hidden>
                                <path
                                    d="M12 16V4m0 0-4 4m4-4 4 4M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"
                                    fill="none"
                                    stroke="currentColor"
                                    strokeWidth="1.6"
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                />
                            </svg>
                            <span className="file-drop-title">
                                {isLoading ? 'Checking the file…' : 'Choose a CSV file or drop it here'}
                            </span>
                            <span className="muted">.csv, up to 1 MB and 1,000 rows</span>
                            <input
                                type="file"
                                accept=".csv,text/csv"
                                aria-label="CSV file of people to call"
                                disabled={isLoading}
                                onChange={(e) => {
                                    const f = e.target.files?.[0]
                                    e.target.value = ''
                                    void handle(f)
                                }}
                            />
                        </label>
                        {error && (
                            <div className="banner error" role="alert">
                                {error}
                            </div>
                        )}
                        <section className="bulk-format" aria-labelledby="bulk-format-title">
                            <div className="bulk-format-head">
                                <h2 id="bulk-format-title">File format</h2>
                                <button type="button" onClick={downloadSample}>
                                    Download sample CSV
                                </button>
                            </div>
                            <p className="muted">
                                The first row names the columns. Common spellings are recognised too (for
                                example “Mobile Number”, “Due Date”, “Bank”).
                            </p>
                            <table className="bulk-table format-table">
                                <thead>
                                    <tr>
                                        <th scope="col">Column</th>
                                        <th scope="col">What it holds</th>
                                        <th scope="col" />
                                    </tr>
                                </thead>
                                <tbody>
                                    {COLUMNS.map((c) => (
                                        <tr key={c.name}>
                                            <td className="mono">{c.name}</td>
                                            <td>{c.note}</td>
                                            <td className="muted">{c.required ? 'Required' : 'Optional'}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </section>
                    </>
                )}
                {preview && (
                    <PreviewTable result={preview.result} fileName={preview.fileName} onClear={clear} />
                )}
            </div>
        </div>
    )
}

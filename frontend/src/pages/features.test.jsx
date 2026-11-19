import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Provider } from 'react-redux'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { makeStore } from '../app/store'
import { routes } from '../app/router'
import { checkFile } from './BulkCalling'

vi.mock('./Landing', () => ({ default: () => <div /> }))

const ME = { uid: 'u1', username: 'Ann', email: 'ann@example.com', avatar_url: null, agent_count: 0 }
const json = (b, status = 200) =>
    new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } })
const AGENT = {
    aid: 'a1',
    name: 'Ava',
    role: 'Loan-Recovery Agent',
    status: 'free',
    system_prompt: 'You are Ava, a Loan-Recovery Agent.\n# Conduct',
    created_at: '2026-11-18T10:00:00Z',
}

/** A fake backend keyed by "METHOD /path"; unknown -> 404. Returns the list of requests seen. */
function mockApi(handlers) {
    const seen = []
    vi.stubGlobal(
        'fetch',
        vi.fn(async (req) => {
            const u = new URL(req.url)
            const key = `${req.method} ${u.pathname.replace('/api/v1', '')}`
            seen.push({ key, req })
            const h = handlers[key]
            return h ? h(req, u) : json({ error: { message: 'nope' } }, 404)
        }),
    )
    return seen
}
const base = { 'GET /auth/me': () => json(ME) }
function renderAt(path) {
    const router = createMemoryRouter(routes, { initialEntries: [path] })
    render(
        <Provider store={makeStore()}>
            <RouterProvider router={router} />
        </Provider>,
    )
    return router
}
afterEach(() => vi.unstubAllGlobals())

/** An in-memory agent backend: GET / POST / PUT / DELETE on /users/u1/agent. */
function agentBackend(initial = null, extra = {}) {
    let agent = initial
    const seen = mockApi({
        ...base,
        'GET /users/u1/agent': () => json(agent),
        'POST /users/u1/agent': async (req) => {
            agent = { ...AGENT, name: (await req.json()).name }
            return json(agent, 201)
        },
        'PUT /users/u1/agent': async (req) => {
            agent = { ...agent, name: (await req.json()).name }
            return json(agent)
        },
        'DELETE /users/u1/agent': () => {
            agent = null
            return new Response(null, { status: 204 })
        },
        ...extra,
    })
    return seen
}

describe('your agent: no agent yet (state A)', () => {
    it('shows the empty "+" slot and a "+ Create Agent" button', async () => {
        agentBackend()
        renderAt('/agent/u1')
        expect(await screen.findByRole('img', { name: 'No agent yet' })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: '+ Create Agent' })).toBeInTheDocument()
    })

    it('Cancel closes the pop-up and creates nothing', async () => {
        const seen = agentBackend()
        renderAt('/agent/u1')
        await userEvent.click(await screen.findByRole('button', { name: '+ Create Agent' }))
        const dialog = screen.getByRole('dialog')
        expect(within(dialog).getByLabelText('Name')).toHaveFocus()
        await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
        expect(screen.queryByRole('dialog')).toBeNull()
        expect(screen.getByRole('button', { name: '+ Create Agent' })).toBeInTheDocument()
        expect(seen.some((c) => c.key === 'POST /users/u1/agent')).toBe(false)
    })

    it('Create makes the agent: the tile shows the name and "Free", and the create button is gone', async () => {
        const seen = agentBackend()
        renderAt('/agent/u1')
        await userEvent.click(await screen.findByRole('button', { name: '+ Create Agent' }))
        const dialog = screen.getByRole('dialog')
        expect(within(dialog).getByRole('button', { name: 'Create' })).toBeDisabled() // empty name
        await userEvent.type(within(dialog).getByLabelText('Name'), '  Ava ')
        await userEvent.click(within(dialog).getByRole('button', { name: 'Create' }))
        const tile = await screen.findByRole('button', { name: /^Ava, Free/ })
        expect(screen.queryByRole('dialog')).toBeNull()
        expect(within(tile).getByText('Ava')).toBeInTheDocument()
        expect(within(tile).getByText('Free')).toHaveClass('agent-tile-status', 'free')
        expect(tile.querySelector('.status-dot.free')).not.toBeNull()
        expect(screen.queryByRole('button', { name: '+ Create Agent' })).toBeNull()
        expect(seen.filter((c) => c.key === 'POST /users/u1/agent')).toHaveLength(1) // the name was sent trimmed
    })

    it('shows the server error inside the pop-up', async () => {
        agentBackend(null, {
            'POST /users/u1/agent': () => json({ error: { message: 'You already have an agent.' } }, 409),
        })
        renderAt('/agent/u1')
        await userEvent.click(await screen.findByRole('button', { name: '+ Create Agent' }))
        await userEvent.type(screen.getByLabelText('Name'), 'Ava')
        await userEvent.click(screen.getByRole('button', { name: 'Create' }))
        expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveTextContent(
            'already have an agent',
        )
    })
})

describe('your agent: the agent tile and details', () => {
    it('a busy agent shows a red dot and "In-Call"', async () => {
        agentBackend({ ...AGENT, status: 'busy' })
        renderAt('/agent/u1')
        const tile = await screen.findByRole('button', { name: /^Ava, In-Call/ })
        expect(within(tile).getByText('In-Call')).toHaveClass('busy')
        expect(tile.querySelector('.status-dot.busy')).not.toBeNull()
    })

    it('clicking the tile replaces it with the details: name, system prompt, rename and delete', async () => {
        agentBackend(AGENT)
        const router = renderAt('/agent/u1')
        await userEvent.click(await screen.findByRole('button', { name: /^Ava, Free/ }))
        expect(screen.queryByRole('button', { name: /^Ava, Free/ })).toBeNull()
        expect(screen.getByRole('heading', { name: 'Ava' })).toBeInTheDocument()
        expect(screen.getByLabelText('System prompt')).toHaveTextContent(
            'You are Ava, a Loan-Recovery Agent.',
        )
        expect(screen.getByRole('button', { name: 'Rename Agent' })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Delete Agent' })).toBeInTheDocument()
        expect(router.state.location.search).toBe('?view=details')
        await userEvent.click(screen.getByRole('button', { name: /back/i }))
        expect(await screen.findByRole('button', { name: /^Ava, Free/ })).toBeInTheDocument()
    })

    it('Rename: Cancel changes nothing; Rename saves the new name', async () => {
        const seen = agentBackend(AGENT)
        renderAt('/agent/u1?view=details')
        await userEvent.click(await screen.findByRole('button', { name: 'Rename Agent' }))
        let dialog = screen.getByRole('dialog')
        const input = within(dialog).getByLabelText('New Name')
        expect(input).toHaveValue('Ava')
        expect(within(dialog).getByRole('button', { name: 'Rename' })).toBeDisabled() // unchanged
        await userEvent.click(within(dialog).getByRole('button', { name: 'Cancel' }))
        expect(screen.queryByRole('dialog')).toBeNull()
        expect(seen.some((c) => c.key === 'PUT /users/u1/agent')).toBe(false)

        await userEvent.click(screen.getByRole('button', { name: 'Rename Agent' }))
        dialog = screen.getByRole('dialog')
        await userEvent.clear(within(dialog).getByLabelText('New Name'))
        await userEvent.type(within(dialog).getByLabelText('New Name'), 'Maya')
        await userEvent.click(within(dialog).getByRole('button', { name: 'Rename' }))
        expect(await screen.findByRole('heading', { name: 'Maya' })).toBeInTheDocument()
        expect(screen.queryByRole('dialog')).toBeNull()
    })

    it('Delete asks first; Cancel keeps the agent, "Yes" deletes it and returns to state A', async () => {
        const seen = agentBackend(AGENT)
        renderAt('/agent/u1?view=details')
        await userEvent.click(await screen.findByRole('button', { name: 'Delete Agent' }))
        expect(
            screen.getByRole('dialog', { name: 'Are you sure you want to delete the agent?' }),
        ).toBeInTheDocument()
        await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))
        expect(screen.queryByRole('dialog')).toBeNull()
        expect(seen.some((c) => c.key === 'DELETE /users/u1/agent')).toBe(false)

        await userEvent.click(screen.getByRole('button', { name: 'Delete Agent' }))
        await userEvent.click(screen.getByRole('button', { name: 'Yes, delete the agent' }))
        expect(await screen.findByRole('button', { name: '+ Create Agent' })).toBeInTheDocument()
        expect(screen.queryByRole('dialog')).toBeNull()
    })

    it('Escape closes a pop-up', async () => {
        agentBackend(AGENT)
        renderAt('/agent/u1?view=details')
        await userEvent.click(await screen.findByRole('button', { name: 'Rename Agent' }))
        await userEvent.keyboard('{Escape}')
        expect(screen.queryByRole('dialog')).toBeNull()
    })
})

describe('bulk calling', () => {
    const csv = (text, name = 'people.csv') => new File([text], name, { type: 'text/csv' })
    const RESULT = {
        total: 2,
        valid: 1,
        invalid: 1,
        columns: { name: 'name', phone: 'phone', amount: 'amount_due', deadline: 'deadline' },
        ignored_columns: ['extra'],
        rows: [
            {
                line: 2,
                name: 'Ravi Kumar',
                phone: '+919876543210',
                amount: '5200.50',
                currency: 'INR',
                deadline: '2026-12-05',
                lender: 'Sunrise Bank',
                loan_reference: 'LN-1',
                notes: '',
                valid: true,
                errors: [],
                warnings: [],
            },
            {
                line: 3,
                name: 'Bad Row',
                phone: '12345',
                amount: '-3',
                currency: 'INR',
                deadline: '',
                lender: '',
                loan_reference: '',
                notes: '',
                valid: false,
                errors: ['Deadline is missing', 'Phone: enter a valid phone number'],
                warnings: [],
            },
        ],
    }

    it('checks the file type and size before uploading', () => {
        expect(checkFile(csv('a', 'people.xlsx'))).toMatch(/\.csv/)
        expect(checkFile(csv(''))).toMatch(/empty/)
        expect(checkFile(csv('x'.repeat(1024 * 1024 + 1)))).toMatch(/1 MB/)
        expect(checkFile(csv('name\n'))).toBeNull()
    })

    it('uploads the CSV and previews every row with its errors', async () => {
        const seen = mockApi({ ...base, 'POST /users/u1/bulk-calls/preview': () => json(RESULT) })
        renderAt('/bulk-calling/u1')
        expect(await screen.findByRole('heading', { name: 'Bulk Calling' })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Download sample CSV' })).toBeInTheDocument()
        await userEvent.upload(screen.getByLabelText('CSV file of people to call'), csv('name,phone\n'))
        const table = await screen.findByRole('region', { name: 'Borrowers in the file' })
        expect(within(table).getByText('Ravi Kumar')).toBeInTheDocument()
        expect(within(table).getByText('Ready')).toBeInTheDocument()
        expect(within(table).getByText('Deadline is missing')).toBeInTheDocument()
        expect(screen.getByText('Ignored column(s): extra')).toBeInTheDocument()
        const post = seen.find((c) => c.key === 'POST /users/u1/bulk-calls/preview').req
        expect(post.headers.get('content-type')).toBe('text/csv')
        await userEvent.click(screen.getByLabelText('Show only rows that need attention'))
        expect(within(table).queryByText('Ravi Kumar')).toBeNull()
        await userEvent.click(screen.getByRole('button', { name: 'Choose another file' }))
        expect(screen.getByLabelText('CSV file of people to call')).toBeInTheDocument()
    })

    it('shows a file-level error from the server and a client-side error for non-CSV files', async () => {
        mockApi({
            ...base,
            'POST /users/u1/bulk-calls/preview': () =>
                json({ error: { message: 'Missing required column(s): Deadline.' } }, 422),
        })
        renderAt('/bulk-calling/u1')
        const input = await screen.findByLabelText('CSV file of people to call')
        await userEvent.upload(input, csv('name\n'))
        expect(await screen.findByRole('alert')).toHaveTextContent('Missing required column(s): Deadline.')
        await userEvent.upload(input, new File(['x'], 'people.txt', { type: 'text/csv' }), {
            applyAccept: false,
        })
        await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Please choose a .csv file.'))
    })
})

describe('profile screen time', () => {
    it('shows the daily average from the server data', async () => {
        mockApi({
            ...base,
            'GET /users/u1/screen-time': () =>
                json({
                    week_start: '2026-10-19',
                    today: '2026-10-20',
                    days: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((w, i) => ({
                        date: `2026-10-${19 + i}`,
                        weekday: w,
                        hours: i === 0 ? 1 : i === 1 ? 2 : 0,
                    })),
                }),
        })
        renderAt('/profile/u1')
        expect(await screen.findByText('1h 30m')).toBeInTheDocument() // (1h + 2h) / 2 elapsed days
        expect(screen.getByRole('img', { name: /hours in the app/i })).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'Next week' })).toBeDisabled()
    })
})

describe('settings', () => {
    afterEach(() => {
        localStorage.clear()
        document.documentElement.removeAttribute('style')
    })
    it('changes accent colour, font size and font, and keeps the theme switch', async () => {
        mockApi(base)
        renderAt('/settings/u1')
        await userEvent.click(await screen.findByRole('button', { name: '#4f8cff' }))
        expect(document.documentElement.style.getPropertyValue('--brand')).toBe('#4f8cff')
        await userEvent.click(screen.getByRole('radio', { name: 'Large' }))
        expect(document.documentElement.style.fontSize).toBe('18px')
        await userEvent.selectOptions(screen.getByLabelText('Font'), 'open-sans')
        expect(document.documentElement.style.getPropertyValue('--font-sans')).toContain('Open Sans Variable')
        expect(screen.getByRole('switch', { name: 'Theme' })).toBeInTheDocument()
        expect(screen.queryByRole('option', { name: /dyslexic|anthropic/i })).toBeNull()
    })
})

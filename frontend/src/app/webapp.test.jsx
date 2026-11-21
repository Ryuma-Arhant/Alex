import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Provider } from 'react-redux'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { makeStore } from './store'
import { routes } from './router'

vi.mock('../pages/Landing', () => ({ default: () => <div data-testid="landing" /> }))

const ME = { uid: 'u1', username: 'Ann', email: 'ann@example.com', avatar_url: null, agent_count: 1 }
const json = (b, status = 200) =>
    new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } })

/** Routes a fake backend by "METHOD /path"; unknown -> 404. */
function mockApi(handlers) {
    const calls = []
    vi.stubGlobal(
        'fetch',
        vi.fn(async (req) => {
            const path = new URL(req.url).pathname.replace('/api/v1', '')
            const key = `${req.method} ${path}`
            calls.push({ key, req })
            const h = handlers[key]
            return h ? h(req) : json({ error: { message: 'nope' } }, 404)
        }),
    )
    return calls
}

function renderAt(path) {
    const router = createMemoryRouter(routes, { initialEntries: [path] })
    render(
        <Provider store={makeStore()}>
            <RouterProvider router={router} />
        </Provider>,
    )
    return router
}

const signedIn = { 'GET /auth/me': () => json(ME) }
const signedOut = { 'GET /auth/me': () => json({ error: { message: 'Not authenticated' } }, 401) }

afterEach(() => vi.unstubAllGlobals())

describe('route guard', () => {
    it('/home shows the landing page even when signed in (its nav offers "Open app")', async () => {
        mockApi({ ...signedIn })
        const router = renderAt('/home')
        expect(await screen.findByTestId('landing')).toBeInTheDocument()
        expect(router.state.location.pathname).toBe('/home')
    })

    it('/home without a valid token shows the landing page', async () => {
        mockApi({ ...signedOut, 'GET /auth/config': () => json({ google: false }) })
        const router = renderAt('/home')
        expect(await screen.findByTestId('landing')).toBeInTheDocument()
        expect(router.state.location.pathname).toBe('/home')
    })

    it('a protected page without a token goes to /checkin', async () => {
        mockApi({ ...signedOut, 'GET /auth/config': () => json({ google: false }) })
        const router = renderAt('/agent/u1')
        await waitFor(() => expect(router.state.location.pathname).toBe('/checkin'))
    })

    it("someone else's uid in the URL is sent to your own dashboard", async () => {
        mockApi(signedIn)
        const router = renderAt('/profile/other-user')
        await waitFor(() => expect(router.state.location.pathname).toBe('/dashboard/u1'))
    })
})

const DAYS = ['Thu', 'Fri', 'Sat', 'Sun', 'Mon', 'Tue', 'Wed'].map((w, i) => ({
    date: `2026-11-${String(12 + i).padStart(2, '0')}`,
    weekday: w,
    calls: [0, 2, 0, 1, 0, 3, 4][i],
}))
const callsPerDay = () => json({ tz: 'UTC', today: '2026-11-18', days: DAYS })
const AGENT = {
    aid: 'a1',
    name: 'Maya',
    role: 'Loan-Recovery Agent',
    voice: 'female',
    status: 'free',
    system_prompt: 'You are Maya.',
    created_at: '2026-11-18T10:00:00Z',
}
const DASHBOARD = {
    tz: 'UTC',
    today: '2026-11-18',
    calls_today: 0,
    promises: { promised: 0, of: 0 },
    reply_seconds: null,
    replies: 0,
    need_person: 0,
    recent_calls: [],
    next_actions: [],
}

describe('shared navbar', () => {
    it.each(['dashboard', 'agent', 'bulk-calling', 'profile', 'settings'])(
        '%s page has the same navbar: five links in order, "Calls" not available yet',
        async (page) => {
            mockApi({
                ...signedIn,
                'GET /users/u1/agent': () => json(null),
                'GET /users/u1/stats/calls-per-day': callsPerDay,
                'GET /users/u1/dashboard': () => json(DASHBOARD),
            })
            renderAt(`/${page}/u1`)
            const nav = await screen.findByRole('navigation', { name: 'Main' })
            const links = within(nav).getAllByRole('link')
            expect(links.map((a) => a.querySelector('span').textContent)).toEqual([
                'Dashboard',
                'Your agent',
                'Bulk calling',
                'Profile',
                'Settings',
            ])
            expect(links.map((a) => a.getAttribute('href'))).toEqual([
                '/dashboard/u1',
                '/agent/u1',
                '/bulk-calling/u1',
                '/profile/u1',
                '/settings/u1',
            ])
            expect(links.find((a) => a.getAttribute('href') === `/${page}/u1`)).toHaveAttribute(
                'aria-current',
                'page',
            )
            const calls = within(nav).getByText('Calls').closest('.nav-link')
            expect(calls.tagName).toBe('SPAN')
            expect(calls).toHaveAttribute('aria-disabled', 'true')
            expect(calls).toHaveTextContent('Soon')
            expect(within(nav).getByText('Alex')).toBeInTheDocument()
            expect(await within(nav).findByText('No agent yet')).toBeInTheDocument()
        },
    )

    it("the card at the bottom shows the agent's name and whether it is on a call", async () => {
        mockApi({
            ...signedIn,
            'GET /users/u1/agent': () => json({ ...AGENT, status: 'busy' }),
        })
        renderAt('/settings/u1')
        const nav = await screen.findByRole('navigation', { name: 'Main' })
        expect(await within(nav).findByText('Maya')).toBeInTheDocument()
        expect(within(nav).getByText('In a call')).toBeInTheDocument()
    })

    it.each(['/agents/u1', '/manager/u1', '/create_agent/u1'])(
        'the removed page %s is gone',
        async (path) => {
            mockApi(signedIn)
            const router = renderAt(path)
            await waitFor(() => expect(router.state.location.pathname).toBe('/home'))
        },
    )
})

describe('dashboard', () => {
    const TODAY = new Date().toISOString()
    const FULL = {
        ...DASHBOARD,
        calls_today: 4,
        promises: { promised: 1, of: 3 },
        reply_seconds: 2.6,
        replies: 9,
        need_person: 1,
        recent_calls: [
            {
                call_id: 'c1',
                at: TODAY,
                phone_last4: '5678',
                amount: '12000.00',
                currency: 'INR',
                status: 'done',
                outcome: 'completed',
                promise_to_pay: true,
                escalation_needed: false,
                sentiment: 'calm',
                length_seconds: 190,
            },
            {
                call_id: 'c2',
                at: TODAY,
                phone_last4: null,
                amount: null,
                currency: null,
                status: 'done',
                outcome: 'escalated',
                promise_to_pay: false,
                escalation_needed: true,
                sentiment: 'unknown',
                length_seconds: 62,
            },
        ],
        next_actions: [
            {
                call_id: 'c1',
                index: 0,
                action: 'Send the UPI link',
                owner: 'agent',
                due: null,
                done: false,
                at: TODAY,
            },
            {
                call_id: 'c1',
                index: 1,
                action: 'Pay 6,000',
                owner: 'caller',
                due: 'Friday',
                done: true,
                at: TODAY,
            },
        ],
    }
    const dashboardApi = (data = FULL, extra = {}) =>
        mockApi({
            ...signedIn,
            'GET /users/u1/agent': () => json(AGENT),
            'GET /users/u1/stats/calls-per-day': callsPerDay,
            'GET /users/u1/dashboard': () => json(data),
            ...extra,
        })

    it('greets the user by time of day with the date; the profile button opens the profile page', async () => {
        dashboardApi()
        const router = renderAt('/dashboard/u1')
        const h1 = await screen.findByRole('heading', { level: 1 })
        expect(h1).toHaveTextContent(/^Good (morning|afternoon|evening), Ann$/)
        const search = screen.getByRole('button', { name: 'Search (coming soon)' })
        expect(search).toBeDisabled()
        expect(search).toHaveTextContent('Soon')
        expect(screen.queryByRole('link', { name: /return to call/i })).toBeNull() // no call is live
        const profile = screen.getByRole('button', { name: /open your profile/i })
        expect(profile).toHaveTextContent('A') // initials when there is no picture
        await userEvent.click(profile)
        expect(router.state.location.pathname).toBe('/profile/u1')
    })

    it('the four figures come from the server: calls today vs yesterday, promise rate, reply time, need a person', async () => {
        const calls = dashboardApi()
        renderAt('/dashboard/u1')
        const card = async (name) => screen.findByRole('region', { name })
        expect(await card('Calls today')).toHaveTextContent('4+1 vs yesterday') // Tue 3 -> Wed 4
        expect(await card('Promise-to-pay rate')).toHaveTextContent('33%1 of 3 calls')
        expect(await card('Avg reply time')).toHaveTextContent('2.6 sTarget under 2 s')
        expect(await card('Need a person')).toHaveTextContent('1Review now')
        const req = calls.find((c) => c.key === 'GET /users/u1/dashboard').req
        expect(new URL(req.url).searchParams.get('tz')).toBeTruthy()
    })

    it('with no data yet the figures say so instead of showing made-up numbers', async () => {
        dashboardApi({ ...DASHBOARD })
        renderAt('/dashboard/u1')
        expect(await screen.findByRole('region', { name: 'Promise-to-pay rate' })).toHaveTextContent(
            '—No summarised calls today',
        )
        expect(screen.getByRole('region', { name: 'Avg reply time' })).toHaveTextContent('—No replies today')
        expect(screen.getByRole('region', { name: 'Need a person' })).toHaveTextContent('0All clear')
        expect(screen.getByText(/No calls yet/)).toBeInTheDocument()
        expect(screen.getByText("No next actions from today's calls yet.")).toBeInTheDocument()
    })

    it('shows the last seven days as bars, today highlighted', async () => {
        dashboardApi()
        renderAt('/dashboard/u1')
        const chart = await screen.findByRole('img', { name: /calls per day, last 7 days/i })
        expect(chart).toHaveAccessibleName(
            expect.stringContaining('Thu 0, Fri 2, Sat 0, Sun 1, Mon 0, Tue 3, Wed 4'),
        )
        expect(screen.getByText('10 calls · busiest on Wednesday')).toBeInTheDocument()
        expect(chart.querySelectorAll('rect.dash-bar')).toHaveLength(4) // zero days have no bar
        expect(chart.querySelectorAll('rect.dash-bar.today')).toHaveLength(1)
    })

    it('lists recent calls with masked phone, amount, outcome, mood and length', async () => {
        dashboardApi()
        renderAt('/dashboard/u1')
        const table = await screen.findByRole('table')
        const rows = within(table).getAllByRole('row').slice(1)
        expect(rows[0]).toHaveTextContent('•••• 5678')
        expect(rows[0]).toHaveTextContent('12,000')
        expect(rows[0]).toHaveTextContent('Promise to pay')
        expect(rows[0]).toHaveTextContent('Calm')
        expect(rows[0]).toHaveTextContent('3:10')
        expect(rows[1]).toHaveTextContent('Escalate')
        expect(rows[1]).toHaveTextContent('—') // no stored phone / mood unknown
        expect(screen.getByText('View all').closest('[aria-disabled]')).toHaveAttribute(
            'aria-disabled',
            'true',
        )
    })

    it('next actions can be ticked off; the tick is saved on the server', async () => {
        let body = null
        const calls = dashboardApi(FULL, {
            'PUT /users/u1/dashboard/next-actions/c1/0': async (req) => {
                body = await req.json()
                return json({ done: true })
            },
        })
        renderAt('/dashboard/u1')
        const box = await screen.findByRole('checkbox', { name: 'Send the UPI link' })
        expect(box).not.toBeChecked()
        const actions = screen.getByRole('region', { name: 'Next actions' })
        expect(within(actions).getByText('Maya')).toBeInTheDocument() // "agent" shown as the agent's name
        expect(screen.getByRole('checkbox', { name: 'Pay 6,000' })).toBeChecked()
        expect(screen.getByText('Borrower · done')).toBeInTheDocument()
        await userEvent.click(box)
        await waitFor(() => expect(box).toBeChecked())
        expect(body).toEqual({ done: true })
        expect(calls.some((c) => c.key === 'PUT /users/u1/dashboard/next-actions/c1/0')).toBe(true)
    })

    it('a refused tick is rolled back and explained', async () => {
        dashboardApi(FULL, {
            'PUT /users/u1/dashboard/next-actions/c1/0': () =>
                json({ error: { message: 'Next action not found' } }, 404),
        })
        renderAt('/dashboard/u1')
        const box = await screen.findByRole('checkbox', { name: 'Send the UPI link' })
        await userEvent.click(box)
        expect(await screen.findByRole('alert')).toHaveTextContent('Next action not found')
        expect(box).not.toBeChecked()
    })

    it('"Start a call" opens the Individual Call pop-up; without an agent it leads to creating one', async () => {
        dashboardApi()
        renderAt('/dashboard/u1')
        expect(await screen.findByText('Maya is ready.')).toBeInTheDocument()
        await userEvent.click(screen.getByRole('button', { name: 'New individual call' }))
        const dialog = screen.getByRole('dialog', { name: 'Individual Call' })
        expect(within(dialog).getByText('The agent will speak in its female voice.')).toBeInTheDocument()
    })

    it('without an agent, "Start a call" links to creating one', async () => {
        mockApi({
            ...signedIn,
            'GET /users/u1/agent': () => json(null),
            'GET /users/u1/stats/calls-per-day': callsPerDay,
            'GET /users/u1/dashboard': () => json(DASHBOARD),
        })
        renderAt('/dashboard/u1')
        expect(await screen.findByRole('link', { name: 'Create your agent' })).toHaveAttribute(
            'href',
            '/agent/u1',
        )
    })
})

describe('profile, settings, checkin', () => {
    it('profile page shows the details and logout goes to /checkin', async () => {
        let authed = true
        mockApi({
            'GET /auth/me': () => (authed ? json(ME) : json({ error: { message: 'no' } }, 401)),
            'POST /auth/logout': () => {
                authed = false
                return json({ status: 'logged_out' })
            },
            'GET /auth/config': () => json({ google: true }),
        })
        const router = renderAt('/profile/u1')
        expect(await screen.findByText('ann@example.com')).toBeInTheDocument()
        expect(screen.getByText('Ann')).toBeInTheDocument()
        expect(screen.getByLabelText('Upload profile picture')).toBeInTheDocument()
        await userEvent.click(screen.getByRole('button', { name: 'Log out' }))
        await waitFor(() => expect(router.state.location.pathname).toBe('/checkin'))
    })

    it('settings toggles the theme', async () => {
        mockApi(signedIn)
        renderAt('/settings/u1')
        const toggle = await screen.findByRole('switch', { name: 'Theme' })
        const before = toggle.getAttribute('aria-checked')
        await userEvent.click(toggle)
        expect(toggle.getAttribute('aria-checked')).not.toBe(before)
        expect(document.documentElement.dataset.theme).toBe(before === 'true' ? 'light' : 'dark')
    })

    it('checkin: email sign-in goes to the dashboard; Google is disabled when not configured', async () => {
        let authed = false
        mockApi({
            'GET /auth/me': () => (authed ? json(ME) : json({ error: { message: 'no' } }, 401)),
            'GET /auth/config': () => json({ google: false }),
            'POST /auth/login': () => {
                authed = true
                return json(ME)
            },
            'GET /users/u1/stats/calls-per-day': callsPerDay,
        })
        const router = renderAt('/checkin')
        expect(await screen.findByText('Continue with Google')).toHaveAttribute('aria-disabled', 'true')
        await userEvent.type(screen.getByLabelText('Email'), 'ann@example.com')
        await userEvent.type(screen.getByLabelText('Password'), 'correct-horse-1')
        await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
        await waitFor(() => expect(router.state.location.pathname).toBe('/dashboard/u1'))
    })

    it('checkin shows the server error for bad credentials', async () => {
        mockApi({
            ...signedOut,
            'GET /auth/config': () => json({ google: true }),
            'POST /auth/login': () => json({ error: { message: 'Incorrect email or password' } }, 401),
        })
        renderAt('/checkin')
        await userEvent.type(await screen.findByLabelText('Email'), 'a@b.co')
        await userEvent.type(screen.getByLabelText('Password'), 'wrongwrong')
        await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))
        expect(await screen.findByRole('alert')).toHaveTextContent('Incorrect email or password')
    })

    it('checkin stays on the sign-in form for a signed-in visitor, with a way back to the dashboard', async () => {
        mockApi({ ...signedIn, 'GET /auth/config': () => json({ google: false }) })
        const router = renderAt('/checkin')
        expect(await screen.findByLabelText('Email')).toBeInTheDocument()
        expect(await screen.findByRole('link', { name: /continue to your dashboard/i })).toHaveAttribute(
            'href',
            '/dashboard/u1',
        )
        expect(router.state.location.pathname).toBe('/checkin')
    })
})

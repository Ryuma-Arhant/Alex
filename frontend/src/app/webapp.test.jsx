import { render, screen, waitFor } from '@testing-library/react'
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

describe('shared navbar', () => {
    it.each(['dashboard', 'agent', 'bulk-calling', 'profile', 'settings'])(
        '%s page has the five links in order',
        async (page) => {
            mockApi({
                ...signedIn,
                'GET /users/u1/agent': () => json(null),
                'GET /users/u1/stats/calls-per-day': callsPerDay,
            })
            renderAt(`/${page}/u1`)
            const nav = await screen.findByRole('navigation', { name: 'Main' })
            const links = Array.from(nav.querySelectorAll('a'))
            expect(links.map((a) => a.textContent)).toEqual([
                'Dashboard',
                'Your Agent',
                'Bulk Calling',
                'My Profile',
                'Settings',
            ])
            expect(links.map((a) => a.getAttribute('href'))).toEqual([
                '/dashboard/u1',
                '/agent/u1',
                '/bulk-calling/u1',
                '/profile/u1',
                '/settings/u1',
            ])
        },
    )

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
    it('greets the user and the profile icon opens the profile page', async () => {
        mockApi({ ...signedIn, 'GET /users/u1/stats/calls-per-day': callsPerDay })
        const router = renderAt('/dashboard/u1')
        expect(await screen.findByText('Welcome back, Ann!')).toBeInTheDocument()
        await userEvent.click(await screen.findByRole('button', { name: /open your profile/i }))
        expect(router.state.location.pathname).toBe('/profile/u1')
    })

    it('shows one graph: calls per day for the last seven days, by weekday', async () => {
        const calls = mockApi({ ...signedIn, 'GET /users/u1/stats/calls-per-day': callsPerDay })
        renderAt('/dashboard/u1')
        const chart = await screen.findByRole('img', { name: /number of calls made by your agent per day/i })
        expect(chart).toHaveAccessibleName(
            expect.stringContaining('Thu 0, Fri 2, Sat 0, Sun 1, Mon 0, Tue 3, Wed 4'),
        )
        expect(screen.getAllByRole('img', { name: /calls/i })).toHaveLength(1)
        for (const w of ['Thu', 'Fri', 'Sat', 'Sun', 'Mon', 'Tue', 'Wed'])
            expect(screen.getByText(w)).toBeInTheDocument()
        expect(screen.getByText('Day of the week')).toBeInTheDocument()
        expect(screen.getByText('Number of calls')).toBeInTheDocument()
        expect(screen.getByText(/10 calls/)).toBeInTheDocument()
        expect(screen.queryByRole('combobox')).toBeNull() // no metric / period pickers any more
        const req = calls.find((c) => c.key === 'GET /users/u1/stats/calls-per-day').req
        expect(new URL(req.url).searchParams.get('tz')).toBeTruthy()
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

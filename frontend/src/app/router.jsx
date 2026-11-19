import { createBrowserRouter, Navigate } from 'react-router-dom'
import AppLayout from '../components/AppLayout/AppLayout'
import RequireAuth from '../components/Auth/RequireAuth'
import BulkCalling from '../pages/BulkCalling'
import CallPage from '../pages/CallPage'
import CheckinPage from '../pages/CheckinPage'
import Dashboard from '../pages/Dashboard'
import Landing from '../pages/Landing'
import ProfilePage from '../pages/ProfilePage'
import Settings from '../pages/Settings'
import YourAgent from '../pages/YourAgent'

export const routes = [
    { path: '/', element: <Navigate to="/home" replace /> },
    { path: '/home', element: <Landing /> },
    { path: '/checkin', element: <CheckinPage /> },
    {
        element: <RequireAuth />,
        children: [
            {
                element: <AppLayout />,
                children: [
                    { path: '/dashboard/:uid', element: <Dashboard /> },
                    { path: '/agent/:uid', element: <YourAgent /> },
                    { path: '/call/:uid', element: <CallPage /> },
                    { path: '/bulk-calling/:uid', element: <BulkCalling /> },
                    { path: '/profile/:uid', element: <ProfilePage /> },
                    { path: '/settings/:uid', element: <Settings /> },
                ],
            },
        ],
    },
    { path: '*', element: <Navigate to="/home" replace /> },
]

export const router = createBrowserRouter(routes)

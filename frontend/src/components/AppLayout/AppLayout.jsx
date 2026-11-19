import { Outlet, useOutletContext } from 'react-router-dom'
import { CallProvider } from '../../features/call/CallProvider'
import Navbar from '../Navbar/Navbar'

/** Left: the vertical navbar. Right: the page. Every main page is rendered inside this layout, and inside the one call
 * provider, so a call started from Your Agent keeps running on the Call Page and across pages. */
export default function AppLayout() {
    const ctx = useOutletContext()
    return (
        <CallProvider uid={ctx.me.uid}>
            <div className="app-layout">
                <Navbar uid={ctx.me.uid} />
                <div className="app-content">
                    <Outlet context={ctx} />
                </div>
            </div>
        </CallProvider>
    )
}

import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
export const CLOSE_MS = 160 // matches the modal-out animation in app.css

const animates = () => {
    try {
        return (
            typeof window.matchMedia === 'function' &&
            !window.matchMedia('(prefers-reduced-motion: reduce)').matches
        )
    } catch {
        return false
    }
}

const CloseCtx = createContext(null)
/** Inside a Modal: closes it with the exit animation (Cancel / Return buttons). */
export function useModalClose() {
    return useContext(CloseCtx)
}

/**
 * A dialog over a blurred backdrop. Closes with Escape or a click on the backdrop (unless `busy`); focus starts on
 * the first field (or button), is kept inside while open, and returns to the opener on close. It fades and scales in,
 * and out again when closed from inside (Escape, backdrop, or `useModalClose()`); with reduced motion it is instant.
 */
export default function Modal({ title, children, onClose, busy = false, className = '' }) {
    const dialogRef = useRef(null)
    const titleId = useId()
    const [closing, setClosing] = useState(false)
    const onCloseRef = useRef(onClose)
    onCloseRef.current = onClose
    const busyRef = useRef(busy)
    busyRef.current = busy
    const timer = useRef(null)

    const close = useCallback(() => {
        if (busyRef.current || timer.current) return
        if (!animates()) return onCloseRef.current()
        setClosing(true)
        timer.current = setTimeout(() => onCloseRef.current(), CLOSE_MS)
    }, [])
    const closeRef = useRef(close)
    closeRef.current = close

    useEffect(() => {
        const opener = document.activeElement
        const overflow = document.body.style.overflow
        document.body.style.overflow = 'hidden'
        const first =
            dialogRef.current?.querySelector('input, textarea, select') ??
            dialogRef.current?.querySelector(FOCUSABLE)
        first?.focus()
        const onKey = (e) => {
            if (e.key === 'Escape') return closeRef.current()
            if (e.key !== 'Tab') return
            const items = dialogRef.current?.querySelectorAll(FOCUSABLE)
            if (!items?.length) return
            const head = items[0]
            const tail = items[items.length - 1]
            if (e.shiftKey && document.activeElement === head) {
                e.preventDefault()
                tail.focus()
            } else if (!e.shiftKey && document.activeElement === tail) {
                e.preventDefault()
                head.focus()
            }
        }
        document.addEventListener('keydown', onKey)
        return () => {
            document.removeEventListener('keydown', onKey)
            document.body.style.overflow = overflow
            clearTimeout(timer.current)
            timer.current = null
            if (opener instanceof HTMLElement) opener.focus()
        }
    }, [])

    return createPortal(
        <div
            className={`modal-backdrop ${closing ? 'closing' : ''}`}
            onMouseDown={(e) => e.target === e.currentTarget && closeRef.current()}
        >
            <div
                ref={dialogRef}
                className={`box modal ${className} ${closing ? 'closing' : ''}`}
                role="dialog"
                aria-modal="true"
                aria-labelledby={titleId}
            >
                <h1 id={titleId}>{title}</h1>
                <CloseCtx.Provider value={close}>{children}</CloseCtx.Provider>
            </div>
        </div>,
        document.body,
    )
}

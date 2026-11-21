const ICONS = {
    check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
    clock: (
        <>
            <circle cx="12" cy="12" r="9" />
            <path d="M12 7v5l3 2" />
        </>
    ),
    warn: (
        <>
            <path d="M12 3 2 20h20L12 3z" />
            <path d="M12 10v4M12 17.5v.01" />
        </>
    ),
}

/** A small rounded status tag. tone: teal | amber | blue | red | neutral. */
export default function Pill({ tone = 'neutral', icon, children }) {
    return (
        <span className={`dash-pill ${tone}`}>
            {icon && (
                <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                >
                    {ICONS[icon]}
                </svg>
            )}
            {children}
        </span>
    )
}

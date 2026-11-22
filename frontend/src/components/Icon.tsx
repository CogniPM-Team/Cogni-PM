import type { IconName } from '../lib/nav'

// Simple line drawings on a 24 x 24 grid, drawn here so the app needs no icon library. They take their colour from the
// text around them, so the active and hover colours of a nav item colour its icon too.
export type IconKey =
  | IconName
  | 'chevron'
  | 'arrow'
  | 'back'
  | 'external'
  | 'file'
  | 'bookmark'
  | 'layers'
  | 'clock'
  | 'alert'
  | 'list'
  | 'branch'
  | 'download'
  | 'upload'
  | 'panel'
  | 'check'
  | 'info'
  | 'shield'

const DRAWINGS: Record<IconKey, React.ReactNode> = {
  home: (
    <>
      <path d="M3 11.5 12 4l9 7.5" />
      <path d="M5.5 10v10h4.5v-6h4v6h4.5V10" />
    </>
  ),
  console: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <path d="m7.5 9.5 3 2.5-3 2.5" />
      <path d="M13 15h3.5" />
    </>
  ),
  approvals: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m8 12.5 2.8 2.8L16.2 9.6" />
    </>
  ),
  library: (
    <>
      <rect x="4" y="4" width="4.5" height="16" rx="1" />
      <rect x="10.5" y="4" width="4.5" height="16" rx="1" />
      <path d="m17 6.7 3.2-.8 2.3 12.4-3.2.8z" />
    </>
  ),
  activity: <path d="M3 12h4l3-8 4 16 3-8h4" />,
  settings: (
    <>
      <path d="M4 7h9M19 7h1M4 17h1M11 17h9" />
      <circle cx="16" cy="7" r="2.5" />
      <circle cx="8" cy="17" r="2.5" />
    </>
  ),
  chevron: <path d="m15 6-6 6 6 6" />,
  file: (
    <>
      <path d="M7 3h7l4 4v14H7z" />
      <path d="M14 3v4h4M9.5 12h5M9.5 15.5h5" />
    </>
  ),
  download: <path d="M12 4v11m-4.5-4.5L12 15l4.5-4.5M5 20h14" />,
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5.5M12 7.5h.01" />
    </>
  ),
  insights: <path d="M5 20v-9M12 20V4M19 20v-6" />,
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  panel: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <path d="M9.5 4v16" />
    </>
  ),
  upload: <path d="M12 15V4m-4.5 4.5L12 4l4.5 4.5M5 20h14" />,
  shield: (
    <>
      <path d="m12 3 8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </>
  ),
  bookmark: <path d="M7 4h10v17l-5-3.5L7 21z" />,
  layers: (
    <>
      <path d="m12 3 9 5-9 5-9-5z" />
      <path d="m3 13 9 5 9-5" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  alert: (
    <>
      <path d="M12 4 3 19.5h18z" />
      <path d="M12 10v4.5M12 17.5h.01" />
    </>
  ),
  list: <path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" />,
  branch: (
    <>
      <circle cx="6" cy="5.5" r="2" />
      <circle cx="6" cy="18.5" r="2" />
      <circle cx="18" cy="9" r="2" />
      <path d="M6 7.5v9M18 11c0 3.5-2.5 4-6 4H8" />
    </>
  ),
  arrow: <path d="M5 12h14m-5.5-5.5L19 12l-5.5 5.5" />,
  back: <path d="M19 12H5m5.5-5.5L5 12l5.5 5.5" />,
  external: (
    <>
      <path d="M14 4h6v6" />
      <path d="M20 4 11 13" />
      <path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10" />
    </>
  ),
}

/** A decorative icon: the label next to it says what it is, so it is hidden from screen readers. */
export default function Icon({ name, size = 20 }: { name: IconKey; size?: number }) {
  return (
    <svg
      className="icon"
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {DRAWINGS[name]}
    </svg>
  )
}

// One small icon set, one stroke weight (1.75), drawn for Kukkaro. Decorative: aria-hidden.
import type { ReactNode } from "react";

type P = { size?: number };
const svg = (size: number, children: ReactNode) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75}
    strokeLinecap="round" strokeLinejoin="round" aria-hidden focusable="false">
    {children}
  </svg>
);

export const IconAsk = ({ size = 22 }: P) =>
  svg(size, <><path d="M5 18.5V7a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3v6a3 3 0 0 1-3 3H9l-4 2.5Z" /><path d="M9 9.5h6M9 12.5h3.5" /></>);

export const IconBaskets = ({ size = 22 }: P) =>
  svg(size, <><path d="M4 9h16l-1.4 9.1a2 2 0 0 1-2 1.9H7.4a2 2 0 0 1-2-1.9Z" /><path d="M8.5 9 11 4.5M15.5 9 13 4.5" /><path d="M9.5 13v3.5M14.5 13v3.5" /></>);

export const IconButler = ({ size = 22 }: P) =>
  svg(size, <><circle cx="11" cy="11" r="6" /><path d="m20 20-4.2-4.2" /><path d="M11 8.5v5M8.5 11h5" /></>);

export const IconSend = ({ size = 20 }: P) =>
  svg(size, <><path d="M5 12h13" /><path d="m13 6 6 6-6 6" /></>);

export const IconArrow = ({ size = 18 }: P) => svg(size, <path d="m9 6 6 6-6 6" />);

export const IconBack = ({ size = 18 }: P) => svg(size, <path d="m15 6-6 6 6 6" />);

export const IconReceipt = ({ size = 18 }: P) =>
  svg(size, <><path d="M6 3.5h12v17l-2-1.3-2 1.3-2-1.3-2 1.3-2-1.3-2 1.3Z" /><path d="M9 8h6M9 11.5h6M9 15h3.5" /></>);

export const IconSpark = ({ size = 18 }: P) =>
  svg(size, <><path d="M12 3.5 13.8 10l6.2 2-6.2 2L12 20.5 10.2 14 4 12l6.2-2Z" /></>);

export const IconCopy = ({ size = 18 }: P) =>
  svg(size, <><rect x="8" y="8" width="11" height="12" rx="2.5" /><path d="M16 8V6.5A2.5 2.5 0 0 0 13.5 4h-6A2.5 2.5 0 0 0 5 6.5v8A2.5 2.5 0 0 0 7.5 17H8" /></>);

export const IconMail = ({ size = 18 }: P) =>
  svg(size, <><rect x="3.5" y="5.5" width="17" height="13" rx="2.5" /><path d="m4.5 7 7.5 6 7.5-6" /></>);

export const IconExternal = ({ size = 16 }: P) =>
  svg(size, <><path d="M14 4h6v6M20 4l-9 9" /><path d="M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4" /></>);

export const IconShield = ({ size = 16 }: P) =>
  svg(size, <><path d="M12 3.5 19 6v5.5c0 4.3-3 7.6-7 9-4-1.4-7-4.7-7-9V6Z" /><path d="m9 12 2 2 4-4" /></>);

export const IconTrend = ({ size = 18 }: P) =>
  svg(size, <><path d="m4 16 5-5 3.5 3.5L20 7" /><path d="M15 7h5v5" /></>);

// A generic six-wheeled sidewalk delivery robot (our own drawing, no company's design or logo).
export const Robot = ({ size = 56 }: P) => (
  <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden focusable="false">
    <line x1="44" y1="14" x2="48" y2="4" stroke="var(--green-ink)" strokeWidth="2" strokeLinecap="round" />
    <path d="M48 4l7 2.5-6 3z" fill="var(--everyday)" />
    <rect x="10" y="14" width="44" height="30" rx="9" fill="#ffffff" stroke="var(--green-ink)" strokeWidth="2.5" />
    <rect x="10" y="30" width="44" height="6" fill="var(--mint)" />
    <rect x="16" y="19" width="16" height="7" rx="3.5" fill="var(--green-ink)" />
    <circle cx="20" cy="22.5" r="1.6" fill="var(--mint)" />
    <circle cx="28" cy="22.5" r="1.6" fill="var(--mint)" />
    <rect x="8" y="42" width="48" height="4" rx="2" fill="var(--green-ink)" />
    {[16, 32, 48].map((x) => (
      <g key={x}>
        <circle cx={x} cy="52" r="7" fill="var(--green-ink)" />
        <circle cx={x} cy="52" r="2.6" fill="#ffffff" />
      </g>
    ))}
  </svg>
);

export const IconHouse = ({ size = 22 }: P) =>
  svg(size, <><path d="M4 11 12 4.5 20 11" /><path d="M6 9.5V19a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V9.5" /><path d="M10 20v-5h4v5" /></>);

export const IconClose = ({ size = 20 }: P) => svg(size, <><path d="M6 6l12 12M18 6 6 18" /></>);

// The brand mark: a small coin purse ("kukkaro" is Finnish for purse).
// The unlocked lock that is the "A" of KUKKARO: the shackle uses the two-stripe line of S-Group's S symbol,
// and one leg is lifted out of the body. `simple` drops the keyhole slot for small sizes.
export const LockA = ({ fg = "currentColor", cut = "#ffffff", simple = false, width = "0.5em", height = "0.7em" }:
  { fg?: string; cut?: string; simple?: boolean; width?: string | number; height?: string | number }) => (
  <svg width={width} height={height} viewBox="0 0 60 84" aria-hidden focusable="false" style={{ flex: "none" }}>
    <path d="M12 52 V28 A18 18 0 0 1 48 28 V38" fill="none" stroke={fg} strokeWidth={simple ? 16 : 15} />
    <path d="M12 52 V28 A18 18 0 0 1 48 28 V38" fill="none" stroke={cut} strokeWidth={simple ? 5 : 4} />
    <rect x="0" y="46" width="60" height="38" rx="3" fill={fg} />
    {simple ? (
      <circle cx="30" cy="64" r="7" fill={cut} />
    ) : (
      <>
        <circle cx="30" cy="61" r="5.5" fill={cut} />
        <rect x="27.5" y="63" width="5" height="11" rx="1.5" fill={cut} />
      </>
    )}
  </svg>
);

// KUKK + lock + RO, in upright condensed capitals (Bebas Neue stands in for S-Group's own type).
export const Wordmark = () => (
  <span className="wordmark" role="img" aria-label="Kukkaro">
    <span aria-hidden>KUKK</span>
    <LockA fg="var(--green)" cut="var(--surface)" simple />
    <span aria-hidden>RO</span>
  </span>
);

// App icon / chat avatar: the lock on S-market green.
export const Mark = ({ size = 28 }: P) => (
  <span className="mark" style={{ width: size, height: size, borderRadius: size * 0.26 }} aria-hidden>
    <LockA fg="#ffffff" cut="var(--green)" simple width={size * 0.48} height={size * 0.67} />
  </span>
);

export const IconBell = ({ size = 18 }: P) =>
  svg(size, <><path d="M6.5 16.5V11a5.5 5.5 0 0 1 11 0v5.5l1.5 1.5H5Z" /><path d="M10 20.5a2 2 0 0 0 4 0" /></>);

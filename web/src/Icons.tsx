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

// The brand mark: a small coin purse ("kukkaro" is Finnish for purse).
export const Mark = ({ size = 28 }: P) => (
  <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden focusable="false">
    <rect width="64" height="64" rx="18" fill="var(--mark-bg)" />
    <path d="M20 26c0-6 5-10 12-10s12 4 12 10" fill="none" stroke="var(--mark-fg)" strokeWidth="4" strokeLinecap="round" />
    <rect x="14" y="26" width="36" height="24" rx="8" fill="var(--mark-fg)" />
    <circle cx="32" cy="38" r="4" fill="var(--mark-bg)" />
  </svg>
);

/** Inline SVG icons (stroke style, 24x24 grid), decorative: labels carry the meaning. */

import type { ReactNode } from "react";

export interface IconProps {
  width?: number;
  height?: number;
}

function Icon({ width = 18, height = 18, children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export const HomeIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 10.5 12 3l9 7.5" />
    <path d="M5 9.5V21h14V9.5" />
  </Icon>
);

export const TrendIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 17l6-6 4 4 8-8" />
    <path d="M15 7h6v6" />
  </Icon>
);

export const BriefcaseIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="3" y="7" width="18" height="13" rx="2" />
    <path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
    <path d="M3 13h18" />
  </Icon>
);

export const SearchIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </Icon>
);

export const PlusCircleIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8v8M8 12h8" />
  </Icon>
);

export const ListIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M8 6h13M8 12h13M8 18h13" />
    <path d="M3 6h.01M3 12h.01M3 18h.01" />
  </Icon>
);

export const SlidersIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3" />
    <path d="M1 14h6M9 8h6M17 16h6" />
  </Icon>
);

export const BankIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 10 12 4l9 6" />
    <path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8" />
    <path d="M3 21h18" />
  </Icon>
);

export const DatabaseIcon = (p: IconProps) => (
  <Icon {...p}>
    <ellipse cx="12" cy="5" rx="8" ry="3" />
    <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
    <path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
  </Icon>
);

export const MenuIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 6h18M3 12h18M3 18h18" />
  </Icon>
);

export const CloseIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M6 6l12 12M18 6 6 18" />
  </Icon>
);

export const LogoutIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <path d="M16 17l5-5-5-5M21 12H9" />
  </Icon>
);

export const MoonIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
  </Icon>
);

export const SunIcon = (p: IconProps) => (
  <Icon {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </Icon>
);

export const TrashIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
  </Icon>
);

export const EditIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
  </Icon>
);

export const EyeOffIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M3 3l18 18" />
    <path d="M10.6 5.1A10 10 0 0 1 12 5c5 0 9 4.5 10 7-0.4 1-1.2 2.3-2.4 3.5M6.6 6.6C4.4 8 2.9 10.2 2 12c1 2.5 5 7 10 7 1.8 0 3.4-.6 4.8-1.4" />
  </Icon>
);

export const BotIcon = (p: IconProps) => (
  <Icon {...p}>
    <rect x="4" y="8" width="16" height="12" rx="2" />
    <path d="M12 4v4M9 4h6" />
    <circle cx="9" cy="14" r="1" />
    <circle cx="15" cy="14" r="1" />
  </Icon>
);

export const ChevronDownIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m6 9 6 6 6-6" />
  </Icon>
);

export const ChevronRightIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="m9 18 6-6-6-6" />
  </Icon>
);

export const PlusIcon = (p: IconProps) => (
  <Icon {...p}>
    <path d="M12 5v14M5 12h14" />
  </Icon>
);


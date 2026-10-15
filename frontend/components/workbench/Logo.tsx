import React from "react";

/** Workbench mark: stacked work surfaces on a navy tile. */
export function Logo({ size = 30 }: { size?: number }) {
  return (
    <span className="logo" aria-hidden>
      <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
        <defs>
          <linearGradient id="wb-g" x1="3" y1="2" x2="29" y2="30" gradientUnits="userSpaceOnUse">
            <stop stopColor="#3d3f73" />
            <stop offset="1" stopColor="#6b6ea8" />
          </linearGradient>
        </defs>
        <rect width="32" height="32" rx="9" fill="url(#wb-g)" />
        <rect x="7" y="8" width="18" height="4.5" rx="2.25" fill="#fff" />
        <rect x="7" y="14.5" width="12" height="4.5" rx="2.25" fill="#fff" fillOpacity=".85" />
        <rect x="7" y="21" width="15" height="4.5" rx="2.25" fill="#fff" fillOpacity=".65" />
        <circle cx="24.5" cy="16.75" r="2.4" fill="#fff" />
      </svg>
    </span>
  );
}

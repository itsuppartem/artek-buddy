const icon = {
  width: 18,
  height: 18,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.5,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export function IconPlus() {
  return (
    <svg {...icon} aria-hidden="true">
      <path d="M12 6v12M6 12h12" />
    </svg>
  );
}

export function IconSearch() {
  return (
    <svg {...icon} aria-hidden="true">
      <circle cx="11" cy="11" r="6" />
      <path d="m16 16 3.5 3.5" />
    </svg>
  );
}

export function IconComputer() {
  return (
    <svg {...icon} aria-hidden="true">
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <path d="M8 20h8M12 16v4" />
    </svg>
  );
}

export function IconSettings() {
  return (
    <svg {...icon} aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 4.5v2M12 17.5v2M4.5 12h2M17.5 12h2M6.4 6.4l1.4 1.4M16.2 16.2l1.4 1.4M17.6 6.4l-1.4 1.4M7.8 16.2l-1.4 1.4" />
    </svg>
  );
}

export function IconSend() {
  return (
    <svg {...icon} aria-hidden="true">
      <path d="M5 12h12M13 7l5 5-5 5" />
    </svg>
  );
}

export function IconStop() {
  return (
    <svg {...icon} aria-hidden="true">
      <rect x="7" y="7" width="10" height="10" rx="1.5" />
    </svg>
  );
}

export function IconClose() {
  return (
    <svg {...icon} aria-hidden="true">
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}

export function IconPin() {
  return (
    <svg {...icon} aria-hidden="true">
      <path d="m15 4 5 5-4 2-3 5-2-2-5 5-1-1 5-5-2-2 5-3 2-4Z" />
    </svg>
  );
}

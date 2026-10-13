type NavigatorStandalone = Navigator & { standalone?: boolean }

/** True for iPhone/iPad/iPod, including iPadOS that reports as Mac. */
export function isIosDevice(
  nav: Pick<Navigator, 'userAgent' | 'platform' | 'maxTouchPoints'> = navigator,
): boolean {
  if (/iPad|iPhone|iPod/.test(nav.userAgent)) return true
  return nav.platform === 'MacIntel' && nav.maxTouchPoints > 1
}

/** True when running as an installed Home Screen / PWA window. */
export function isStandaloneDisplay(
  nav: NavigatorStandalone = navigator,
  media: Pick<MediaQueryList, 'matches'> | null = typeof matchMedia === 'function'
    ? matchMedia('(display-mode: standalone)')
    : null,
): boolean {
  if (nav.standalone === true) return true
  return media?.matches === true
}

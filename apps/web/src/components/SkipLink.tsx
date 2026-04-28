"use client";

import { useCallback } from "react";

/**
 * "Skip to main content" link.
 *
 * Visually hidden until it receives keyboard focus (first Tab on the page),
 * then pops into the top-left as a high-contrast pill. Pressing Enter
 * programmatically focuses the page's <main id="main"> element so the
 * keyboard cursor *actually* lands there — relying on the browser's default
 * `href="#main"` behaviour is unreliable across Chrome/Safari/Firefox.
 */
export function SkipLink() {
  const handleClick = useCallback((event: React.MouseEvent<HTMLAnchorElement>) => {
    event.preventDefault();
    const main = document.getElementById("main");
    if (!main) return;
    // Make the element programmatically focusable if it isn't already, then
    // focus it. tabIndex=-1 keeps it out of the natural tab order while still
    // accepting `.focus()` calls.
    if (!main.hasAttribute("tabindex")) {
      main.setAttribute("tabindex", "-1");
    }
    main.focus({ preventScroll: false });
    // Some screen readers need the URL hash to update too, so the page state
    // matches what we just announced.
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", "#main");
    }
  }, []);

  return (
    <a
      href="#main"
      onClick={handleClick}
      className="
        sr-only
        focus:not-sr-only
        focus:fixed focus:left-4 focus:top-4 focus:z-[100]
        focus:rounded-md focus:bg-brand-blue focus:px-4 focus:py-2
        focus:text-sm focus:font-medium focus:text-white
        focus:shadow-lg
        focus:ring-2 focus:ring-brand-yellow focus:ring-offset-2
      "
    >
      Skip to main content
    </a>
  );
}

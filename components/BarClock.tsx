"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

/// How long the direction above it has left, and a refresh the moment it expires.
///
/// **The problem this solves.** A direction is read from the last *closed* bar. On a five-minute
/// model that call is current for up to five minutes and then it is history -- and until now
/// nothing on the page said which of those you were looking at. The price ticked every two
/// seconds beside a verdict that might have been four minutes old, which is the worst version of
/// both: it looks live and it is not.
///
/// So the bar is counted down, and when it closes the route is refetched. A server-rendered page
/// cannot do that; the clock is the reason this is a client component.
///
/// The grace period is not decoration. A bar closes at `t`, and the venue needs a moment to make
/// that bar available -- asking at exactly `t` reliably gets the previous one back and burns a
/// render. Waiting a few seconds gets the bar that just closed.
///
/// Reaches no server value: no database module, no environment, and it makes no `fetch` of its
/// own -- `router.refresh()` is the framework re-rendering the route it is already on.

const GRACE_MS = 4000;

export function BarClock({
  /// The close time of the bar the forecast was read from, as epoch milliseconds.
  asOfMs,
  /// The bar interval in milliseconds, so a 5-minute lane and a 4-hour one both count correctly.
  stepMs,
  /// How far ahead this call reaches, in minutes.
  ///
  /// **The refresh and the window are not the same number and the page read as though they
  /// were.** Both the five-minute and the fifteen-minute lanes are read off five-minute bars, so
  /// both re-read every five minutes -- a reader comparing the two saw an identical countdown
  /// and reasonably concluded one of them was wrong. What differs is how far each call reaches:
  /// one is about the next five minutes, the other about the next fifteen. Printing only the
  /// countdown told them when it would change and never what it covered.
  horizonMinutes,
}: {
  asOfMs: number;
  stepMs: number;
  horizonMinutes?: number;
}) {
  const router = useRouter();
  const [left, setLeft] = React.useState<number | null>(null);
  const fired = React.useRef(false);

  React.useEffect(() => {
    fired.current = false;
    const tick = () => {
      const due = asOfMs + stepMs + GRACE_MS;
      const ms = due - Date.now();
      setLeft(ms);
      if (ms <= 0 && !fired.current && document.visibilityState === "visible") {
        // Once. `router.refresh()` re-renders the server component, which reads the new bar and
        // hands down a new `asOfMs`, which resets this effect -- so the next bar is counted from
        // the bar that actually arrived rather than from a clock that assumed one.
        fired.current = true;
        router.refresh();
      }
    };

    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [asOfMs, stepMs, router]);

  if (left === null) return null;
  const secs = Math.max(0, Math.ceil(left / 1000));
  const mm = Math.floor(secs / 60);
  const ss = secs % 60;
  // When the window this call covers actually closes -- asOf plus the horizon, which is a
  // different instant from the next bar close whenever the horizon spans more than one bar.
  const endsAt = new Date(asOfMs + (horizonMinutes ?? 0) * 60_000).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <span className="text-muted-foreground num text-xs normal-case">
      {left <= 0
        ? "reading the new bar…"
        : horizonMinutes
          ? // Two facts, and collapsing them was the confusion: a fifteen-minute call that
            // re-reads in four is not a contradiction, because the model is fitted on
            // five-minute bars and a fresh one closes every five minutes. The call you are
            // looking at runs its full fifteen from the bar it was read from; what happens in
            // four minutes is that a *new* call appears, about a later fifteen minutes.
            `this call runs to ${endsAt} · next read in ${mm > 0 ? `${mm}m ` : ""}${ss}s`
          : `this call stands for ${mm > 0 ? `${mm}m ` : ""}${ss}s, then refreshes`}
    </span>
  );
}

"use client";

import { useEffect, useState } from "react";
import { Card, Note } from "@/components/ui";
import { DEFAULT_PREFS, readPrefs, writePrefs, type Prefs } from "../prefs";

/// The preferences half of Screen 8, held in this browser for the same reason the watchlist is.
///
/// `prisma/schema.prisma` has no `Preference` model and the project has no identity subsystem, so
/// a stored preference has nowhere to belong to. Rather than introduce auth to hold two switches,
/// they live in `localStorage` and the screen says so -- the same position as
/// `app/preview/watchlist/storage.ts`, taken for the same reason.
///
/// Only preferences that this interface can actually honour are offered. A settings screen listing
/// switches that do nothing is worse than one with two that work, and both switches here are read
/// by `app/preview/watchlist/WatchlistClient.tsx`: one orders the list, the other shows each
/// figure's source and full timestamp inline.

const SWITCHES: { key: keyof Prefs; label: string; note: string }[] = [
  {
    key: "recentFirst",
    label: "Order the watchlist by when each instrument was saved",
    note: "Off orders it alphabetically by symbol.",
  },
  {
    key: "verboseProvenance",
    label: "Show source and full time beside every stored close",
    note: "Off shows the source under the date only, which keeps the tables easier to scan.",
  },
];

export function Preferences() {
  const [prefs, setPrefs] = useState<Prefs | null>(null);

  useEffect(() => setPrefs(readPrefs()), []);

  const set = (key: keyof Prefs, value: boolean) => {
    const next = { ...(prefs ?? DEFAULT_PREFS), [key]: value };
    setPrefs(next);
    writePrefs(next);
  };

  return (
    <>
      <Note>
        These are held in this browser only, for the same reason the watchlist is: this project has
        no user accounts and no preference table. They will not follow you to another browser or
        device.
      </Note>
      <Card>
        {/* Rendered disabled until the stored values are read, so the server's HTML and the first
            client render agree -- the server cannot see localStorage and must not guess. */}
        <ul className="space-y-3">
          {SWITCHES.map(({ key, label, note }) => (
            <li key={key} className="flex items-start gap-3">
              <input
                id={`pref-${key}`}
                type="checkbox"
                className="mt-1"
                disabled={prefs === null}
                checked={prefs ? prefs[key] : DEFAULT_PREFS[key]}
                onChange={(e) => set(key, e.target.checked)}
              />
              <label htmlFor={`pref-${key}`} className="text-sm">
                {label}
                <span className="text-muted-foreground block text-xs">{note}</span>
              </label>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}

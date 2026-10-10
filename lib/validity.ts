/// How long a call is meant to run, and how long it has been running.
///
/// One function, used by every list row and by the asset page, so the two cannot show a different
/// horizon or a different window for the same name.
///
/// **The horizon is read, not invented.** Every direction comes from one of two stored setups:
/// `swing` (`jobs/setup.py`: 20 and 50 session averages, five-day analogs) or `longer`
/// (`jobs/horizons.py`: 100 and 200 session averages). Which one decided is the horizon. Nothing here
/// derives a horizon from the distance between the stop and the target, because that distance is a
/// consequence of the setup's window, not a second measurement of it.
///
/// **"Valid from" is the day the call began, from the decision log.** A LONG that has been LONG
/// since Tuesday has been valid since Tuesday, not since this morning's refresh; the log records every
/// day's verdict, so the start of the current run of identical verdicts is a stored fact. When the log
/// has no run for this verdict yet (a call that began today, or a name the log has not reached) the
/// close the call is read from is its start.
///
/// **What the status can and cannot say.** "Active" is a call inside its window. "Expired" is a call
/// that has outlived it: still the rule table's answer today, but older than the horizon it was
/// measured for, which a reader should know. There is no "Invalidated" status on a direction, because
/// a direction whose stop has been crossed is not a direction: the rule table turns it into a WAIT
/// (`stop-crossed`), and that row says so in its own words.

export type HorizonKey = "swing" | "longer";

export const HORIZONS: Record<HorizonKey, { label: string; span: string; validDays: number }> = {
  swing: { label: "Swing", span: "1–7 days", validDays: 7 },
  longer: { label: "Position", span: "1–4 weeks", validDays: 28 },
};

export interface Validity {
  horizon: HorizonKey;
  label: string;
  span: string;
  /// ISO days, UTC.
  from: string;
  until: string;
  status: "Active" | "Expired";
  /// Which day of its window the call is on, 1 being the day it began.
  day: number;
}

/// A stored setup horizon read as a trade horizon. A direction always comes from a daily setup, so an
/// unrecognised or missing value is the default daily one, which is swing.
export function horizonKey(stored: string | null | undefined): HorizonKey {
  return stored === "longer" ? "longer" : "swing";
}

function addDays(iso: string, days: number): string {
  const t = Date.parse(`${iso.slice(0, 10)}T00:00:00Z`);
  return new Date(t + days * 86_400_000).toISOString().slice(0, 10);
}

function daysBetween(fromIso: string, toIso: string): number {
  return Math.round(
    (Date.parse(`${toIso.slice(0, 10)}T00:00:00Z`) - Date.parse(`${fromIso.slice(0, 10)}T00:00:00Z`)) / 86_400_000,
  );
}

function iso(d: Date | string | null | undefined): string | null {
  if (!d) return null;
  const t = d instanceof Date ? d.getTime() : Date.parse(String(d).slice(0, 10) + "T00:00:00Z");
  return Number.isFinite(t) ? new Date(t).toISOString().slice(0, 10) : null;
}

export function validityOf(o: {
  action: string;
  setupHorizon: string | null | undefined;
  /// The newest run of identical verdicts in the decision log: which verdict, and the day it began.
  runAction: string | null | undefined;
  runSince: Date | string | null | undefined;
  /// The close the call is read from.
  asOf: Date | string | null | undefined;
  today: string;
}): Validity | null {
  if (o.action !== "LONG" && o.action !== "SHORT") return null;
  const key = horizonKey(o.setupHorizon);
  const h = HORIZONS[key];
  const since = iso(o.runSince);
  const from = since && o.runAction === o.action ? since : (iso(o.asOf) ?? o.today);
  const until = addDays(from, h.validDays);
  return {
    horizon: key,
    label: h.label,
    span: h.span,
    from,
    until,
    status: o.today > until ? "Expired" : "Active",
    day: Math.max(1, daysBetween(from, o.today) + 1),
  };
}

/// "Oct 10", from an ISO day, in UTC. Written out rather than left to the reader's locale so the list
/// and the detail page print the same characters.
export function shortDay(isoDay: string): string {
  const m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const [, mm, dd] = isoDay.slice(0, 10).split("-");
  return `${m[Number(mm) - 1]} ${Number(dd)}`;
}

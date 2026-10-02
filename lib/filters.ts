// Filter state, as URL search params. Pure, so the link-building is testable.
//
// Why links and not a dropdown: a `<select>` that filters needs JavaScript to react to a change,
// and `useSearchParams` in a prerendered route must sit inside a `<Suspense>` boundary or
// `next build` fails outright while `next dev` passes — a trap that ships green and breaks on
// deploy. Chips that are plain links need none of it: the server page reads `searchParams`, does
// the filtering it already does best, and this app keeps the property that it runs no client
// JavaScript at all.
//
// The cost is one navigation per filter change, which is prefetched and, on a list this size,
// indistinguishable from local state.

/// A filter the reader can set. `null` is the "All" option and is represented by the key being
/// absent from the URL rather than by an empty value, so a default view has a clean address.
export interface FilterOption {
  label: string;
  value: string | null;
}

export interface FilterGroup {
  /// The search-param key, e.g. "market".
  key: string;
  label: string;
  options: FilterOption[];
}

/// What `searchParams` looks like once awaited. Next hands over `string | string[] | undefined`,
/// and a repeated key (`?market=US&market=PSX`) legitimately arrives as an array.
export type RawParams = Record<string, string | string[] | undefined>;

/// The first value for a key, because every filter here is single-choice.
///
/// A repeated key is not an error worth rejecting — a reader who hand-edits the URL gets the first
/// value rather than a crash.
export function readParam(params: RawParams, key: string): string | null {
  const raw = params[key];
  if (raw === undefined) return null;
  const value = Array.isArray(raw) ? raw[0] : raw;
  return value === undefined || value === "" ? null : value;
}

/// Read every declared filter, ignoring anything in the URL that is not one of ours.
///
/// Unknown keys are dropped rather than carried, so a stale or hostile link cannot smuggle
/// parameters through the chips and back out again.
export function readFilters(groups: FilterGroup[], params: RawParams): Record<string, string> {
  const out: Record<string, string> = {};
  for (const group of groups) {
    const value = readParam(params, group.key);
    if (value === null) continue;
    // Only values the group actually offers. A filter is a closed set; `?action=rm%20-rf` is not
    // one of the options and must not reach a query.
    if (group.options.some((o) => o.value === value)) out[group.key] = value;
  }
  return out;
}

/// The href for setting one filter, keeping the others as they are.
///
/// Setting a filter to null removes the key, which is what makes "All" the clean default address.
/// Keys are sorted so the same view always has the same URL, which matters for caching and for a
/// reader comparing two links.
export function hrefFor(
  basePath: string,
  current: Record<string, string>,
  key: string,
  value: string | null,
): string {
  const next: Record<string, string> = { ...current };
  if (value === null) delete next[key];
  else next[key] = value;

  const search = new URLSearchParams();
  for (const k of Object.keys(next).sort()) search.set(k, next[k]);
  const query = search.toString();
  return query ? `${basePath}?${query}` : basePath;
}

/// Whether a chip is the active one. The "All" chip is active exactly when the key is unset.
export function isActive(current: Record<string, string>, key: string, value: string | null): boolean {
  const set = current[key];
  return value === null ? set === undefined : set === value;
}

/// A one-line description of what is being shown, for the list heading.
///
/// Worth having because a filtered list that looks empty is indistinguishable from a broken one,
/// and the heading is where a reader looks first to tell those apart.
export function describeFilters(groups: FilterGroup[], current: Record<string, string>): string {
  const parts: string[] = [];
  for (const group of groups) {
    const value = current[group.key];
    if (value === undefined) continue;
    const option = group.options.find((o) => o.value === value);
    if (option) parts.push(option.label);
  }
  return parts.length === 0 ? "Everything stored" : parts.join(" · ");
}

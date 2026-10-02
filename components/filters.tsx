import Link from "next/link";
import { hrefFor, isActive, type FilterGroup } from "@/lib/filters";

/// Filter chips, as links.
///
/// Deliberately not a `<select>` and deliberately not a client component. The reasoning is in
/// lib/filters.ts, but the short version: `useSearchParams` in a prerendered route must sit inside
/// a `<Suspense>` boundary or `next build` fails while `next dev` passes, and this app has run zero
/// client JavaScript since it was written. Links keep both properties. The server page reads
/// `searchParams` and filters, which is the thing it is already good at.
///
/// Each chip is a real link, so it works with a keyboard, opens in a new tab, and can be shared —
/// a filtered list has an address, which a dropdown would have taken away.
export interface FilterChipsProps {
  groups: FilterGroup[];
  /// The filters currently set, already validated by `readFilters`.
  current: Record<string, string>;
  /// The page these chips filter, e.g. "/".
  basePath: string;
}

export function FilterChips({ groups, current, basePath }: FilterChipsProps) {
  return (
    <nav aria-label="Filter the lists" className="space-y-2">
      {groups.map((group) => (
        <div key={group.key} className="flex flex-wrap items-center gap-2">
          {/* The group name is a real label rather than a placeholder inside the control, because a
              chip row has no control to put it in and a reader needs to know what they are choosing. */}
          <span className="text-muted-foreground w-full shrink-0 text-xs sm:w-20">
            {group.label}
          </span>
          {group.options.map((option) => {
            const active = isActive(current, group.key, option.value);
            return (
              <Link
                key={option.label}
                href={hrefFor(basePath, current, group.key, option.value)}
                // aria-current rather than colour alone: the active chip has to be announced, and
                // a border change is invisible to a screen reader and to a colour-blind reader.
                aria-current={active ? "true" : undefined}
                // min-h-11 is 44px. Chips are the one control on these pages a thumb has to hit,
                // and the repo's existing pills are ~17px tall, which is not tappable.
                className={
                  active
                    ? "bg-primary text-primary-foreground border-primary inline-flex min-h-11 items-center rounded-full border px-3 text-sm font-medium"
                    : "bg-card text-muted-foreground hover:border-primary/50 hover:text-foreground inline-flex min-h-11 items-center rounded-full border px-3 text-sm"
                }
              >
                {option.label}
              </Link>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

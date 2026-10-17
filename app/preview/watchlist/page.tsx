import type { Metadata } from "next";
import { Card, Section } from "@/components/ui";
import { WatchlistClient } from "./WatchlistClient";

/// Screen 6 — watchlist.
///
/// The screen the contract called the largest undeclared item in the UI workstream, shipped as the
/// cheap first cut it recommended: the list is held in this browser and no identity subsystem is
/// introduced to hold it. `app/preview/watchlist/storage.ts` records that reasoning in full.
///
/// A server component that renders a client island and reads nothing itself. It cannot: the list
/// is in `localStorage`, so there is nothing for the server to fetch until the browser says what
/// it saved.
export const metadata: Metadata = { title: "Watchlist" };

export default function WatchlistPage() {
  return (
    <>
      <Section title="Watchlist">
        <Card>
          <p className="text-sm leading-relaxed">
            <strong>This list is held in this browser only.</strong> It is not an account. Nothing
            here is sent to the server except the symbols needed to look up their stored readings,
            and the list itself is not stored anywhere else — it will not follow you to another
            browser or device, and clearing this site&rsquo;s data will remove it.
          </p>
          <p className="text-muted-foreground mt-2 text-sm">
            This project has no user accounts: there is no sign-in, and no user, watchlist or
            preference table exists in the schema. A saved list that looked like an account while
            living in one browser would be the dishonest version of this screen.
          </p>
        </Card>
      </Section>

      <Section title="Saved instruments">
        <WatchlistClient />
      </Section>
    </>
  );
}

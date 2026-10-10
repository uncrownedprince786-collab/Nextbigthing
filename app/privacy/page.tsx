import type { Metadata } from "next";
import { Section } from "@/components/ui";

export const metadata: Metadata = {
  title: "Privacy and disclaimer",
  description: "What this site is and is not, what it collects about visitors, and who to contact.",
};

// Static: nothing here reads the database, and every statement is about how the site is built.
// Each one was checked against the code when it was written (2026-10-10): no sign-in, no forms, no
// cookies set by the site, no analytics or advertising scripts. If any of that changes, this page
// must change in the same commit.
const UPDATED = "10 October 2026";

export default function PrivacyPage() {
  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Privacy and disclaimer</h1>
        <p className="text-muted-foreground mt-2 text-sm">Last updated {UPDATED}.</p>
      </div>

      <Section title="Not investment advice">
        <div className="space-y-3 text-sm leading-relaxed">
          <p>
            NextBigThing publishes rule-based readings of public market data: prices, volumes, news
            headlines and similar sources. Every LONG, SHORT, entry zone, stop level, target, horizon
            and badge on this site is the output of a fixed set of rules applied to that data. It is
            information, not advice.
          </p>
          <p>
            Nothing on this site is a recommendation, an offer or a solicitation to buy or sell any
            security, currency, commodity or crypto-asset, and nothing here takes account of your
            objectives, finances or circumstances. The site is not a broker, an investment adviser or
            a licensed financial service in any jurisdiction.
          </p>
          <p>
            Trading carries a real risk of loss, including the loss of more than you put in on leveraged
            products. Past measurements, including any rate or reward figure shown here, do not predict
            future results. Data can be late, incomplete or wrong. Before acting on anything you read
            here, do your own research and, where appropriate, consult a qualified, licensed adviser.
          </p>
          <p>
            The site is provided as it is, without any warranty. To the extent the law allows, its
            operators accept no liability for any loss arising from its use.
          </p>
        </div>
      </Section>

      <Section title="What we collect about you">
        <div className="space-y-3 text-sm leading-relaxed">
          <p>
            <strong>Nothing you give us, because there is nothing to give.</strong> The site has no
            accounts, no sign-in, no forms, no comments and no mailing list.
          </p>
          <p>
            <strong>No cookies and no tracking.</strong> The site sets no cookies of its own and runs no
            analytics, advertising or tracking scripts. Your browser may keep its own ordinary cache.
          </p>
          <p>
            <strong>Hosting logs.</strong> The site is hosted by Vercel. Like any web host, Vercel
            processes the technical details of each request (such as your IP address, browser type and
            the time of the request) to deliver pages and to protect the service from abuse. That
            processing is governed by Vercel&apos;s own privacy policy. The site&apos;s own code does not
            store these details.
          </p>
          <p>
            <strong>Live prices.</strong> When an asset page refreshes its latest price, your browser asks
            this site&apos;s own server, and the server asks the price provider. No information about you
            is passed to the provider.
          </p>
        </div>
      </Section>

      <Section title="Third-party data and links">
        <div className="space-y-3 text-sm leading-relaxed">
          <p>
            Figures come from public sources including Yahoo Finance, CoinPaprika, the Pakistan Stock
            Exchange, Google News, Google Trends, Wikipedia, Hacker News, Reddit and Amazon. Their data
            remains theirs, and their terms apply to it. Links to other sites lead to pages governed by
            those sites&apos; own privacy policies.
          </p>
        </div>
      </Section>

      <Section title="Changes and contact">
        <div className="space-y-3 text-sm leading-relaxed">
          <p>
            If what the site collects ever changes, this page will change with it, and the date above
            will say when.
          </p>
          <p>
            Questions about this page or the site can be raised on the project&apos;s public issue
            tracker:{" "}
            <a
              href="https://github.com/uncrownedprince786-collab/Nextbigthing/issues"
              className="underline underline-offset-2"
              rel="noopener"
            >
              github.com/uncrownedprince786-collab/Nextbigthing/issues
            </a>
            .
          </p>
        </div>
      </Section>
    </div>
  );
}

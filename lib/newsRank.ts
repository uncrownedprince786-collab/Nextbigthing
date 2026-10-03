/// Which stored headlines are about the business, and which are about everything else.
///
/// Why this file exists, with the rows that forced it. The asset page is allowed three news
/// links above the fold, so the three it picks are the whole of what most readers will ever see.
/// Picking them by `publishedAt` alone put this at the top of Attock Refinery on 2026-10-01:
///
///   "Attock Refinery secures 1st position in labour category at GCNP Sustainability Awards"
///
/// and pushed below the fold, three days older and carried by three separate outlets:
///
///   "Attock Refinery plans new 50,000 bpd deep-conversion refinery"
///   "4 local refineries sign $5bn upgradation deals with govt"
///
/// Apple the same week was thirteen consecutive rows of iPhone buying advice, fading paint and
/// MagSafe accessories. And `Cricinfo` has 26 rows in the News table, none of them about an
/// asset's business. Newest-first is not a ranking, it is the absence of one.
///
/// **What this does and does not claim.** It sorts stored headlines; it never writes one, never
/// scores a company, and never decides a direction. A headline it ranks low is still stored,
/// still counted by `jobs/human.py`, and still listed in full under Details — this changes which
/// three reach the top block, and nothing else. It is deliberately a keyword reading over the
/// title: that is crude, and it is also inspectable, arguable and cheap, which a model would not
/// be. When it is wrong it is wrong visibly and in one list that anyone can edit.
///
/// The ordering rule, in one line: how many separate outlets carried the story first, what the
/// words are about second, how recent it is last.

/// A story carried by several outlets independently is more likely to be material than one
/// carried by a single publisher. This is the same argument `NewsLineage` was built on — one
/// report syndicated twenty times is one piece of information — used the other way round: the
/// count is evidence of how many desks thought it was worth writing up.
///
/// It is the first term because it is the only one that is not a guess about language. On Attock
/// Refinery it alone separates the refinery plan (three outlets) from the awards item (one).
const OUTLET_WEIGHT = 6;

/// Words that make a headline about the business. Grouped so that the reason can be named.
///
/// Drawn from the stored rows rather than from imagination: every group below matched something
/// real in the News table when this was written.
const MATERIAL: ReadonlyArray<readonly [string, RegExp]> = [
  ["results", /\b(earnings|results|profit|loss|revenue|margin|guidance|outlook|forecast|quarter|q[1-4]\b|half[- ]year|eps)\b/i],
  ["payout", /\b(dividend|payout|buyback|repurchase|bonus share|right shares?)\b/i],
  ["deal", /\b(deal|agreement|contract|mou|acquisition|acquires?|merger|merges?|stake|joint venture|tender|awards? contract|wins? contract)\b/i],
  ["capacity", /\b(refinery|plant|capacity|expansion|upgradation|upgrade (?:project|programme|program|agreement|deal|plan)s?|deep[- ]conversion|bpd|production|output|commissioned?|shutdown|maintenance)\b/i],
  // Deliberately not a bare `upgrade`. "iPhone Duo can be just $9/month with trade-in using
  // Apple Upgrade" scored as an analyst rating on exactly that, and a trade-in programme is not
  // a broker's opinion. An upgrade only counts here when something says whose upgrade it is.
  ["rating", /\b(?:analysts?|brokers?|bank|firm)\w* (?:upgrades?|downgrades?|cuts?|raises?)\b|\b(?:upgraded|downgraded|rated) (?:to|from|at)\b|\bprice target\b|\b(?:overweight|underweight|buy rating|sell rating|hold rating)\b|\binitiat\w+ coverage\b|\banalyst rating\b/i],
  ["policy", /\b(tariff|duty|duties|subsidy|policy|regulat\w+|government|govt|ministry|cabinet|ogra|sbp|state bank|sec\b|fda|antitrust|probe|investigation|lawsuit|fine|penalty|sanction)\b/i],
  ["money", /\b(invest\w+|funding|raises?|debt|bond|sukuk|loan|ipo|listing|rights issue|placement|billion|bn\b|crore)\b/i],
  ["people", /\b(ceo|chief executive|chairman|cfo|resigns?|appoint\w+|steps down|board approves)\b/i],
  // Not a bare `orders?` either: "when you can start the iPhone Duo pre-order process" is a
  // launch date for shoppers, and it matched demand. An order book is a business fact; a
  // pre-order queue is a retail one.
  ["demand", /\b(demand|order book|backlog|shipments?|export(?:s|ed)?|sales (?:rose|fell|up|down|jump\w*|slump\w*)|price (?:hike|cut|increase)|supply (?:deal|chain|agreement)|volumes? (?:rose|fell|up|down))\b/i],
];

/// Words that make a headline about something other than the business.
///
/// Every one of these matched a stored row. The awards group is first because it is the one that
/// produced the complaint: a sustainability award is a real event and it is not a reason to hold
/// or sell a refinery, and it outranked a $5bn upgrade programme purely by being newer.
const NOISE: ReadonlyArray<readonly [string, RegExp]> = [
  ["award", /\b(awards?|award-winning|wins? (?:1st|first|top|the)? ?(?:position|place|prize)|honou?red|recognis\w+|accolade|certifi\w+ for|csr|sustainability award)\b/i],
  ["sport", /\b(cricket|psl\b|t20|odi\b|test match|football|hockey|olympic|tournament|wickets?|innings|squad|captain)\b/i],
  ["advice", /\b(how to|tips?\b|should you|here'?s why|what to know|guide to|explained|best \d+|top \d+ (?:things|ways|tips)|read these)\b/i],
  // `colou?r\b[^.]{0,20}fading` rather than a fixed phrase: the stored row reads "the devices'
  // color is already fading", and a pattern written for "color is fading" missed it by one
  // adverb. Noise wording varies more than business wording does, so these stay loose.
  ["gadget", /\b(hands[- ]on|unboxing|wallpapers?|accessor\w+|magsafe|screen protector|battery life)\b|\breview\b|\bcolou?r\b[^.]{0,20}\bfading\b|\bdeals? on\b/i],
  ["pundit", /\b(jim cramer|cramer (?:says|urges)|mad money|analyst says you should|why i |i love |i can'?t wait)\b/i],
  ["listicle", /\b(\d+ (?:stocks?|things|reasons|ways)|stocks? to (?:buy|watch) (?:now|today)|motley fool|zacks rank)\b/i],
  // Pages a machine wrote from a ticker, which carry no report at all. These only surfaced once
  // the events page started ranking every asset's news together instead of one asset's at a
  // time: TradingView is the second largest publisher in the table at 104 rows, and its
  // auto-generated "NCPL Forecast — Price Target — Prediction for 2027" appeared twice in the
  // first six rows under two different symbols. Matched on the title's shape rather than by
  // banning the publisher, because the same desk does also carry real items.
  ["generated", /\bforecast\s*[—–-]\s*price target\b|\bprice target\s*[—–-]\s*prediction\b|\bprediction for \d{4}\b|\b(?:price|quote) (?:on|for) \w+ \d{1,2}, \d{4}\b|\bprediction market\b|\bETF Profile\b|\b(?:employee count|headcount) data\b/i],
];

/// Publishers whose whole output is off-topic for every asset. Not a judgement of quality — a
/// statement that nothing from this desk is about a listed company's business. `Cricinfo` is in
/// the News table because an industry feed matched a sports page, and 26 rows of it are stored.
const OFF_TOPIC_PUBLISHERS = /^(cricinfo|espncricinfo|espn|sky sports|geo super)/i;

export interface RankedHeadline {
  /// Higher is more market-relevant. Can be negative.
  score: number;
  /// The groups that matched, for the reason line and for arguing with this file.
  material: string[];
  noise: string[];
  /// False when nothing about the business was found and something off-topic was, which is the
  /// state the top block should skip rather than rank low.
  relevant: boolean;
}

/// Read one headline. Pure, so the ranking is the same on the server and in a test.
///
/// `outlets` is the lineage's item count — how many stored rows share this story. Null and 1 are
/// treated the same, because an unclustered row and a single-outlet story are the same evidence.
export function rankHeadline(
  title: string,
  publisher: string | null | undefined,
  outlets: number | null | undefined,
): RankedHeadline {
  const text = `${title} ${publisher ?? ""}`;
  const material = MATERIAL.filter(([, re]) => re.test(text)).map(([name]) => name);
  const noise = NOISE.filter(([, re]) => re.test(text)).map(([name]) => name);

  if (publisher && OFF_TOPIC_PUBLISHERS.test(publisher.trim())) {
    return { score: -100, material, noise: [...noise, "off-topic publisher"], relevant: false };
  }

  // The outlet count is capped. Beyond four desks the extra ones are syndication rather than
  // independent judgement, and an uncapped term would let one wire pickup outrank everything.
  const spread = Math.min(Math.max((outlets ?? 1) - 1, 0), 3) * OUTLET_WEIGHT;
  const score = spread + material.length * 4 - noise.length * 5;

  // Relevance is not the same question as the score. A headline with nothing material in it and
  // something off-topic in it is not a weak business story, it is not a business story, and the
  // top block should leave it out rather than print it third.
  //
  // `generated` is the exception that rejects outright, like an off-topic publisher does. A page
  // a machine assembled from a ticker is stuffed with business vocabulary by construction —
  // "NCPL Forecast — Price Target — Prediction for 2027" matches the analyst-rating group on
  // `price target` — so the ordinary "did anything material match?" rescue hands it the slot it
  // least deserves. There is no report behind these at any score.
  if (noise.includes("generated")) {
    return { score: Math.min(score, -1), material, noise, relevant: false };
  }

  return { score, material, noise, relevant: material.length > 0 || noise.length === 0 };
}

export interface RankableHeadline {
  title: string;
  publisher: string;
  publishedAt: Date | string;
  outlets?: number | null;
  /// The story this row belongs to, from `jobs/lineage.py`. Rows sharing one are the same report
  /// at different desks, and only the best of them may take a slot.
  lineageId?: string | null;
  /// True for the earliest row in its story, which is the closest thing stored to the original
  /// report. Used to choose which outlet represents the story.
  isOriginal?: boolean | null;
}

/// Sort headlines so the top block can take the first few, dropping the ones that are not about
/// the business at all.
///
/// Recency is the last term rather than the first. It still decides between two stories that are
/// equally material, which is most pairs — this is a re-ordering of the top handful, not a
/// suppression of today's news.
export function rankHeadlines<T extends RankableHeadline>(
  items: readonly T[],
): Array<T & { rank: RankedHeadline }> {
  const scored = items
    .map((item) => ({ ...item, rank: rankHeadline(item.title, item.publisher, item.outlets) }))
    .filter((item) => item.rank.relevant)
    .sort((a, b) => {
      if (b.rank.score !== a.rank.score) return b.rank.score - a.rank.score;
      return new Date(b.publishedAt).getTime() - new Date(a.publishedAt).getTime();
    });

  // One slot per story, not one per row. The outlet count is the first term in the score, so
  // without this the best-evidenced story wins every slot it has rows for: Attock Refinery's
  // three slots were all the same refinery announcement from three Pakistani desks, which tells
  // a reader one thing and spends three lines doing it. The original report represents the
  // story where one is marked, and otherwise the highest-scoring row does.
  const seen = new Set<string>();
  const titles = new Set<string>();
  const byStory: Array<T & { rank: RankedHeadline }> = [];
  for (const item of scored) {
    // The second guard is for duplicates `jobs/lineage.py` cannot see. Stories are clustered
    // **per asset**, because the same wording about two different companies is two different
    // stories — so one wire item filed against two symbols gets two lineages and passes the
    // check above. That is right on an asset page, where only one symbol's rows are ever in
    // play, and wrong on the events page, which ranks every asset's news in one list: the same
    // TradingView page appeared there under NCPL and NCL. Matching on the title is the weaker
    // test and it is the only one available across assets.
    const key = headlineOf(item.title, item.publisher).toLowerCase().replace(/\s+/g, " ").trim();
    if (titles.has(key)) continue;
    if (item.lineageId) {
      if (seen.has(item.lineageId)) continue;
      const original = scored.find((o) => o.lineageId === item.lineageId && o.isOriginal);
      seen.add(item.lineageId);
      titles.add(key);
      byStory.push(original ?? item);
      continue;
    }
    titles.add(key);
    byStory.push(item);
  }
  return byStory;
}

/// The headline, with the outlet's name taken off the end of it.
///
/// Shared by the asset panel's top block and the events page strip, which both print the
/// publisher on its own beside the title.
///
/// Stored titles arrive as "Jim Cramer urges buying Apple stock - Yahoo Finance", because that is
/// how the feeds write them. The publisher is printed on its own line directly underneath, so the
/// suffix is the same word twice in a block that has three lines of space for three stories. Only
/// stripped when it actually matches the publisher: a title that genuinely ends in a dash and a
/// name is left exactly as stored, because this is a quotation.
export function headlineOf(title: string, publisher: string): string {
  for (const dash of [" - ", " – ", " — ", " | "]) {
    const tail = `${dash}${publisher}`;
    if (title.endsWith(tail) && title.length > tail.length) {
      return title.slice(0, -tail.length);
    }
  }
  return title;
}

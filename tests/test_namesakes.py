"""A headline is stored against an asset only when it names that asset.

Measured 2026-10-11 over the rows stored in the 14 days before: the news lane filed "DASH diet
found safe" under the Dash coin, "Chicago Sky" and "October's night sky" under Sky, "Port Vale
2-0 Mansfield" under Vale, "King Lear" under Lear, "H-1B visa workers" under Visa, "Dow Jones
Futures" under Dow, "SAP Center" under SAP, and a publisher suffix ("... - S&P Global",
"... - Polygon.com") counted as the name. Each case below is a real headline from those rows, or
the genuine story that must still match. Run: python -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "jobs"))

import human  # noqa: E402
import prices  # noqa: E402


def coin(symbol: str, name: str) -> dict:
    return {"symbol": symbol, "name": name, "assetType": "crypto", "source": "coinpaprika"}


def share(symbol: str, name: str) -> dict:
    return {"symbol": symbol, "name": name, "assetType": "stock", "source": "yahoo"}


def karachi(symbol: str, name: str) -> dict:
    return {"symbol": symbol, "name": name, "assetType": "stock", "source": prices.PSX}


class Case(unittest.TestCase):
    def names(self, asset: dict, *titles: str) -> None:
        m = prices.news_matcher(asset)
        for t in titles:
            self.assertTrue(m.search(t), f"{asset['symbol']} should match {t!r}")

    def not_names(self, asset: dict, *titles: str) -> None:
        m = prices.news_matcher(asset)
        for t in titles:
            self.assertFalse(m.search(t), f"{asset['symbol']} should not match {t!r}")


class ACoinNamedLikeAWordNeedsCryptoContext(Case):
    def test_ordinary_words_are_not_the_coin(self):
        self.not_names(
            coin("dash-dash", "Dash"),
            "Potassium-rich DASH diet found safe for adults taking common blood pressure "
            "medications - www.heart.org",
            "Houston Dash Defender Avery Patterson Named to U.S. Women's National Team Roster "
            "- Houston Dynamo FC",
            "Jaylin Noel makes 30-yard dash on kick return - Houston Texans",
        )
        self.not_names(
            coin("sky-sky", "Sky"),
            "What's next for the Chicago Sky in 2027, per Jeff Pagliocca - The IX Sports",
            "October’s night sky is full of cosmic tricks and treats - Science Daily",
            "Reform given record-breaking £72m by two crypto billionaires - Sky News",
        )
        self.not_names(coin("grass-grass", "GRASS"),
                       "The Best Time to Plant Grass Seed for a Greener, Healthier Lawn - Real Simple")
        self.not_names(coin("atom-cosmos", "Cosmos"),
                       "HE’S GONE: Stover departs Cosmos - Front Row Soccer",
                       "NVIDIA Cosmos 3 on AWS: Omnimodal World Models for Physical AI - AWS")
        self.not_names(coin("xlm-stellar", "Stellar"),
                       "NASA’s Webb Captures Commotion From Nebula’s Stellar Jets - NASA")
        self.not_names(coin("op-optimism", "Optimism"),
                       "Consumer optimism slides to lowest since 2014 as fears escalate over "
                       "rising prices and jobs - CNBC")
        self.not_names(coin("qnt-quant", "Quant"),
                       "AI upends Singapore’s ‘quant Olympics’ - Financial Times")
        self.not_names(coin("stx-stacks", "Stacks"),
                       "Cargo stacks up as Pakistan seizes containers to block capital routes - Reuters")
        self.not_names(coin("ondo-ondo", "Ondo"),
                       "Nigerian Air Force says plane carrying 25 crashed with no survivors in "
                       "southern Ondo state - AP News")
        self.not_names(coin("drv7-derive", "Derive"),
                       "Researchers Derive Bounds For Quantum Channel Games - Quantum Zeitgeist")
        self.not_names(coin("sol-solana", "Solana"),
                       "Solana Beach market owners say immigration enforcement is hurting business")

    def test_a_quoted_title_is_still_a_title(self):
        self.not_names(coin("rndr-render-token", "Render"),
                       "‘Render Unto Caesar …’ - Billy Graham Evangelistic Association")
        self.not_names(coin("met-meteora", "Meteora"),
                       "Linkin Park’s ‘Meteora’ Earns Diamond Certification - 95.9 The RAT")
        self.not_names(coin("cro-cryptocom-chain", "Cronos"),
                       "Venom Frontman Conrad ‘Cronos’ Lant Dies at 63 - Variety")
        # And a quoted fragment does not hide a genuine story.
        self.names(coin("strk-starknet", "Starknet"),
                   "‘Not fast enough’ – Starknet eyes Ethereum exit amid quantum fears - AMBCrypto")

    def test_a_share_with_the_coins_ticker_is_not_the_coin(self):
        self.not_names(coin("dash-dash", "Dash"),
                       "Can AI Really Disrupt DoorDash (DASH)? Jim Cramer Isn't Convinced - Yahoo Finance")
        self.not_names(
            coin("sei-sei", "Sei"),
            "Solaris Energy Infrastructure (NYSE:SEI) - Stock Analysis - Simply Wall Street",
            "Sintana Energy Inc. (SEI.V) Stock Price, News, Quote & History - Yahoo! Finance Canada",
            "SEI Opens Singapore Office to Support Growing Asset Management Sector in Asia - PR Newswire",
        )
        # "Trump" the person is not the OFFICIAL TRUMP coin, even next to the word crypto.
        self.not_names(coin("trump-official-trump", "OFFICIAL TRUMP"),
                       "Trump signs order on crypto reserve as bitcoin rallies - Reuters")

    def test_genuine_coin_stories_still_match(self):
        self.names(coin("avax-avalanche", "Avalanche"),
                   "Avalanche (AVAX) jumps 8% as institutional demand builds - CoinDesk",
                   "Tokenized Treasuries on Avalanche Surge 300% in a Year - Benzinga")
        self.names(coin("sui-sui", "Sui"),
                   "Sui token unlock looms as SUI slips 4% - The Block",
                   "Sui (SUI) Price USD Today, News, Charts, Market Cap - Coinbase")
        self.names(coin("dash-dash", "Dash"),
                   "Dash crypto rallies 165% then corrects 31% - Pluang",
                   "Zcash and Dash Explode 80% While Crypto Market Bleeds - CoinMarketCap")
        self.names(coin("sky-sky", "Sky"),
                   "Galaxy adds $100M Sky token and institutional adoption is tested - CryptoSlate")
        self.names(coin("aster-aster", "Aster"),
                   "Binance Founder ‘CZ’ Calls Aster Mainnet Launch A ‘Big One’ - Stocktwits")
        self.names(coin("flr-flare-network", "Flare Network"),
                   "Firelight launches DeFi insurance with $115M staked XRP on Flare network - Crypto Briefing")
        self.names(coin("trump-official-trump", "OFFICIAL TRUMP"),
                   "OFFICIAL TRUMP (TRUMP) Volatility: Gala Contest & Media Spotlight")
        self.names(coin("vvv-venice-token", "Venice Token"),
                   "Venice Token drops 25% after Q3 rally - Pluang")
        self.names(coin("btc-bitcoin", "Bitcoin"),
                   "Current price of Bitcoin for Sept. 28, 2026 - Fortune",
                   "BTC slips below $60,000 as liquidations mount - Reuters")
        # A crypto publisher is context, though never a name.
        self.names(coin("aave-new", "Aave"),
                   "Aave Raises Core GHO Borrow Rate to 4.5% Amid Thin Redemption Reserves - The Defiant")
        self.names(coin("dot-polkadot", "Polkadot"),
                   "Polkadot Price Prediction October 2026: Can DOT Build on a 45.4% September Surge?")


class AShareIsMatchedOnItsNameAsPrinted(Case):
    def test_a_name_inside_a_longer_proper_noun_is_that_other_thing(self):
        self.not_names(share("VALE", "Vale"),
                       "Port Vale 2-0 Mansfield (Oct 6, 2026) Player Stats - ESPN",
                       "Vale High School (OR) Football - MaxPreps")
        self.not_names(share("LEA", "Lear"),
                       "King Lear review – David Threlfall makes a moving Lear, but why is he "
                       "playing the Fool too? - The Guardian")
        self.not_names(share("DOW", "Dow"),
                       "Dow Jones Futures: Nasdaq Hits Record Highs; TSMC, Nvidia Rally - Investor's Business Daily")
        self.not_names(share("SAP", "SAP"),
                       "Sharks unveil what's new at SAP Center for the 2026-27 season | San Jose Sharks - NHL.com")
        self.not_names(share("WM", "Waste Management"),
                       "Boone County Solid Waste Management District eyes permanent tox drop site")
        self.not_names(share("COF", "Capital One"),
                       "Kennedy Center Honors to take place at Capital One Arena - CBS News")
        self.not_names(share("KR", "Kroger"),
                       "Ride LexTran to Kroger Field, Keeneland for $1 Each Way on Saturday - UKAthletics")

    def test_a_lowercase_word_is_not_a_name(self):
        self.not_names(share("V", "Visa"),
                       "WATCH: Vance says Microsoft is being suspended from green card program for "
                       "H-1B visa workers - PBS",
                       "Trump administration investigates 9 universities over visa fraud claims - Higher Ed Dive")
        self.not_names(share("WM", "Waste Management"),
                       "Federal EPR could cut waste management costs in half: WWF - Packaging Dive")
        self.not_names(share("TGT", "Target"),
                       "Alzheimer's disease target and drug discovery by leveraging multiomics - Nature")

    def test_the_wrong_capitals_are_not_the_name(self):
        # The Department of War is "DoW".
        self.not_names(share("DOW", "Dow"),
                       "DoW and U.S. Navy Announce Contract With Raytheon - U.S. Department of War (.gov)")

    def test_a_short_word_is_matched_whole_and_never_inside_another(self):
        # The old check was the first word of the name as a lowercase substring: "ge" is in
        # "generation", "on" is in every headline.
        self.not_names(share("GE", "GE Aerospace"),
                       "UC co-op student helps develop next generation of commercial airliners")
        self.not_names(share("ON", "ON Semiconductor"),
                       "New research institute focusing on semiconductor innovation opens in Arkansas")
        self.names(share("ON", "ON Semiconductor"),
                   "ON Semiconductor to Buy Synaptics for Cash, Not Stock, in Downsized Deal - WSJ")

    def test_a_ticker_counts_only_where_it_can_only_be_the_ticker(self):
        dow = share("DOW", "Dow")
        self.names(dow, "Dow Inc. (DOW) to cut 1,500 jobs", "$DOW slides after earnings",
                   "Chemical maker NYSE: DOW guides lower")
        # Not GE Vernova, not GE HealthCare: "GE" bare is not GE Aerospace.
        self.not_names(share("GE", "GE Aerospace"), "GE Vernova shares jump on grid orders")
        # A ticker that is the company's initials is how the press names it.
        self.names(share("AIG", "American International Group"),
                   "AIG rises as investors weigh higher yields - Quiver Quantitative")
        self.names(share("IOVA", "Iovance Biotherapeutics, Inc."),
                   "Buy Now Before Many Growth Catalysts Kick In (NASDAQ:IOVA) - Seeking Alpha")

    def test_the_publisher_is_not_the_headline(self):
        spgi = share("SPGI", "S&P Global")
        self.not_names(spgi, "Most US bank stocks trade lower in September - S&P Global",
                       "S&P 500 rises 1% as yields ease - Reuters")
        self.names(spgi, "S&P Global to sell its mobility unit - Reuters")
        self.not_names(coin("pol-polygon-ecosystem-token", "Polygon"),
                       "Star Wars: Galactic Racer is the Best Arcade Racing Game in a Generation - Polygon.com")

    def test_a_search_word_is_not_a_name(self):
        # Citigroup's hint is "bank", a search word; as a token it filed every bank story under C.
        self.not_names(share("C", "Citigroup"), "Bank stocks fall as yields rise - Reuters")
        # A hint written as a name still is one: Alphabet is "Google" in every headline.
        self.names(share("GOOGL", "Alphabet"), "Google rolls out Gemini 4 Argon - CNBC")

    def test_genuine_company_stories_still_match(self):
        self.names(share("AAPL", "Apple"), "Apple unveils new iPhone lineup - Reuters")
        self.names(share("TSLA", "Tesla"), "Tesla shares slide after deliveries miss - CNBC")
        self.names(share("V", "Visa"), "Visa Inc. reports quarterly earnings - Business Wire")
        self.names(share("WM", "Waste Management"), "Waste Management beats estimates - Reuters")
        self.names(share("MU", "Micron Technology"),
                   "Micron's AI-fueled revenue forecast blows past estimates - Reuters")
        self.names(share("XOM", "Exxon Mobil"), "Exxon to cut 2,000 jobs - Bloomberg")
        self.names(share("PH", "Parker Hannifin"),
                   "Parker-Hannifin Benefits From Business Strength Amid Headwinds - Yahoo Finance")
        self.names(share("ITUB", "Itaú Unibanco Holding S.A."),
                   "Itau Unibanco Holding SA Stock (ITUB) Closed Up by 3.36% on Oct 9 - TradingKey")
        self.names(share("LOW", "Lowe's"), "Lowe’s beats estimates on pro demand - Reuters")
        self.names(share("NU", "Nu Holdings Ltd."),
                   "Nu Holdings Jumps 3% After Ruling Out Monzo Deal - Yahoo Finance")
        self.names(share("PM", "Philip Morris International"),
                   "Philip Morris raises guidance on Zyn demand - Reuters")
        # The short form is refused when it is an ordinary word.
        self.assertNotIn("waste", prices.news_match_tokens(share("WM", "Waste Management")))
        self.assertNotIn("walt", prices.news_match_tokens(share("DIS", "Walt Disney")))


class TheOtherKindsKeepTheirRules(Case):
    def test_a_karachi_listing(self):
        self.names(karachi("LUCK", "Lucky Cement"), "Lucky Cement profit rises 20% - Business Recorder")
        self.names(karachi("HUBC", "Hub Power"),
                   "Hub Power Company Reports PKR 33M Loss from BYD Pakistan")
        self.names(karachi("SYS", "Systems Limited"), "SYS Insider Buy: senior management director reports")
        # A capitalised ticker in an all-capitals headline is just a word in capitals.
        self.not_names(karachi("POWER", "Power Cement"), "PAKISTAN POWER SECTOR DEBT SWELLS AGAIN")

    def test_a_fund_and_a_pair(self):
        slv = {"symbol": "SLV", "name": "iShares Silver Trust", "assetType": "etf"}
        self.names(slv, "Silver ETF Faceoff: Will SLV or SIL Give You Better Exposure? - The Motley Fool")
        gld = {"symbol": "GLD", "name": "SPDR Gold Shares", "assetType": "etf"}
        self.names(gld, "GLD Sees Biggest Single-Day Gains Since February - Stocktwits")
        pkr = {"symbol": "USDPKR", "name": "US Dollar / Pakistani Rupee", "assetType": "forex"}
        self.names(pkr, "Rupee Falls 22 Paise To 96.57 Against US Dollar")


class TheHeadlineIsCutFromItsPublisher(unittest.TestCase):
    def test_the_publisher_suffix_is_cut(self):
        self.assertEqual(prices.headline_body("Apple unveils iPhone - Reuters"), "Apple unveils iPhone")
        # Only the last " - ": a headline can hold one of its own.
        self.assertEqual(prices.headline_body("Breakingviews - Why a deal makes sense - Reuters"),
                         "Breakingviews - Why a deal makes sense")
        # A " | " inside a Google title is part of the headline...
        self.assertEqual(prices.headline_body("CDE News | COEUR MINING INC (NYSE:CDE) - ChartMill"),
                         "CDE News | COEUR MINING INC (NYSE:CDE)")
        # ...and a short " | Site" tail on a title with no " - " is the publisher.
        self.assertEqual(prices.headline_body("Lucky Cement posts record profit | Dawn"),
                         "Lucky Cement posts record profit")

    def test_a_coins_query_says_which_meaning_it_wants(self):
        self.assertEqual(prices.asset_news_term(coin("dash-dash", "Dash")), "Dash crypto")
        self.assertEqual(prices.asset_news_term(coin("avax-avalanche", "Avalanche")),
                         "Avalanche crypto AVAX")


class StoredRowsAreJudgedByTheSameRule(unittest.TestCase):
    """jobs/human.py counts stored rows. Rows stored under the old rule are set aside by the new one
    when they are counted, so a reading stops being built from someone else's news."""

    END = date(2026, 10, 11)

    def row(self, title: str, days_ago: float) -> dict:
        when = datetime.combine(self.END, datetime.min.time()) - timedelta(days=days_ago)
        return {"title": title, "publisher": title.rsplit(" - ", 1)[-1], "lineageId": None,
                "publishedAt": when}

    def test_namesakes_are_set_aside_and_genuine_rows_kept(self):
        visa = dict(share("V", "Visa"), id="v")
        recent = {"v": [
            self.row("Visa Inc. reports quarterly earnings - Business Wire", 1),
            self.row("Trump administration investigates 9 universities over visa fraud claims - Higher Ed Dive", 1),
            self.row("WATCH: Vance says Microsoft is suspended for H-1B visa workers - PBS", 2),
        ], "product-1": [self.row("anything at all - Somewhere", 1)]}
        (kept,), aside = human.on_target([visa], recent)
        self.assertEqual(aside, 2)
        self.assertEqual([r["title"] for r in kept["v"]],
                         ["Visa Inc. reports quarterly earnings - Business Wire"])
        # A target that is not an asset is untouched.
        self.assertEqual(len(kept["product-1"]), 1)

    def test_setting_rows_aside_only_lowers_the_counts(self):
        dash = dict(coin("dash-dash", "Dash"), id="d")
        titles = [
            "Dash crypto rallies 165% then corrects 31% - Pluang",
            "Dash Drops 9% Amid Broad Crypto Liquidation Event - CoinMarketCap",
            "Potassium-rich DASH diet found safe for adults - www.heart.org",
            "Houston Dash Defender Named to U.S. Roster - Houston Dynamo FC",
            "Jaylin Noel makes 30-yard dash on kick return - Houston Texans",
        ]
        recent = {"d": [self.row(t, 1 + i * 0.1) for i, t in enumerate(titles)]}
        earlier = {"d": []}
        before = human.read_target(None, "assetId", "d", "Dash", self.END, recent, earlier)
        (recent_on, earlier_on), aside = human.on_target([dash], recent, earlier)
        after = human.read_target(None, "assetId", "d", "Dash", self.END, recent_on, earlier_on)
        self.assertEqual(aside, 3)
        self.assertEqual((before["items"], after["items"]), (5, 2))
        self.assertLessEqual(after["recentStories"], before["recentStories"])
        self.assertLessEqual(after["positive"] + after["negative"],
                             before["positive"] + before["negative"])

    def test_a_negative_clause_keeps_its_row_and_still_takes_no_side(self):
        # Identity and tone are separate questions. A genuine headline that hedges is still about
        # the asset, so it is kept and counted -- and the tone rule still refuses to score it.
        tsla = dict(share("TSLA", "Tesla"), id="t")
        hedged = "Tesla shares won't recover this year, analyst says - Barron's"
        (kept,), aside = human.on_target([tsla], {"t": [self.row(hedged, 1)]})
        self.assertEqual(aside, 0)
        subject = human.subject_names("Tesla", "TSLA", "stock", {"tesla"})
        self.assertEqual(human.classify(kept["t"][0]["title"], None, subject), "neutral")
        # And a negative headline about the travel document never reaches the company's tone.
        visa = dict(share("V", "Visa"), id="v")
        (kept,), aside = human.on_target(
            [visa], {"v": [self.row("H-1B visa fraud surges, officials warn - PBS", 1)]})
        self.assertEqual((aside, kept["v"]), (1, []))


if __name__ == "__main__":
    unittest.main()

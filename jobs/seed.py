"""Seed the fixed lists: industries, assets, products, product to asset links.

The asset list is fixed on purpose. Widening or narrowing it silently would change what
"top" means between one run and the next, so a change here is a deliberate edit.

Run: python jobs/seed.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jobs"))

from nbt import db, step  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:  # noqa: BLE001
    os.environ.setdefault("DATABASE_URL", "")

# slug, name, summary, sort
INDUSTRIES = [
    (
        "mega-cap-tech",
        "Mega Cap Tech",
        "The largest US listed platform and hardware companies. This group is the closest "
        "proxy for how public markets priced the AI build out.",
        1,
    ),
    (
        "semiconductors",
        "Semiconductors",
        "Chip designers and the equipment makers that supply them. The clearest read on "
        "the physical side of the AI build out.",
        2,
    ),
    (
        "crypto",
        "Crypto",
        "Large cap cryptocurrencies by circulating supply times price, as published by "
        "CoinPaprika.",
        3,
    ),
    (
        "precious-metals",
        "Precious Metals",
        "Gold, silver, platinum and palladium, as futures and as the funds that hold the "
        "metal. Used here as the non risk asset comparison against the AI trade.",
        4,
    ),
    (
        "industrial-metals",
        "Industrial Metals",
        "Copper, as futures and as the funds and miners that track it. Separated from the "
        "precious metals because the two answer different questions: copper is read as a "
        "demand gauge for building things, and the peer median of a group holding both would "
        "describe neither.",
        12,
    ),
    (
        "energy-commodities",
        "Energy Commodities",
        "Crude oil and natural gas futures. The commodity itself, where the Energy group is "
        "the listed companies that produce it -- a refiner's share price and the barrel it "
        "refines move together often enough to be compared and not often enough to be pooled.",
        13,
    ),
    (
        "energy",
        "Energy",
        "Integrated oil, gas and refining. The cost side of data centre power demand.",
        5,
    ),
    (
        "healthcare",
        "Healthcare and Biotech",
        "Large pharmaceutical, biotech and medical device companies.",
        6,
    ),
    (
        "financials",
        "Banks and Financials",
        "Large US banks, asset managers and payments companies.",
        7,
    ),
    (
        "automobile",
        "Automobile",
        "Global vehicle makers and the suppliers underneath them, from legacy volume "
        "manufacturers to the electric only names.",
        8,
    ),
    (
        "software-cloud",
        "Software and Cloud",
        "Enterprise software and the infrastructure it runs on. Separate from Mega Cap "
        "Tech, which is dominated by hardware and advertising revenue.",
        9,
    ),
]

# The Pakistan Stock Exchange sectors, using the exchange's own sector groupings.
#
# These are separate industries rather than extra rows in the existing ones, and that is
# deliberate. Every ranking on this site is computed inside one industry, so keeping PSX
# apart means a rupee size figure is never sorted against a dollar one. Returns are
# percentages and would compare, but a return computed in a depreciating currency is not
# the same quantity as one computed in a stable one, and the methodology page says so.
PSX_MARKET = "PK"
PKR = "PKR"
PSX_INDUSTRIES = [
    (
        "psx-banks",
        "PSX Banks",
        "The largest commercial banks listed in Karachi. The most heavily traded sector "
        "on the exchange and the one most directly exposed to the policy rate.",
        20,
    ),
    (
        "psx-oil-gas",
        "PSX Oil and Gas",
        "Exploration, marketing and refining. Priced in rupees against a dollar "
        "denominated commodity, so the currency shows up in the returns.",
        21,
    ),
    (
        "psx-cement",
        "PSX Cement",
        "Cement makers, read locally as the clearest listed proxy for construction and "
        "public development spending.",
        22,
    ),
    (
        "psx-fertilizer",
        "PSX Fertilizer",
        "Fertilizer producers. A small field of five listings, which is itself a limit "
        "on how much a ranking within it can say.",
        23,
    ),
    (
        "psx-power",
        "PSX Power",
        "Independent power producers and distribution. Earnings here turn on tariff and "
        "receivable settlement rather than on demand alone.",
        24,
    ),
    (
        "psx-technology",
        "PSX Technology and Communication",
        "Listed IT services, software exporters and telecoms. The export earners in this "
        "sector bill in dollars and report in rupees.",
        25,
    ),
    (
        "psx-textile",
        "PSX Textile",
        "Composite textile manufacturers, Pakistan's largest export category.",
        26,
    ),
    (
        "psx-automobile",
        "PSX Automobile",
        "Vehicle and tractor assemblers. Almost entirely an import assembly business, so "
        "the sector tracks the import regime as much as local demand.",
        27,
    ),
]
FOREX_INDUSTRIES = [
    (
        "fx-majors",
        "Major currency pairs",
        "The seven most traded pairs plus the three euro and sterling crosses. These are the "
        "deepest markets in the world and the ones a rate decision moves first.",
        30,
    ),
    (
        "fx-asia",
        "Asian currencies",
        "The dollar against ten Asian currencies, including the rupee. Several are managed "
        "rather than floating, so a long flat stretch here is a policy choice and not a quiet "
        "market.",
        31,
    ),
    (
        # Seven pairs, and the count is the reason this is one group rather than two.
        #
        # It was "fx-emerging" (4: BRL, MXN, TRY, ZAR) and "fx-europe" (3: NOK, PLN, SEK), and
        # both sat under `MIN_PEERS` in jobs/factors.py -- 5, because "at three it *is* one
        # listing, which is a quote rather than an industry". So `relStrength` was null for all
        # seven, measured 2026-10-07. That is not a small loss for a currency pair: FX publishes
        # no volume anywhere, and `jobs/analogs.py` cannot match a day without a volume ratio, so
        # the peer reading is one of only **two** legs a pair can ever have. Those seven were left
        # with news tone alone, which reads directional for 2 of 27 pairs.
        #
        # Merging is the only repair that does not move a threshold: seven pairs cannot be split
        # into two groups of five, and lowering `MIN_PEERS` to fit them would make the median of a
        # three-name group a quote wearing an industry's name. What they genuinely share is the
        # thing the peer reading asks about -- the dollar against a currency outside the majors --
        # so the comparison is "is this pair moving more than the other non-major crosses", which
        # is a real question with a real answer.
        "fx-emerging",
        "USD against non-major currencies",
        "The dollar against seven currencies outside the majors, from the Scandinavian and "
        "central European pairs to the higher volatility ones. They are read together because "
        "the question a peer median answers here is whether a pair is moving more than the rest "
        "of the non-major crosses, not whether it is European.",
        32,
    ),
]

INDUSTRIES = INDUSTRIES + PSX_INDUSTRIES + FOREX_INDUSTRIES
INDUSTRIES = INDUSTRIES + [
    # --- 2026-10-08, second pass -----------------------------------------------------------
    #
    # Eleven US groups and six Karachi ones, and none of them is a category invented to hold a
    # name. Each exists because a measured, liquid field of names had nowhere to sit, and a
    # name filed into the wrong industry is worse than a name not covered: every peer median,
    # every relative-strength reading and every ranking on this site is computed inside one.
    #
    # The Karachi six are the exchange's own sector codes, taken from field three of its daily
    # closing file and only where at least five liquid symbols carry the code.
    (
        "chemicals-materials",
        "Chemicals and Materials",
        "Industrial gases, coatings and commodity chemicals. The input side of everything "
        "built or manufactured, which is why it reads differently from the companies that "
        "buy from it.",
        50,
    ),
    (
        "industrials",
        "Industrials",
        "Heavy equipment, electrical systems, automation and waste handling. Capital "
        "spending shows up here before it shows up in the companies doing the spending.",
        51,
    ),
    (
        "aerospace-defence",
        "Aerospace and Defence",
        "Airframes, engines and defence primes. Revenue here is set by government budgets "
        "and multi-year programmes rather than by a quarter's demand.",
        52,
    ),
    (
        "transport-logistics",
        "Transport and Logistics",
        "Railroads and parcel carriers. The physical movement of goods, read as a volume "
        "gauge rather than a consumer one.",
        53,
    ),
    (
        "real-estate",
        "Real Estate",
        "Listed property trusts: towers, warehouses, data centres, malls and net lease. "
        "Priced against the interest rate more directly than most equities.",
        54,
    ),
    (
        "retail",
        "Retail",
        "General merchandise, home improvement, grocery and off-price. What households "
        "actually spent, as reported by the companies they spent it with.",
        55,
    ),
    (
        "consumer-brands",
        "Consumer Brands",
        "Restaurants and branded apparel. Discretionary spending, and the first line to "
        "move when households stop stretching.",
        56,
    ),
    (
        "consumer-staples",
        "Consumer Staples",
        "Food, drink, household and tobacco. Bought in every condition, which is what makes "
        "the group a comparison rather than a bet.",
        57,
    ),
    (
        "media-telecom",
        "Media and Telecom",
        "Networks, carriers, studios and games. Subscription and advertising revenue in one "
        "group because the same budgets fund both.",
        58,
    ),
    (
        "insurance",
        "Insurance",
        "Property, casualty and life underwriters. Separated from Banks and Financials "
        "because an underwriter's result turns on claims and float, and pooling the two gave "
        "a peer median that described neither.",
        59,
    ),
    (
        "utilities",
        "Utilities",
        "Regulated electric and gas utilities. Rate-set revenue, which is why the group "
        "moves with the bond market more than with demand.",
        60,
    ),
    (
        "psx-chemicals",
        "PSX Chemicals and Paints",
        "Industrial chemicals, resins and coatings listed in Karachi. The exchange's own "
        "chemicals sector.",
        70,
    ),
    (
        "psx-steel",
        "PSX Steel and Engineering",
        "Long and flat steel producers and re-rollers. Left out of earlier batches for want "
        "of an industry; there are eight liquid names, which is a field rather than a pair.",
        71,
    ),
    (
        "psx-food",
        "PSX Food and Personal Care",
        "Dairy, poultry, edible oils, packaged food and household brands. The largest "
        "unrepresented sector on the exchange by listed count.",
        72,
    ),
    (
        "psx-investment",
        "PSX Investment and Securities",
        "Holding companies, brokerages and the exchange's own listing. This group is why "
        "the sector map needs three names behind a code before it trusts it: one holding "
        "company filed under Fertilizer had been teaching it that every brokerage here grew "
        "urea.",
        73,
    ),
    (
        "psx-pharma",
        "PSX Pharmaceuticals",
        "Listed drug makers and distributors. Input costs are dollar denominated and prices "
        "are regulated in rupees, so the currency shows up in the margin.",
        74,
    ),
    (
        "psx-spinning",
        "PSX Textile Spinning",
        "Yarn spinners, which the exchange files separately from the composite mills in PSX "
        "Textile. Kept apart here for the same reason it keeps them apart: a spinner sells "
        "yarn and a composite sells finished cloth.",
        75,
    ),
]

INDUSTRIES = INDUSTRIES + [
    (
        "precious-metal-miners",
        "Precious Metal Miners",
        "Listed gold and silver producers and the royalty companies that finance them. Kept "
        "apart from Precious Metals, which holds the metal itself: a miner is a levered claim "
        "on the same price with a cost base of its own, and pooling the two would give a peer "
        "median that describes neither.",
        14,
    ),
    (
        "base-metals-and-steel",
        "Base Metals and Steel",
        "Copper, iron ore, aluminium and steel producers. The listed companies that dig and "
        "make the material, where Industrial Metals is the copper price itself.",
        15,
    ),
]


# industry slug, symbol, name, type, cap basis, source, source ref, note
YAHOO = "yahoo"
BINANCE = "binance"
PAPRIKA = "coinpaprika"
EQUITY = "price times shares outstanding, Yahoo Finance"
FUNDSIZE = "fund size from price times shares outstanding, Yahoo Finance"
NONE_NOTE = "not applicable"

ASSETS: list[tuple] = [
    # Mega Cap Tech
    ("mega-cap-tech", "AAPL", "Apple", "stock", "marketCap", YAHOO, "AAPL", "Consumer devices, software and services."),
    ("mega-cap-tech", "MSFT", "Microsoft", "stock", "marketCap", YAHOO, "MSFT", "Windows, Office and Azure cloud."),
    ("mega-cap-tech", "NVDA", "NVIDIA", "stock", "marketCap", YAHOO, "NVDA", "Data centre GPUs and networking."),
    ("mega-cap-tech", "GOOGL", "Alphabet", "stock", "marketCap", YAHOO, "GOOGL", "Search, advertising and Google Cloud."),
    ("mega-cap-tech", "AMZN", "Amazon", "stock", "marketCap", YAHOO, "AMZN", "Online retail and AWS cloud."),
    ("mega-cap-tech", "META", "Meta Platforms", "stock", "marketCap", YAHOO, "META", "Social advertising and Llama models."),
    ("mega-cap-tech", "AVGO", "Broadcom", "stock", "marketCap", YAHOO, "AVGO", "Custom silicon and networking chips."),
    ("mega-cap-tech", "TSLA", "Tesla", "stock", "marketCap", YAHOO, "TSLA", "Electric vehicles and energy storage."),
    ("mega-cap-tech", "ORCL", "Oracle", "stock", "marketCap", YAHOO, "ORCL", "Database software and cloud infrastructure."),
    ("mega-cap-tech", "NFLX", "Netflix", "stock", "marketCap", YAHOO, "NFLX", "Subscription streaming."),
    # Semiconductors
    ("semiconductors", "TSM", "TSMC", "stock", "marketCap", YAHOO, "TSM", "Contract chip manufacturing."),
    ("semiconductors", "ASML", "ASML Holding", "stock", "marketCap", YAHOO, "ASML", "Lithography equipment for chip making."),
    ("semiconductors", "AMD", "Advanced Micro Devices", "stock", "marketCap", YAHOO, "AMD", "CPUs, GPUs and adaptive SoCs."),
    ("semiconductors", "INTC", "Intel", "stock", "marketCap", YAHOO, "INTC", "PC and server CPUs, foundry build out."),
    ("semiconductors", "MU", "Micron Technology", "stock", "marketCap", YAHOO, "MU", "DRAM and NAND memory."),
    ("semiconductors", "QCOM", "Qualcomm", "stock", "marketCap", YAHOO, "QCOM", "Mobile SoCs and RF components."),
    ("semiconductors", "ARM", "Arm Holdings", "stock", "marketCap", YAHOO, "ARM", "CPU architecture licensor."),
    ("semiconductors", "TXN", "Texas Instruments", "stock", "marketCap", YAHOO, "TXN", "Analog and embedded chips."),
    ("semiconductors", "LRCX", "Lam Research", "stock", "marketCap", YAHOO, "LRCX", "Wafer fabrication equipment."),
    ("semiconductors", "KLAC", "KLA Corporation", "stock", "marketCap", YAHOO, "KLAC", "Inspection and metrology equipment."),
    # Crypto
    ("crypto", "btc-bitcoin", "Bitcoin", "crypto", "marketCap", PAPRIKA, "btc-bitcoin", "Proof of work blockchain, fixed supply near 21 million."),
    ("crypto", "eth-ethereum", "Ethereum", "crypto", "marketCap", PAPRIKA, "eth-ethereum", "Smart contract platform, proof of stake."),
    ("crypto", "sol-solana", "Solana", "crypto", "marketCap", PAPRIKA, "sol-solana", "High throughput smart contract chain."),
    ("crypto", "xrp-xrp", "XRP", "crypto", "marketCap", PAPRIKA, "xrp-xrp", "Payments focused blockchain."),
    ("crypto", "bnb-binance-coin", "BNB", "crypto", "marketCap", PAPRIKA, "bnb-binance-coin", "Exchange token and chain fees."),
    ("crypto", "doge-dogecoin", "Dogecoin", "crypto", "marketCap", PAPRIKA, "doge-dogecoin", "Proof of work meme coin."),
    ("crypto", "ada-cardano", "Cardano", "crypto", "marketCap", PAPRIKA, "ada-cardano", "Proof of stake smart contract chain."),
    ("crypto", "link-chainlink", "Chainlink", "crypto", "marketCap", PAPRIKA, "link-chainlink", "Oracle network for off chain data."),
    ("crypto", "avax-avalanche", "Avalanche", "crypto", "marketCap", PAPRIKA, "avax-avalanche", "Smart contract chain."),
    ("crypto", "ltc-litecoin", "Litecoin", "crypto", "marketCap", PAPRIKA, "ltc-litecoin", "Proof of work payments chain."),
    # Precious Metals
    ("precious-metals", "GLD", "SPDR Gold Shares", "etf", "fundAssets", YAHOO, "GLD", "Gold backed fund, one share roughly one tenth of an ounce."),
    ("precious-metals", "IAU", "iShares Gold Trust", "etf", "fundAssets", YAHOO, "IAU", "Gold backed fund."),
    ("precious-metals", "SLV", "iShares Silver Trust", "etf", "fundAssets", YAHOO, "SLV", "Silver backed fund."),
    ("precious-metals", "SIVR", "abrdn Silver Shares", "etf", "fundAssets", YAHOO, "SIVR", "Silver backed fund."),
    ("precious-metals", "PPLT", "abrdn Physical Platinum", "etf", "fundAssets", YAHOO, "PPLT", "Physical platinum fund."),
    ("precious-metals", "PALL", "abrdn Physical Palladium", "etf", "fundAssets", YAHOO, "PALL", "Physical palladium fund."),
    ("precious-metals", "GC=F", "Gold futures", "commodity", "none", YAHOO, "GC=F", "Front month gold futures on COMEX."),
    ("precious-metals", "SI=F", "Silver futures", "commodity", "none", YAHOO, "SI=F", "Front month silver futures on COMEX."),
    ("precious-metals", "PL=F", "Platinum futures", "commodity", "none", YAHOO, "PL=F", "Front month platinum futures on NYMEX."),
    ("precious-metals", "PA=F", "Palladium futures", "commodity", "none", YAHOO, "PA=F", "Front month palladium futures on NYMEX."),
    # Industrial Metals. CPER and COPX moved here from `precious-metals`, where they had been
    # filed since the group was seeded. Copper is not a precious metal and the misfiling was not
    # cosmetic: `relStrength` compares a name against the median of its own industry, so copper
    # was being measured against gold and gold against copper. Both readings were noise, and
    # `REL_AGAINST_AT` can turn a noisy peer median into a `peers-against` WAIT.
    ("industrial-metals", "HG=F", "Copper futures", "commodity", "none", YAHOO, "HG=F", "Front month copper futures on COMEX."),
    ("industrial-metals", "CPER", "United States Copper Index Fund", "etf", "fundAssets", YAHOO, "CPER", "Copper futures based fund."),
    ("industrial-metals", "COPX", "Global X Copper Miners", "etf", "fundAssets", YAHOO, "COPX", "Global copper miner equities."),
    # Energy Commodities. The site had eight listed energy companies and no barrel of oil, so
    # the one input every one of them is priced off was the only thing not on it.
    ("energy-commodities", "CL=F", "WTI crude oil futures", "commodity", "none", YAHOO, "CL=F", "Front month West Texas Intermediate on NYMEX, the US benchmark."),
    ("energy-commodities", "BZ=F", "Brent crude oil futures", "commodity", "none", YAHOO, "BZ=F", "Front month Brent on ICE, the benchmark most of the world prices against."),
    ("energy-commodities", "NG=F", "Natural gas futures", "commodity", "none", YAHOO, "NG=F", "Front month Henry Hub natural gas on NYMEX."),
    # Energy
    ("energy", "XOM", "Exxon Mobil", "stock", "marketCap", YAHOO, "XOM", "Integrated oil and gas."),
    ("energy", "CVX", "Chevron", "stock", "marketCap", YAHOO, "CVX", "Integrated oil and gas."),
    ("energy", "COP", "ConocoPhillips", "stock", "marketCap", YAHOO, "COP", "Oil and gas exploration and production."),
    ("energy", "SLB", "SLB", "stock", "marketCap", YAHOO, "SLB", "Oilfield services."),
    ("energy", "OXY", "Occidental Petroleum", "stock", "marketCap", YAHOO, "OXY", "Oil and gas, chemicals, Midstream."),
    ("energy", "EOG", "EOG Resources", "stock", "marketCap", YAHOO, "EOG", "Oil and gas exploration and production."),
    ("energy", "PSX", "Phillips 66", "stock", "marketCap", YAHOO, "PSX", "Refining and midstream."),
    ("energy", "VLO", "Valero Energy", "stock", "marketCap", YAHOO, "VLO", "Oil refining."),
    ("energy", "MPC", "Marathon Petroleum", "stock", "marketCap", YAHOO, "MPC", "Refining and marketing."),
    ("energy", "SHEL", "Shell", "stock", "marketCap", YAHOO, "SHEL", "Integrated oil and gas, LNG."),
    # Healthcare
    ("healthcare", "LLY", "Eli Lilly", "stock", "marketCap", YAHOO, "LLY", "Incretin diabetes and obesity treatments."),
    ("healthcare", "NVO", "Novo Nordisk", "stock", "marketCap", YAHOO, "NVO", "Incretin diabetes and obesity treatments."),
    ("healthcare", "JNJ", "Johnson & Johnson", "stock", "marketCap", YAHOO, "JNJ", "Pharmaceuticals and medical devices."),
    ("healthcare", "MRK", "Merck", "stock", "marketCap", YAHOO, "MRK", "Pharmaceuticals, notably oncology."),
    ("healthcare", "ABBV", "AbbVie", "stock", "marketCap", YAHOO, "ABBV", "Pharmaceuticals and immunology."),
    ("healthcare", "ISRG", "Intuitive Surgical", "stock", "marketCap", YAHOO, "ISRG", "Robotic assisted surgery systems."),
    ("healthcare", "AMGN", "Amgen", "stock", "marketCap", YAHOO, "AMGN", "Biologics."),
    ("healthcare", "GILD", "Gilead Sciences", "stock", "marketCap", YAHOO, "GILD", "Antivirals, oncology and liver disease."),
    ("healthcare", "VRTX", "Vertex Pharmaceuticals", "stock", "marketCap", YAHOO, "VRTX", "Cystic fibrosis and rare disease drugs."),
    ("healthcare", "DHR", "Danaher", "stock", "marketCap", YAHOO, "DHR", "Life science tools and diagnostics."),
    # Financials
    ("financials", "JPM", "JPMorgan Chase", "stock", "marketCap", YAHOO, "JPM", "Bank, investment banking and asset management."),
    ("financials", "BAC", "Bank of America", "stock", "marketCap", YAHOO, "BAC", "Bank and consumer lending."),
    ("financials", "GS", "Goldman Sachs", "stock", "marketCap", YAHOO, "GS", "Investment banking and markets."),
    ("financials", "MS", "Morgan Stanley", "stock", "marketCap", YAHOO, "MS", "Investment banking, wealth and asset management."),
    ("financials", "WFC", "Wells Fargo", "stock", "marketCap", YAHOO, "WFC", "Bank and consumer lending."),
    ("financials", "C", "Citigroup", "stock", "marketCap", YAHOO, "C", "Bank and consumer lending."),
    ("financials", "BLK", "BlackRock", "stock", "marketCap", YAHOO, "BLK", "Asset management."),
    ("financials", "SCHW", "Charles Schwab", "stock", "marketCap", YAHOO, "SCHW", "Retail brokerage and custody."),
    ("financials", "AXP", "American Express", "stock", "marketCap", YAHOO, "AXP", "Card issuing and merchant acquiring."),
    # An underwriter among banks. Moved to Insurance now that there is a field of them.
    ("insurance", "PGR", "The Progressive", "stock", "marketCap", YAHOO, "PGR", "Auto and property insurance."),
    # Automobile. Tesla is not repeated here even though it is a car maker: it already sits
    # in Mega Cap Tech, and listing one asset in two industries would put it in two
    # rankings, two industry averages and two news feeds, so its peers would be compared
    # against an average it had helped set twice.
    ("automobile", "TM", "Toyota Motor", "stock", "marketCap", YAHOO, "TM", "The largest vehicle maker by unit volume, hybrid led."),
    ("automobile", "GM", "General Motors", "stock", "marketCap", YAHOO, "GM", "US volume manufacturer, trucks and an electric line."),
    ("automobile", "F", "Ford Motor", "stock", "marketCap", YAHOO, "F", "US volume manufacturer with a separate electric division."),
    ("automobile", "STLA", "Stellantis", "stock", "marketCap", YAHOO, "STLA", "Fourteen brand group formed from Fiat Chrysler and PSA."),
    ("automobile", "HMC", "Honda Motor", "stock", "marketCap", YAHOO, "HMC", "Vehicles and the largest motorcycle business in the world."),
    ("automobile", "RIVN", "Rivian Automotive", "stock", "marketCap", YAHOO, "RIVN", "Electric trucks, vans and delivery fleets."),
    ("automobile", "LCID", "Lucid Group", "stock", "marketCap", YAHOO, "LCID", "Electric saloons and powertrain supply."),
    ("automobile", "RACE", "Ferrari", "stock", "marketCap", YAHOO, "RACE", "Low volume performance cars, priced as a luxury brand."),
    ("automobile", "APTV", "Aptiv", "stock", "marketCap", YAHOO, "APTV", "Vehicle electrical architecture and software."),
    ("automobile", "BWA", "BorgWarner", "stock", "marketCap", YAHOO, "BWA", "Drivetrain and electrification components."),
    # Software and Cloud. Microsoft and Oracle stay in Mega Cap Tech for the same reason
    # Tesla is not duplicated above.
    ("software-cloud", "CRM", "Salesforce", "stock", "marketCap", YAHOO, "CRM", "Customer relationship software and its platform."),
    ("software-cloud", "NOW", "ServiceNow", "stock", "marketCap", YAHOO, "NOW", "Enterprise workflow automation."),
    ("software-cloud", "ADBE", "Adobe", "stock", "marketCap", YAHOO, "ADBE", "Creative, document and marketing software."),
    ("software-cloud", "INTU", "Intuit", "stock", "marketCap", YAHOO, "INTU", "Tax, accounting and small business software."),
    ("software-cloud", "PANW", "Palo Alto Networks", "stock", "marketCap", YAHOO, "PANW", "Network and cloud security platforms."),
    ("software-cloud", "SNOW", "Snowflake", "stock", "marketCap", YAHOO, "SNOW", "Cloud data warehousing, consumption priced."),
    ("software-cloud", "PLTR", "Palantir Technologies", "stock", "marketCap", YAHOO, "PLTR", "Data integration and analysis platforms."),
    ("software-cloud", "WDAY", "Workday", "stock", "marketCap", YAHOO, "WDAY", "Human resources and finance software."),
    ("software-cloud", "DDOG", "Datadog", "stock", "marketCap", YAHOO, "DDOG", "Infrastructure and application monitoring."),
    ("software-cloud", "MDB", "MongoDB", "stock", "marketCap", YAHOO, "MDB", "Document database, self hosted and managed."),
]

# Pakistan Stock Exchange listings.
#
# Every symbol below was checked against the exchange's own closing file for 2026-09-30 and
# again for 2021-12-31, so each one exists today and has a pre-AI reading to compare with.
#
# Size is market capitalisation, but only against the most recent close. The share count on
# the exchange's company page is a current figure with no history behind it, so jobs/psx.py
# writes no size for any earlier date rather than multiplying today's share count by an old
# price. The pre-AI size table therefore shows these sectors as having no figure, which is
# true, rather than a figure nobody ever published.
PSX = "psx"

PSX_ASSETS: list[tuple] = [
    ("psx-banks", "HBL", "Habib Bank", "stock", "marketCap", PSX, "HBL", "The largest bank by assets, with an international network."),
    ("psx-banks", "UBL", "United Bank", "stock", "marketCap", PSX, "UBL", "Commercial and consumer banking, large government paper holdings."),
    ("psx-banks", "MCB", "MCB Bank", "stock", "marketCap", PSX, "MCB", "Commercial bank with a long dividend record."),
    ("psx-banks", "MEBL", "Meezan Bank", "stock", "marketCap", PSX, "MEBL", "The largest Islamic bank in the country."),
    ("psx-banks", "BAFL", "Bank Alfalah", "stock", "marketCap", PSX, "BAFL", "Commercial and consumer banking."),
    ("psx-banks", "BAHL", "Bank AL Habib", "stock", "marketCap", PSX, "BAHL", "Trade finance and commercial banking."),
    ("psx-banks", "NBP", "National Bank of Pakistan", "stock", "marketCap", PSX, "NBP", "State owned commercial bank and government agent."),
    ("psx-banks", "ABL", "Allied Bank", "stock", "marketCap", PSX, "ABL", "Commercial bank, Ibrahim group."),
    ("psx-banks", "AKBL", "Askari Bank", "stock", "marketCap", PSX, "AKBL", "Commercial bank, Fauji Foundation controlled."),
    ("psx-banks", "FABL", "Faysal Bank", "stock", "marketCap", PSX, "FABL", "Converted to full Islamic banking operations."),

    ("psx-oil-gas", "OGDC", "Oil and Gas Development Company", "stock", "marketCap", PSX, "OGDC", "The largest exploration and production company, state majority owned."),
    ("psx-oil-gas", "PPL", "Pakistan Petroleum", "stock", "marketCap", PSX, "PPL", "Exploration and production, gas weighted."),
    ("psx-oil-gas", "POL", "Pakistan Oilfields", "stock", "marketCap", PSX, "POL", "Exploration and production, Attock group."),
    ("psx-oil-gas", "MARI", "Mari Energies", "stock", "marketCap", PSX, "MARI", "Gas producer centred on the Mari field."),
    ("psx-oil-gas", "PSO", "Pakistan State Oil", "stock", "marketCap", PSX, "PSO", "The largest fuel marketing company, state majority owned."),
    ("psx-oil-gas", "APL", "Attock Petroleum", "stock", "marketCap", PSX, "APL", "Fuel marketing and lubricants."),
    ("psx-oil-gas", "SNGP", "Sui Northern Gas Pipelines", "stock", "marketCap", PSX, "SNGP", "Gas transmission and distribution in the north."),
    ("psx-oil-gas", "SSGC", "Sui Southern Gas Company", "stock", "marketCap", PSX, "SSGC", "Gas transmission and distribution in the south."),
    ("psx-oil-gas", "ATRL", "Attock Refinery", "stock", "marketCap", PSX, "ATRL", "Crude refining, Attock group."),
    ("psx-oil-gas", "HTL", "Hi-Tech Lubricants", "stock", "marketCap", PSX, "HTL", "Lubricant blending and retail fuel."),

    ("psx-cement", "LUCK", "Lucky Cement", "stock", "marketCap", PSX, "LUCK", "The largest cement maker, with holdings outside cement."),
    ("psx-cement", "DGKC", "D.G. Khan Cement", "stock", "marketCap", PSX, "DGKC", "Cement, Nishat group."),
    ("psx-cement", "MLCF", "Maple Leaf Cement", "stock", "marketCap", PSX, "MLCF", "Cement, Kohinoor Maple Leaf group."),
    ("psx-cement", "FCCL", "Fauji Cement", "stock", "marketCap", PSX, "FCCL", "Cement, Fauji Foundation controlled."),
    ("psx-cement", "CHCC", "Cherat Cement", "stock", "marketCap", PSX, "CHCC", "Cement, Ghulam Faruque group."),
    ("psx-cement", "KOHC", "Kohat Cement", "stock", "marketCap", PSX, "KOHC", "Cement producer in the north west."),
    ("psx-cement", "PIOC", "Pioneer Cement", "stock", "marketCap", PSX, "PIOC", "Cement producer in central Punjab."),
    ("psx-cement", "ACPL", "Attock Cement", "stock", "marketCap", PSX, "ACPL", "Cement, Attock group, export exposed."),
    ("psx-cement", "BWCL", "Bestway Cement", "stock", "marketCap", PSX, "BWCL", "One of the largest producers by capacity."),
    ("psx-cement", "GWLC", "Gharibwal Cement", "stock", "marketCap", PSX, "GWLC", "Cement producer in central Punjab."),

    ("psx-fertilizer", "FFC", "Fauji Fertilizer", "stock", "marketCap", PSX, "FFC", "The largest urea producer."),
    ("psx-fertilizer", "EFERT", "Engro Fertilizers", "stock", "marketCap", PSX, "EFERT", "Urea and phosphate fertilizers."),
    ("psx-fertilizer", "FATIMA", "Fatima Fertilizer", "stock", "marketCap", PSX, "FATIMA", "Urea, CAN and NP fertilizers."),
    ("psx-fertilizer", "AGL", "Agritech", "stock", "marketCap", PSX, "AGL", "Urea producer, repeatedly gas supply constrained."),
    ("psx-fertilizer", "AHCL", "Arif Habib Corporation", "stock", "marketCap", PSX, "AHCL", "Holding company the exchange classifies in this sector."),

    ("psx-power", "HUBC", "Hub Power", "stock", "marketCap", PSX, "HUBC", "The largest independent power producer."),
    ("psx-power", "KAPCO", "Kot Addu Power", "stock", "marketCap", PSX, "KAPCO", "Thermal generation, post concession."),
    ("psx-power", "KEL", "K-Electric", "stock", "marketCap", PSX, "KEL", "Generation and distribution for Karachi."),
    ("psx-power", "NCPL", "Nishat Chunian Power", "stock", "marketCap", PSX, "NCPL", "Furnace oil generation, Nishat group."),
    ("psx-power", "NPL", "Nishat Power", "stock", "marketCap", PSX, "NPL", "Furnace oil generation, Nishat group."),
    ("psx-power", "ALTN", "Altern Energy", "stock", "marketCap", PSX, "ALTN", "Gas fired generation."),
    ("psx-power", "PKGP", "Pakgen Power", "stock", "marketCap", PSX, "PKGP", "Thermal generation, Nishat group."),
    ("psx-power", "TSPL", "Tri-Star Power", "stock", "marketCap", PSX, "TSPL", "Small independent generation."),

    ("psx-technology", "SYS", "Systems Limited", "stock", "marketCap", PSX, "SYS", "IT services and software, largely exported."),
    ("psx-technology", "NETSOL", "NetSol Technologies", "stock", "marketCap", PSX, "NETSOL", "Leasing and finance software for global lenders."),
    ("psx-technology", "TRG", "TRG Pakistan", "stock", "marketCap", PSX, "TRG", "Holding company for business process outsourcing."),
    ("psx-technology", "AVN", "Avanceon", "stock", "marketCap", PSX, "AVN", "Industrial automation and control systems."),
    ("psx-technology", "PTC", "Pakistan Telecommunication", "stock", "marketCap", PSX, "PTC", "Fixed line, broadband and the Ufone mobile network."),
    ("psx-technology", "TELE", "Telecard", "stock", "marketCap", PSX, "TELE", "Telecom services and infrastructure."),
    ("psx-technology", "AIRLINK", "Air Link Communication", "stock", "marketCap", PSX, "AIRLINK", "Mobile phone distribution and local assembly."),
    ("psx-technology", "TPL", "TPL Corp", "stock", "marketCap", PSX, "TPL", "Holding company across tracking, insurance and property."),
    ("psx-technology", "HUMNL", "Hum Network", "stock", "marketCap", PSX, "HUMNL", "Television broadcasting and content."),
    ("psx-technology", "WTL", "WorldCall Telecom", "stock", "marketCap", PSX, "WTL", "Broadband and telecom services, heavily traded at a very low price."),

    ("psx-textile", "NML", "Nishat Mills", "stock", "marketCap", PSX, "NML", "The largest composite textile manufacturer."),
    ("psx-textile", "GATM", "Gul Ahmed Textile Mills", "stock", "marketCap", PSX, "GATM", "Composite textiles and domestic retail."),
    ("psx-textile", "ILP", "Interloop", "stock", "marketCap", PSX, "ILP", "Hosiery and apparel, export led."),
    ("psx-textile", "NCL", "Nishat Chunian", "stock", "marketCap", PSX, "NCL", "Spinning and home textiles."),
    ("psx-textile", "KTML", "Kohinoor Textile Mills", "stock", "marketCap", PSX, "KTML", "Composite textiles, also holds cement interests."),
    ("psx-textile", "ANL", "Azgard Nine", "stock", "marketCap", PSX, "ANL", "Denim and apparel manufacturing."),
    ("psx-textile", "KOIL", "Kohinoor Industries", "stock", "marketCap", PSX, "KOIL", "Textile manufacturing."),
    ("psx-textile", "TOWL", "Towellers", "stock", "marketCap", PSX, "TOWL", "Towel manufacturing, export led."),

    ("psx-automobile", "INDU", "Indus Motor Company", "stock", "marketCap", PSX, "INDU", "Assembles Toyota vehicles under licence."),
    ("psx-automobile", "HCAR", "Honda Atlas Cars", "stock", "marketCap", PSX, "HCAR", "Assembles Honda vehicles under licence."),
    ("psx-automobile", "MTL", "Millat Tractors", "stock", "marketCap", PSX, "MTL", "Tractor assembly, Massey Ferguson licence."),
    ("psx-automobile", "AGTL", "Al-Ghazi Tractors", "stock", "marketCap", PSX, "AGTL", "Tractor assembly, New Holland licence."),
    ("psx-automobile", "SAZEW", "Sazgar Engineering", "stock", "marketCap", PSX, "SAZEW", "Three wheelers and, more recently, hybrid vehicles."),
    ("psx-automobile", "GHNI", "Ghandhara Industries", "stock", "marketCap", PSX, "GHNI", "Commercial vehicle assembly."),
    ("psx-automobile", "ATLH", "Atlas Honda", "stock", "marketCap", PSX, "ATLH", "Motorcycle assembly, the largest by volume."),
    ("psx-automobile", "HINO", "Hinopak Motors", "stock", "marketCap", PSX, "HINO", "Truck and bus assembly."),
    ("psx-automobile", "DFML", "Dewan Farooque Motors", "stock", "marketCap", PSX, "DFML", "Vehicle assembly, intermittently operating."),
]

# --- expansion, 2026-10-04 ------------------------------------------------------------------
#
# Every symbol here was verified against its own source before being written down, and the
# verification is why this list is this length rather than longer. For Yahoo: at least 200 daily
# bars in the last year and at least $50M of median daily turnover, which dropped HES and BK (no
# frame returned at all) and GT and HOG (around $45-50M, too thin to rank honestly inside an
# industry). For crypto: present on CoinPaprika, Binance actually serving daily klines for
# <SYM>USDT, and over $20M of 24h volume -- which dropped Polkadot (not carried under that id),
# MATIC (a $17K day, effectively dead) and VET.
#
# Names were chosen inside the industries that already exist rather than by inventing new ones.
# Every ranking on this site is computed inside one industry, so a thinly populated new category
# would produce rankings of three names against each other. The eighteen industries were all
# sitting at or below ten.
#
# PSX is deliberately absent. Its symbols cannot be checked the same way: the daily closing
# archive is the only list of what actually trades, and a PSX name guessed from memory that is
# not in those files becomes an asset that can never price. It needs the archive parsed first.
MORE_US: list[tuple] = [
    ("mega-cap-tech", "IBM", "IBM", "stock", "marketCap", YAHOO, "IBM", "Enterprise software, consulting and mainframes."),
    ("mega-cap-tech", "CSCO", "Cisco Systems", "stock", "marketCap", YAHOO, "CSCO", "Networking hardware and security."),
    ("mega-cap-tech", "ACN", "Accenture", "stock", "marketCap", YAHOO, "ACN", "Technology consulting and outsourcing."),
    ("mega-cap-tech", "SAP", "SAP", "stock", "marketCap", YAHOO, "SAP", "Enterprise resource planning software."),
    ("mega-cap-tech", "UBER", "Uber Technologies", "stock", "marketCap", YAHOO, "UBER", "Ride hailing and delivery platforms."),
    ("mega-cap-tech", "BKNG", "Booking Holdings", "stock", "marketCap", YAHOO, "BKNG", "Online travel agencies and accommodation."),

    ("semiconductors", "ADI", "Analog Devices", "stock", "marketCap", YAHOO, "ADI", "Analog and mixed signal chips."),
    ("semiconductors", "NXPI", "NXP Semiconductors", "stock", "marketCap", YAHOO, "NXPI", "Automotive and industrial chips."),
    ("semiconductors", "MRVL", "Marvell Technology", "stock", "marketCap", YAHOO, "MRVL", "Data centre and networking silicon."),
    ("semiconductors", "ON", "ON Semiconductor", "stock", "marketCap", YAHOO, "ON", "Power and sensing chips, automotive weighted."),
    ("semiconductors", "SWKS", "Skyworks Solutions", "stock", "marketCap", YAHOO, "SWKS", "Radio frequency chips for handsets."),
    ("semiconductors", "MCHP", "Microchip Technology", "stock", "marketCap", YAHOO, "MCHP", "Microcontrollers and embedded control."),
    ("semiconductors", "AMAT", "Applied Materials", "stock", "marketCap", YAHOO, "AMAT", "Wafer fabrication equipment."),
    ("semiconductors", "TER", "Teradyne", "stock", "marketCap", YAHOO, "TER", "Semiconductor test equipment and robotics."),

    ("software-cloud", "SHOP", "Shopify", "stock", "marketCap", YAHOO, "SHOP", "Commerce software for online merchants."),
    ("software-cloud", "NET", "Cloudflare", "stock", "marketCap", YAHOO, "NET", "Edge network, security and delivery."),
    ("software-cloud", "TEAM", "Atlassian", "stock", "marketCap", YAHOO, "TEAM", "Developer and team collaboration tools."),
    ("software-cloud", "ZS", "Zscaler", "stock", "marketCap", YAHOO, "ZS", "Cloud delivered network security."),
    ("software-cloud", "CRWD", "CrowdStrike", "stock", "marketCap", YAHOO, "CRWD", "Endpoint security delivered from the cloud."),
    ("software-cloud", "SNPS", "Synopsys", "stock", "marketCap", YAHOO, "SNPS", "Chip design software and verification."),
    ("software-cloud", "CDNS", "Cadence Design Systems", "stock", "marketCap", YAHOO, "CDNS", "Electronic design automation software."),

    ("energy", "HAL", "Halliburton", "stock", "marketCap", YAHOO, "HAL", "Oilfield services and completions."),
    ("energy", "DVN", "Devon Energy", "stock", "marketCap", YAHOO, "DVN", "Onshore exploration and production."),
    ("energy", "BKR", "Baker Hughes", "stock", "marketCap", YAHOO, "BKR", "Oilfield equipment and industrial turbines."),
    ("energy", "FANG", "Diamondback Energy", "stock", "marketCap", YAHOO, "FANG", "Permian basin exploration and production."),
    ("energy", "KMI", "Kinder Morgan", "stock", "marketCap", YAHOO, "KMI", "Natural gas pipelines and terminals."),
    ("energy", "WMB", "Williams Companies", "stock", "marketCap", YAHOO, "WMB", "Natural gas gathering and transmission."),
    ("energy", "OKE", "ONEOK", "stock", "marketCap", YAHOO, "OKE", "Natural gas liquids gathering and processing."),

    ("financials", "V", "Visa", "stock", "marketCap", YAHOO, "V", "Card payment network."),
    ("financials", "MA", "Mastercard", "stock", "marketCap", YAHOO, "MA", "Card payment network."),
    ("financials", "USB", "U.S. Bancorp", "stock", "marketCap", YAHOO, "USB", "Regional commercial and consumer banking."),
    ("financials", "PNC", "PNC Financial Services", "stock", "marketCap", YAHOO, "PNC", "Regional commercial banking."),
    ("financials", "TFC", "Truist Financial", "stock", "marketCap", YAHOO, "TFC", "Regional commercial and consumer banking."),
    ("financials", "COF", "Capital One", "stock", "marketCap", YAHOO, "COF", "Card issuing and consumer lending."),
    ("financials", "SPGI", "S&P Global", "stock", "marketCap", YAHOO, "SPGI", "Credit ratings, indices and market data."),

    ("healthcare", "PFE", "Pfizer", "stock", "marketCap", YAHOO, "PFE", "Large cap pharmaceuticals and vaccines."),
    ("healthcare", "UNH", "UnitedHealth Group", "stock", "marketCap", YAHOO, "UNH", "Health insurance and care delivery."),
    ("healthcare", "TMO", "Thermo Fisher Scientific", "stock", "marketCap", YAHOO, "TMO", "Laboratory instruments and reagents."),
    ("healthcare", "BMY", "Bristol-Myers Squibb", "stock", "marketCap", YAHOO, "BMY", "Oncology and immunology pharmaceuticals."),
    ("healthcare", "REGN", "Regeneron Pharmaceuticals", "stock", "marketCap", YAHOO, "REGN", "Antibody therapeutics."),
    ("healthcare", "CVS", "CVS Health", "stock", "marketCap", YAHOO, "CVS", "Pharmacy retail, benefits management and insurance."),
    ("healthcare", "MDT", "Medtronic", "stock", "marketCap", YAHOO, "MDT", "Medical devices across cardiac and surgical."),
    ("healthcare", "SYK", "Stryker", "stock", "marketCap", YAHOO, "SYK", "Orthopaedic implants and surgical equipment."),
    ("healthcare", "BSX", "Boston Scientific", "stock", "marketCap", YAHOO, "BSX", "Interventional medical devices."),

    ("automobile", "PCAR", "PACCAR", "stock", "marketCap", YAHOO, "PCAR", "Heavy truck manufacturing and finance."),
    ("automobile", "CMI", "Cummins", "stock", "marketCap", YAHOO, "CMI", "Engines, generators and powertrain."),
    ("automobile", "MGA", "Magna International", "stock", "marketCap", YAHOO, "MGA", "Contract vehicle assembly and parts."),
    ("automobile", "LEA", "Lear", "stock", "marketCap", YAHOO, "LEA", "Vehicle seating and electrical systems."),
]

MORE_CRYPTO: list[tuple] = [
    ("crypto", "trx-tron", "TRON", "crypto", "marketCap", PAPRIKA, "trx-tron", "Smart contract chain, stablecoin transfer heavy."),
    ("crypto", "xlm-stellar", "Stellar", "crypto", "marketCap", PAPRIKA, "xlm-stellar", "Payments and asset issuance network."),
    ("crypto", "bch-bitcoin-cash", "Bitcoin Cash", "crypto", "marketCap", PAPRIKA, "bch-bitcoin-cash", "Proof of work payments chain, a Bitcoin fork."),
    ("crypto", "near-near-protocol", "NEAR Protocol", "crypto", "marketCap", PAPRIKA, "near-near-protocol", "Sharded proof of stake smart contract chain."),
    ("crypto", "uni-uniswap", "Uniswap", "crypto", "marketCap", PAPRIKA, "uni-uniswap", "Decentralised exchange governance token."),
    ("crypto", "sui-sui", "Sui", "crypto", "marketCap", PAPRIKA, "sui-sui", "Parallel execution smart contract chain."),
    ("crypto", "hbar-hedera-hashgraph", "Hedera", "crypto", "marketCap", PAPRIKA, "hbar-hedera-hashgraph", "Enterprise governed public ledger."),
    ("crypto", "aave-new", "Aave", "crypto", "marketCap", PAPRIKA, "aave-new", "Lending and borrowing protocol token."),
    ("crypto", "icp-internet-computer", "Internet Computer", "crypto", "marketCap", PAPRIKA, "icp-internet-computer", "Chain hosting web applications directly."),
    ("crypto", "etc-ethereum-classic", "Ethereum Classic", "crypto", "marketCap", PAPRIKA, "etc-ethereum-classic", "Proof of work chain, the original Ethereum fork."),
    ("crypto", "arb-arbitrum", "Arbitrum", "crypto", "marketCap", PAPRIKA, "arb-arbitrum", "Ethereum rollup scaling network."),
    ("crypto", "algo-algorand", "Algorand", "crypto", "marketCap", PAPRIKA, "algo-algorand", "Pure proof of stake chain."),
    ("crypto", "fil-filecoin", "Filecoin", "crypto", "marketCap", PAPRIKA, "fil-filecoin", "Decentralised storage market."),
    ("crypto", "inj-injective-protocol", "Injective", "crypto", "marketCap", PAPRIKA, "inj-injective-protocol", "Chain built for on chain finance."),
    ("crypto", "apt-aptos", "Aptos", "crypto", "marketCap", PAPRIKA, "apt-aptos", "Parallel execution smart contract chain."),
    ("crypto", "atom-cosmos", "Cosmos", "crypto", "marketCap", PAPRIKA, "atom-cosmos", "Interchain hub and staking token."),
    ("crypto", "op-optimism", "Optimism", "crypto", "marketCap", PAPRIKA, "op-optimism", "Ethereum rollup scaling network."),
]

ASSETS = ASSETS + PSX_ASSETS + MORE_US + MORE_CRYPTO

# PSX, chosen from the exchange's own published closing files rather than from memory.
#
# Fifteen trading days of `mkt_summary` were parsed and every symbol ranked by average daily
# turnover. That list is not a list of shares: government paper (P01GIS..., P03GHS..., P05FRR...)
# dominates it by orders of magnitude, and every underlying also carries a futures contract per
# month (PRL-SEP, OGDC-OCTB, TRG-OCT) which would double-count a name whose cash symbol is
# already here. Both classes were filtered out. What remains are equities that printed a close on
# all fifteen sessions with real turnover behind them, and each one is placed in an industry that
# already exists — none of these needed a new category invented for it.
#
# Steel and engineering (ASL, ASTL, MUGHAL) are liquid and are deliberately left out: there is no
# industry here for them, and a two-name industry produces rankings of two names against each
# other. The same goes for Pak Elektron, the terminals and the property names.
MORE_PSX: list[tuple] = [
    ("psx-oil-gas", "PRL", "Pakistan Refinery", "stock", "marketCap", PSX, "PRL", "Coastal refinery, upgrading to deeper conversion."),
    ("psx-oil-gas", "NRL", "National Refinery", "stock", "marketCap", PSX, "NRL", "Refining and lube base oils, Attock group."),
    ("psx-oil-gas", "CNERGY", "Cnergyico PK", "stock", "marketCap", PSX, "CNERGY", "The largest refining capacity by nameplate."),
    ("psx-oil-gas", "HASCOL", "Hascol Petroleum", "stock", "marketCap", PSX, "HASCOL", "Fuel retail and storage."),
    ("psx-oil-gas", "SPSL", "Sitara Petroleum", "stock", "marketCap", PSX, "SPSL", "Petroleum refining and marketing."),

    ("psx-banks", "BOP", "Bank of Punjab", "stock", "marketCap", PSX, "BOP", "Provincial government majority owned commercial bank."),

    ("psx-automobile", "GAL", "Ghandhara Automobile", "stock", "marketCap", PSX, "GAL", "Vehicle assembly and distribution."),

    # Re-filed into PSX Investment and Securities, which is the exchange's own sector for
    # it. It sat in Fertilizer, and because the sector map is learned from where names
    # already sit, this one row was teaching it that every brokerage in Karachi was a
    # fertilizer producer. seed.py moves a name within one market by UPDATE, so the row
    # keeps its id and every close, setup and decision attached to it.
    ("psx-investment", "ENGROH", "Engro Holdings", "stock", "marketCap", PSX, "ENGROH", "Holding company of the Engro fertilizer and energy group."),

    ("psx-cement", "THCCL", "Thatta Cement", "stock", "marketCap", PSX, "THCCL", "Cement manufacturer in southern Sindh."),

    ("psx-power", "SGPL", "S.G. Power", "stock", "marketCap", PSX, "SGPL", "Independent power generation."),

    ("psx-technology", "TISL", "Tasdeeq Information Services", "stock", "marketCap", PSX, "TISL", "Credit information and data services."),
    ("psx-technology", "SELECT", "Select Technologies", "stock", "marketCap", PSX, "SELECT", "Information technology services."),
    ("psx-technology", "STL", "Supernet Technologies", "stock", "marketCap", PSX, "STL", "Network and satellite connectivity services."),
    ("psx-technology", "ITANZ", "Itanz Technologies", "stock", "marketCap", PSX, "ITANZ", "Information technology products and services."),

    # A spinner, which the exchange files apart from the composite mills that make up the
    # rest of PSX Textile.
    ("psx-spinning", "KOSM", "Kohinoor Spinning", "stock", "marketCap", PSX, "KOSM", "Yarn spinning and textile manufacture."),
]

ASSETS = ASSETS + MORE_PSX


# industry slug, symbol, name, type, cap basis, source, source ref, note
#
# Every pair below was requested from Yahoo before it was written here: 1300 daily bars
# each, five years, full OHLC, newest close present. Three further candidates were checked
# and dropped rather than carried -- USDAED and USDSAR are hard pegs to the dollar and
# USDHKD is a tight band peg, so ranking them by return would be ranking noise against
# noise.
#
# capBasis is `none` for all of them. A currency pair has no issuer and no share count, so
# there is no size to compute: the size tables on these industry pages hold no rows by
# construction, which the page already states in words rather than printing a zero.
#
# source is `yahoo`, which is not a new integration. `yahoo_assets` in jobs/prices.py selects
# on source = 'yahoo' and never on assetType, so these ride the existing fetch, the existing
# rate limit and the existing disk cache.
FOREX_ASSETS: list[tuple] = [
    ("fx-majors", "EURUSD", "Euro / US Dollar", "forex", "none", "yahoo", "EURUSD=X",
     "The most traded pair in the world. A rise means the euro is stronger against the dollar."),
    ("fx-majors", "GBPUSD", "British Pound / US Dollar", "forex", "none", "yahoo", "GBPUSD=X",
     "A rise means sterling is stronger against the dollar."),
    ("fx-majors", "USDJPY", "US Dollar / Japanese Yen", "forex", "none", "yahoo", "USDJPY=X",
     "Yen per dollar. A rise means the yen is weaker."),
    ("fx-majors", "USDCHF", "US Dollar / Swiss Franc", "forex", "none", "yahoo", "USDCHF=X",
     "Francs per dollar. The franc is a haven, so this often falls when equities do."),
    ("fx-majors", "USDCAD", "US Dollar / Canadian Dollar", "forex", "none", "yahoo", "USDCAD=X",
     "Canadian dollars per US dollar. Moves with crude."),
    ("fx-majors", "AUDUSD", "Australian Dollar / US Dollar", "forex", "none", "yahoo", "AUDUSD=X",
     "A rise means the Australian dollar is stronger. Tracks industrial metals and Chinese demand."),
    ("fx-majors", "NZDUSD", "New Zealand Dollar / US Dollar", "forex", "none", "yahoo", "NZDUSD=X",
     "A rise means the New Zealand dollar is stronger."),
    ("fx-majors", "EURGBP", "Euro / British Pound", "forex", "none", "yahoo", "EURGBP=X",
     "Sterling per euro. A cross with no dollar in it, so it reads European divergence directly."),
    ("fx-majors", "EURJPY", "Euro / Japanese Yen", "forex", "none", "yahoo", "EURJPY=X",
     "Yen per euro. Commonly read as a risk appetite gauge."),
    ("fx-majors", "GBPJPY", "British Pound / Japanese Yen", "forex", "none", "yahoo", "GBPJPY=X",
     "Yen per pound. The widest daily range of the crosses here."),
    ("fx-asia", "USDPKR", "US Dollar / Pakistani Rupee", "forex", "none", "yahoo", "USDPKR=X",
     "Rupees per dollar. A rise means the rupee is weaker, which feeds straight into PSX import costs."),
    ("fx-asia", "USDINR", "US Dollar / Indian Rupee", "forex", "none", "yahoo", "USDINR=X",
     "Rupees per dollar. Managed within a band by the Reserve Bank of India."),
    ("fx-asia", "USDCNY", "US Dollar / Chinese Yuan", "forex", "none", "yahoo", "USDCNY=X",
     "Yuan per dollar, onshore. A daily fix sets the band, so moves are policy as much as flow."),
    ("fx-asia", "USDKRW", "US Dollar / South Korean Won", "forex", "none", "yahoo", "USDKRW=X",
     "Won per dollar. Moves with the semiconductor cycle."),
    ("fx-asia", "USDIDR", "US Dollar / Indonesian Rupiah", "forex", "none", "yahoo", "USDIDR=X",
     "Rupiah per dollar."),
    ("fx-asia", "USDTHB", "US Dollar / Thai Baht", "forex", "none", "yahoo", "USDTHB=X",
     "Baht per dollar."),
    ("fx-asia", "USDPHP", "US Dollar / Philippine Peso", "forex", "none", "yahoo", "USDPHP=X",
     "Pesos per dollar."),
    ("fx-asia", "USDMYR", "US Dollar / Malaysian Ringgit", "forex", "none", "yahoo", "USDMYR=X",
     "Ringgit per dollar."),
    ("fx-asia", "USDSGD", "US Dollar / Singapore Dollar", "forex", "none", "yahoo", "USDSGD=X",
     "Singapore dollars per US dollar. Managed against a trade weighted basket."),
    ("fx-asia", "USDBDT", "US Dollar / Bangladeshi Taka", "forex", "none", "yahoo", "USDBDT=X",
     "Taka per dollar."),
    ("fx-emerging", "USDTRY", "US Dollar / Turkish Lira", "forex", "none", "yahoo", "USDTRY=X",
     "Lira per dollar. A near one way move for years, so a return figure here reads as inflation."),
    ("fx-emerging", "USDBRL", "US Dollar / Brazilian Real", "forex", "none", "yahoo", "USDBRL=X",
     "Reais per dollar."),
    ("fx-emerging", "USDZAR", "US Dollar / South African Rand", "forex", "none", "yahoo", "USDZAR=X",
     "Rand per dollar. One of the most volatile liquid currencies."),
    ("fx-emerging", "USDMXN", "US Dollar / Mexican Peso", "forex", "none", "yahoo", "USDMXN=X",
     "Pesos per dollar."),
    ("fx-emerging", "USDSEK", "US Dollar / Swedish Krona", "forex", "none", "yahoo", "USDSEK=X",
     "Kronor per dollar."),
    ("fx-emerging", "USDNOK", "US Dollar / Norwegian Krone", "forex", "none", "yahoo", "USDNOK=X",
     "Kroner per dollar. Moves with crude."),
    ("fx-emerging", "USDPLN", "US Dollar / Polish Zloty", "forex", "none", "yahoo", "USDPLN=X",
     "Zloty per dollar."),
]

ASSETS = ASSETS + FOREX_ASSETS

# --- expansion, 2026-10-08 ----------------------------------------------------------------
#
# Measured by `tools/candidates.py` against each market's own free source, which is the check
# the 2026-10-04 batch was done by hand and the reason this one is reproducible. Every figure
# below is that tool's output on 2026-10-08 and can be reprinted by running it.
#
# US: one year of Yahoo daily bars, at least 200 sessions and $50M of median daily turnover
# (close x volume). Turnover rather than share count, because an industry ranking puts a $3
# stock and a $600 one side by side. Three candidates were measured and dropped rather than
# carried: GOLD at $20M and TX at $11M, both under the floor, and X returned no series at all.
#
# Two industries are new here, and they exist because the alternative was a wrong label. The
# miners could not go into Precious Metals -- that group is written as futures "and the funds
# that hold the metal", and a peer median mixing bullion with a levered producer describes
# neither -- and the steel and iron names had nowhere at all. Each new group opens with eleven
# and thirteen names, so neither is the three-name ranking the 2026-10-04 note refused.
MORE_US_2: list[tuple] = [
    ("mega-cap-tech", "ABNB", "Airbnb", "stock", "marketCap", YAHOO, "ABNB", "Short stay accommodation marketplace."),
    ("mega-cap-tech", "SPOT", "Spotify", "stock", "marketCap", YAHOO, "SPOT", "Subscription music and podcast streaming."),

    ("software-cloud", "FTNT", "Fortinet", "stock", "marketCap", YAHOO, "FTNT", "Network firewalls and security appliances."),
    ("software-cloud", "VEEV", "Veeva Systems", "stock", "marketCap", YAHOO, "VEEV", "Cloud software for the life sciences industry."),
    ("software-cloud", "HUBS", "HubSpot", "stock", "marketCap", YAHOO, "HUBS", "Marketing, sales and service software."),

    ("semiconductors", "MPWR", "Monolithic Power Systems", "stock", "marketCap", YAHOO, "MPWR", "Power management chips, data centre weighted."),
    ("semiconductors", "GFS", "GlobalFoundries", "stock", "marketCap", YAHOO, "GFS", "Contract chip manufacturing outside the leading edge."),

    ("financials", "PYPL", "PayPal", "stock", "marketCap", YAHOO, "PYPL", "Online payments and consumer wallets."),

    ("energy", "TRGP", "Targa Resources", "stock", "marketCap", YAHOO, "TRGP", "Natural gas gathering, processing and logistics."),

    ("healthcare", "ABT", "Abbott Laboratories", "stock", "marketCap", YAHOO, "ABT", "Diagnostics, devices and nutrition."),
    ("healthcare", "ELV", "Elevance Health", "stock", "marketCap", YAHOO, "ELV", "Health insurance and managed care."),
    ("healthcare", "ZTS", "Zoetis", "stock", "marketCap", YAHOO, "ZTS", "Animal health medicines and vaccines."),
    ("healthcare", "HCA", "HCA Healthcare", "stock", "marketCap", YAHOO, "HCA", "Hospital and outpatient care operator."),

    ("precious-metal-miners", "NEM", "Newmont", "stock", "marketCap", YAHOO, "NEM", "The largest listed gold producer by output."),
    ("precious-metal-miners", "AEM", "Agnico Eagle Mines", "stock", "marketCap", YAHOO, "AEM", "Gold production, Canada and Finland weighted."),
    ("precious-metal-miners", "FNV", "Franco-Nevada", "stock", "marketCap", YAHOO, "FNV", "Gold royalties and streams rather than mines."),
    ("precious-metal-miners", "WPM", "Wheaton Precious Metals", "stock", "marketCap", YAHOO, "WPM", "Precious metal streaming contracts."),
    ("precious-metal-miners", "KGC", "Kinross Gold", "stock", "marketCap", YAHOO, "KGC", "Gold production across the Americas and West Africa."),
    ("precious-metal-miners", "AU", "AngloGold Ashanti", "stock", "marketCap", YAHOO, "AU", "Gold production, Africa and the Americas."),
    ("precious-metal-miners", "GFI", "Gold Fields", "stock", "marketCap", YAHOO, "GFI", "Gold production, South Africa and Australia."),
    ("precious-metal-miners", "PAAS", "Pan American Silver", "stock", "marketCap", YAHOO, "PAAS", "Silver and gold production in Latin America."),
    ("precious-metal-miners", "RGLD", "Royal Gold", "stock", "marketCap", YAHOO, "RGLD", "Gold royalties and stream interests."),
    ("precious-metal-miners", "BTG", "B2Gold", "stock", "marketCap", YAHOO, "BTG", "Gold production, Mali and the Philippines weighted."),
    ("precious-metal-miners", "HMY", "Harmony Gold", "stock", "marketCap", YAHOO, "HMY", "South African gold production."),

    ("base-metals-and-steel", "FCX", "Freeport-McMoRan", "stock", "marketCap", YAHOO, "FCX", "Copper and gold mining, Indonesia and the Americas."),
    ("base-metals-and-steel", "SCCO", "Southern Copper", "stock", "marketCap", YAHOO, "SCCO", "Copper mining in Peru and Mexico."),
    ("base-metals-and-steel", "VALE", "Vale", "stock", "marketCap", YAHOO, "VALE", "Iron ore and nickel, the largest Brazilian miner."),
    ("base-metals-and-steel", "RIO", "Rio Tinto", "stock", "marketCap", YAHOO, "RIO", "Iron ore, aluminium and copper."),
    ("base-metals-and-steel", "BHP", "BHP Group", "stock", "marketCap", YAHOO, "BHP", "Iron ore, copper and coal."),
    ("base-metals-and-steel", "NUE", "Nucor", "stock", "marketCap", YAHOO, "NUE", "Electric arc furnace steel, the largest US producer."),
    ("base-metals-and-steel", "STLD", "Steel Dynamics", "stock", "marketCap", YAHOO, "STLD", "Electric arc furnace steel and recycling."),
    ("base-metals-and-steel", "CLF", "Cleveland-Cliffs", "stock", "marketCap", YAHOO, "CLF", "Integrated steel and iron ore pellets."),
    ("base-metals-and-steel", "CMC", "Commercial Metals", "stock", "marketCap", YAHOO, "CMC", "Rebar and merchant steel, construction weighted."),
    ("base-metals-and-steel", "RS", "Reliance", "stock", "marketCap", YAHOO, "RS", "Metals service centres and processing."),
    ("base-metals-and-steel", "MT", "ArcelorMittal", "stock", "marketCap", YAHOO, "MT", "Integrated steel across Europe and the Americas."),
    ("base-metals-and-steel", "GGB", "Gerdau", "stock", "marketCap", YAHOO, "GGB", "Long steel production in Brazil and North America."),
    ("base-metals-and-steel", "AA", "Alcoa", "stock", "marketCap", YAHOO, "AA", "Bauxite, alumina and primary aluminium."),
]

# Crypto, measured through `prices.crypto_closes` -- the same four venue chain the fetch job
# uses, not one exchange. The floor is $4M of median daily turnover on whichever venue answers,
# which is the median of the 27 coins already followed rather than a number chosen to sound
# strict: those run from $573M down to $0.5M, so the $20M Binance figure the earlier batch used
# would reject two thirds of the universe this site already prices. Seven candidates were
# measured and dropped under the floor, and two more because CoinPaprika does not carry the id.
MORE_CRYPTO_2: list[tuple] = [
    ("crypto", "dot-polkadot", "Polkadot", "crypto", "marketCap", PAPRIKA, "dot-polkadot", "Relay chain securing parallel chains."),
    ("crypto", "pol-polygon-ecosystem-token", "Polygon", "crypto", "marketCap", PAPRIKA, "pol-polygon-ecosystem-token", "Ethereum scaling network and its staking token."),
    ("crypto", "shib-shiba-inu", "Shiba Inu", "crypto", "marketCap", PAPRIKA, "shib-shiba-inu", "Ethereum meme token with a layer two of its own."),
    ("crypto", "pepe-pepe", "Pepe", "crypto", "marketCap", PAPRIKA, "pepe-pepe", "Ethereum meme token."),
    ("crypto", "ondo-ondo", "Ondo", "crypto", "marketCap", PAPRIKA, "ondo-ondo", "Tokenised treasury and credit products."),
    ("crypto", "tao-bittensor", "Bittensor", "crypto", "marketCap", PAPRIKA, "tao-bittensor", "Network paying for machine learning model output."),
    ("crypto", "ena-ethena", "Ethena", "crypto", "marketCap", PAPRIKA, "ena-ethena", "Synthetic dollar protocol governance token."),
    ("crypto", "tia-celestia", "Celestia", "crypto", "marketCap", PAPRIKA, "tia-celestia", "Modular data availability layer."),
    ("crypto", "sei-sei", "Sei", "crypto", "marketCap", PAPRIKA, "sei-sei", "Trading focused parallel execution chain."),
]

# PSX, taken from the exchange's own published closing files and placed by the exchange's own
# sector code -- field three of every row in `mkt_summary`, which `tools/candidates.py psx`
# reads and maps to an industry by looking at which code the names already followed carry.
#
# A code is only trusted when at least three followed names sit behind it. That rule is not
# decoration: ENGROH is a holding company the exchange files under its investment-company code
# and this project placed in PSX Fertilizer, and on its own it taught the map that every
# brokerage on the exchange -- Arif Habib, Trust Brokerage, five others -- was a fertilizer
# producer. Every peer median and relative strength reading here is computed inside an
# industry, so an import under a wrong label is not cosmetic.
#
# Seventy-two liquid symbols were ranked and left out because this project has no industry for
# them: steel, sugar, pharmaceuticals, chemicals, paints, food, property, insurance and the
# terminals. Turnover figures behind each pick are medians over the 16 sessions the exchange
# published in the three weeks to 2026-10-08.
MORE_PSX_2: list[tuple] = [
    ("psx-technology", "ZUMA", "Zuma Resources", "stock", "marketCap", PSX, "ZUMA", "Technology and communication sector listing, Rs.129M a day."),
    ("psx-technology", "MDTL", "Media Times", "stock", "marketCap", PSX, "MDTL", "Media and publishing, filed under technology and communication."),
    ("psx-technology", "QTECH", "Quantum Data", "stock", "marketCap", PSX, "QTECH", "Data and technology services."),
    ("psx-technology", "ZAL", "Zarea", "stock", "marketCap", PSX, "ZAL", "Technology and communication sector listing."),

    ("psx-oil-gas", "OBOY", "Oilboy Energy", "stock", "marketCap", PSX, "OBOY", "Fuel marketing, in the exchange's oil and gas marketing sector."),
    ("psx-oil-gas", "WAFI", "Wafi Energy Pakistan", "stock", "marketCap", PSX, "WAFI", "Fuel retail and lubricants, the former Shell Pakistan network."),

    ("psx-banks", "BML", "Bank Makramah", "stock", "marketCap", PSX, "BML", "Commercial bank, the former Summit Bank."),
    ("psx-banks", "HMB", "Habib Metropolitan Bank", "stock", "marketCap", PSX, "HMB", "Commercial bank, trade finance weighted."),

    ("psx-cement", "DCL", "Dewan Cement", "stock", "marketCap", PSX, "DCL", "Cement manufacture."),
    ("psx-cement", "POWER", "Power Cement", "stock", "marketCap", PSX, "POWER", "Cement manufacture in southern Sindh."),
    ("psx-cement", "DNCC", "Dandot Cement", "stock", "marketCap", PSX, "DNCC", "Cement manufacture in northern Punjab."),
    ("psx-cement", "DBCI", "Dadabhoy Cement", "stock", "marketCap", PSX, "DBCI", "Cement manufacture."),
]

ASSETS = ASSETS + MORE_US_2 + MORE_CRYPTO_2 + MORE_PSX_2

# --- expansion, 2026-10-08, second pass ------------------------------------------------------
#
# 331 names to 480. Every US symbol was measured by `tools/candidates.py us` against a year of
# Yahoo daily bars -- at least 200 sessions and $50M of median daily turnover -- and every
# Karachi symbol came out of `tools/candidates.py psx`, which ranks the exchange's own closing
# files and places a name by the exchange's own sector code.
#
# Six US candidates were measured and dropped rather than carried: K, WBD and EA under the
# turnover floor, and ABT.W, NEM.W and BRK-B returned no series under those tickers.
MORE_US_3: list[tuple] = [
    ("chemicals-materials", "LIN", "Linde", "stock", "marketCap", YAHOO, "LIN", "Industrial gases, the largest listed producer."),
    ("chemicals-materials", "APD", "Air Products", "stock", "marketCap", YAHOO, "APD", "Industrial gases and hydrogen projects."),
    ("chemicals-materials", "SHW", "Sherwin-Williams", "stock", "marketCap", YAHOO, "SHW", "Architectural and industrial coatings."),
    ("chemicals-materials", "ECL", "Ecolab", "stock", "marketCap", YAHOO, "ECL", "Water treatment and cleaning chemistry."),
    ("chemicals-materials", "DOW", "Dow", "stock", "marketCap", YAHOO, "DOW", "Commodity plastics and chemicals."),
    ("chemicals-materials", "DD", "DuPont", "stock", "marketCap", YAHOO, "DD", "Electronics and water materials."),
    ("chemicals-materials", "PPG", "PPG Industries", "stock", "marketCap", YAHOO, "PPG", "Coatings for vehicles and buildings."),

    ("industrials", "CAT", "Caterpillar", "stock", "marketCap", YAHOO, "CAT", "Construction and mining equipment."),
    ("industrials", "DE", "Deere", "stock", "marketCap", YAHOO, "DE", "Agricultural and construction machinery."),
    ("industrials", "HON", "Honeywell", "stock", "marketCap", YAHOO, "HON", "Aerospace systems, automation and materials."),
    ("industrials", "GE", "GE Aerospace", "stock", "marketCap", YAHOO, "GE", "Jet engines and aftermarket services."),
    ("industrials", "MMM", "3M", "stock", "marketCap", YAHOO, "MMM", "Industrial and consumer materials."),
    ("industrials", "EMR", "Emerson Electric", "stock", "marketCap", YAHOO, "EMR", "Process automation and control."),
    ("industrials", "ETN", "Eaton", "stock", "marketCap", YAHOO, "ETN", "Electrical power management, data centre weighted."),
    ("industrials", "PH", "Parker Hannifin", "stock", "marketCap", YAHOO, "PH", "Motion and flow control systems."),
    ("industrials", "ROK", "Rockwell Automation", "stock", "marketCap", YAHOO, "ROK", "Factory automation and control."),
    ("industrials", "ITW", "Illinois Tool Works", "stock", "marketCap", YAHOO, "ITW", "Diversified industrial components."),
    ("industrials", "WM", "Waste Management", "stock", "marketCap", YAHOO, "WM", "Collection, landfill and recycling."),
    ("industrials", "RSG", "Republic Services", "stock", "marketCap", YAHOO, "RSG", "Waste collection and disposal."),

    ("aerospace-defence", "LMT", "Lockheed Martin", "stock", "marketCap", YAHOO, "LMT", "Combat aircraft and missile systems."),
    ("aerospace-defence", "RTX", "RTX", "stock", "marketCap", YAHOO, "RTX", "Engines, avionics and missiles."),
    ("aerospace-defence", "NOC", "Northrop Grumman", "stock", "marketCap", YAHOO, "NOC", "Strategic systems and space."),
    ("aerospace-defence", "GD", "General Dynamics", "stock", "marketCap", YAHOO, "GD", "Submarines, combat vehicles and business jets."),
    ("aerospace-defence", "BA", "Boeing", "stock", "marketCap", YAHOO, "BA", "Commercial airframes and defence."),

    ("transport-logistics", "UNP", "Union Pacific", "stock", "marketCap", YAHOO, "UNP", "Western US freight rail."),
    ("transport-logistics", "CSX", "CSX", "stock", "marketCap", YAHOO, "CSX", "Eastern US freight rail."),
    ("transport-logistics", "NSC", "Norfolk Southern", "stock", "marketCap", YAHOO, "NSC", "Eastern US freight rail."),
    ("transport-logistics", "FDX", "FedEx", "stock", "marketCap", YAHOO, "FDX", "Air and ground parcel delivery."),
    ("transport-logistics", "UPS", "United Parcel Service", "stock", "marketCap", YAHOO, "UPS", "Ground and air parcel delivery."),

    ("real-estate", "AMT", "American Tower", "stock", "marketCap", YAHOO, "AMT", "Communications towers leased to carriers."),
    ("real-estate", "PLD", "Prologis", "stock", "marketCap", YAHOO, "PLD", "Logistics warehouses."),
    ("real-estate", "EQIX", "Equinix", "stock", "marketCap", YAHOO, "EQIX", "Interconnection data centres."),
    ("real-estate", "DLR", "Digital Realty", "stock", "marketCap", YAHOO, "DLR", "Data centre property."),
    ("real-estate", "CCI", "Crown Castle", "stock", "marketCap", YAHOO, "CCI", "Towers and small cells."),
    ("real-estate", "SPG", "Simon Property", "stock", "marketCap", YAHOO, "SPG", "Shopping centres and outlets."),
    ("real-estate", "O", "Realty Income", "stock", "marketCap", YAHOO, "O", "Single tenant net lease property."),

    ("retail", "WMT", "Walmart", "stock", "marketCap", YAHOO, "WMT", "General merchandise and grocery."),
    ("retail", "COST", "Costco", "stock", "marketCap", YAHOO, "COST", "Membership warehouse retail."),
    ("retail", "HD", "Home Depot", "stock", "marketCap", YAHOO, "HD", "Home improvement retail."),
    ("retail", "LOW", "Lowe's", "stock", "marketCap", YAHOO, "LOW", "Home improvement retail."),
    ("retail", "TGT", "Target", "stock", "marketCap", YAHOO, "TGT", "General merchandise retail."),
    ("retail", "TJX", "TJX Companies", "stock", "marketCap", YAHOO, "TJX", "Off-price apparel and home."),
    ("retail", "ROST", "Ross Stores", "stock", "marketCap", YAHOO, "ROST", "Off-price apparel."),
    ("retail", "DG", "Dollar General", "stock", "marketCap", YAHOO, "DG", "Small format discount retail."),
    ("retail", "DLTR", "Dollar Tree", "stock", "marketCap", YAHOO, "DLTR", "Discount variety retail."),
    ("retail", "KR", "Kroger", "stock", "marketCap", YAHOO, "KR", "Grocery retail."),
    ("retail", "SYY", "Sysco", "stock", "marketCap", YAHOO, "SYY", "Food distribution to restaurants."),

    ("consumer-brands", "MCD", "McDonald's", "stock", "marketCap", YAHOO, "MCD", "Quick service restaurants, franchised."),
    ("consumer-brands", "SBUX", "Starbucks", "stock", "marketCap", YAHOO, "SBUX", "Coffee retail."),
    ("consumer-brands", "CMG", "Chipotle", "stock", "marketCap", YAHOO, "CMG", "Fast casual restaurants, company operated."),
    ("consumer-brands", "YUM", "Yum! Brands", "stock", "marketCap", YAHOO, "YUM", "Franchised restaurant brands."),
    ("consumer-brands", "DRI", "Darden Restaurants", "stock", "marketCap", YAHOO, "DRI", "Full service restaurant brands."),
    ("consumer-brands", "NKE", "Nike", "stock", "marketCap", YAHOO, "NKE", "Athletic footwear and apparel."),
    ("consumer-brands", "LULU", "Lululemon", "stock", "marketCap", YAHOO, "LULU", "Athletic apparel, direct to consumer weighted."),

    ("consumer-staples", "PG", "Procter & Gamble", "stock", "marketCap", YAHOO, "PG", "Household and personal care brands."),
    ("consumer-staples", "KO", "Coca-Cola", "stock", "marketCap", YAHOO, "KO", "Non-alcoholic beverages."),
    ("consumer-staples", "PEP", "PepsiCo", "stock", "marketCap", YAHOO, "PEP", "Beverages and snacks."),
    ("consumer-staples", "PM", "Philip Morris International", "stock", "marketCap", YAHOO, "PM", "Tobacco and heated products."),
    ("consumer-staples", "MO", "Altria", "stock", "marketCap", YAHOO, "MO", "US tobacco."),
    ("consumer-staples", "CL", "Colgate-Palmolive", "stock", "marketCap", YAHOO, "CL", "Oral, personal and home care."),
    ("consumer-staples", "KMB", "Kimberly-Clark", "stock", "marketCap", YAHOO, "KMB", "Tissue and personal care."),
    ("consumer-staples", "GIS", "General Mills", "stock", "marketCap", YAHOO, "GIS", "Packaged food."),
    ("consumer-staples", "HSY", "Hershey", "stock", "marketCap", YAHOO, "HSY", "Confectionery."),
    ("consumer-staples", "STZ", "Constellation Brands", "stock", "marketCap", YAHOO, "STZ", "Beer, wine and spirits."),
    ("consumer-staples", "KHC", "Kraft Heinz", "stock", "marketCap", YAHOO, "KHC", "Packaged food."),

    ("media-telecom", "DIS", "Walt Disney", "stock", "marketCap", YAHOO, "DIS", "Studios, parks and streaming."),
    ("media-telecom", "CMCSA", "Comcast", "stock", "marketCap", YAHOO, "CMCSA", "Cable broadband and NBCUniversal."),
    ("media-telecom", "T", "AT&T", "stock", "marketCap", YAHOO, "T", "Wireless and fibre."),
    ("media-telecom", "VZ", "Verizon", "stock", "marketCap", YAHOO, "VZ", "Wireless and broadband."),
    ("media-telecom", "TMUS", "T-Mobile US", "stock", "marketCap", YAHOO, "TMUS", "Wireless carrier."),
    ("media-telecom", "TTWO", "Take-Two Interactive", "stock", "marketCap", YAHOO, "TTWO", "Video game publishing."),
    ("media-telecom", "RBLX", "Roblox", "stock", "marketCap", YAHOO, "RBLX", "User generated game platform."),

    ("insurance", "ALL", "Allstate", "stock", "marketCap", YAHOO, "ALL", "Personal property and casualty."),
    ("insurance", "TRV", "Travelers", "stock", "marketCap", YAHOO, "TRV", "Commercial property and casualty."),
    ("insurance", "CB", "Chubb", "stock", "marketCap", YAHOO, "CB", "Commercial and specialty insurance."),
    ("insurance", "AIG", "American International Group", "stock", "marketCap", YAHOO, "AIG", "Commercial property and casualty."),
    ("insurance", "MET", "MetLife", "stock", "marketCap", YAHOO, "MET", "Life insurance and benefits."),
    ("insurance", "PRU", "Prudential Financial", "stock", "marketCap", YAHOO, "PRU", "Life insurance and retirement."),

    ("utilities", "NEE", "NextEra Energy", "stock", "marketCap", YAHOO, "NEE", "Regulated Florida utility and renewables."),
    ("utilities", "DUK", "Duke Energy", "stock", "marketCap", YAHOO, "DUK", "Regulated electric utility, southeast US."),
    ("utilities", "SO", "Southern Company", "stock", "marketCap", YAHOO, "SO", "Regulated electric utility and nuclear."),
    ("utilities", "D", "Dominion Energy", "stock", "marketCap", YAHOO, "D", "Regulated electric utility, mid-Atlantic."),
    ("utilities", "AEP", "American Electric Power", "stock", "marketCap", YAHOO, "AEP", "Regulated electric utility and transmission."),
    ("utilities", "EXC", "Exelon", "stock", "marketCap", YAHOO, "EXC", "Regulated transmission and distribution."),
    ("utilities", "SRE", "Sempra", "stock", "marketCap", YAHOO, "SRE", "California utility and LNG infrastructure."),
    ("utilities", "XEL", "Xcel Energy", "stock", "marketCap", YAHOO, "XEL", "Regulated electric utility, midwest US."),
]

# PSX, six sectors the exchange publishes that this project had no industry for. Turnover
# figures are medians over the 16 sessions published in the three weeks to 2026-10-08, and a
# name is only here if it printed a close on at least 80% of them.
MORE_PSX_3: list[tuple] = [
    ("psx-chemicals", "GCIL", "Ghani Chemical Industries", "stock", "marketCap", PSX, "GCIL", "Industrial and medical gases."),
    ("psx-chemicals", "BUXL", "Buxly Paints", "stock", "marketCap", PSX, "BUXL", "Decorative and industrial paints."),
    ("psx-chemicals", "LOTCHEM", "Lotte Chemical Pakistan", "stock", "marketCap", PSX, "LOTCHEM", "Purified terephthalic acid for polyester."),
    ("psx-chemicals", "NICL", "Nimir Industrial Chemicals", "stock", "marketCap", PSX, "NICL", "Chlor-alkali and oleochemicals."),
    ("psx-chemicals", "BERG", "Berger Paints Pakistan", "stock", "marketCap", PSX, "BERG", "Decorative and protective coatings."),
    ("psx-chemicals", "GGL", "Ghani Global Holdings", "stock", "marketCap", PSX, "GGL", "Glass and chemical manufacturing holding."),
    ("psx-chemicals", "NRSL", "Nimir Resins", "stock", "marketCap", PSX, "NRSL", "Resins and polymers for coatings."),
    ("psx-chemicals", "LCI", "Lucky Core Industries", "stock", "marketCap", PSX, "LCI", "Soda ash, polyester and chemicals."),
    ("psx-chemicals", "BAPL", "Bawany Air Products", "stock", "marketCap", PSX, "BAPL", "Industrial gases."),
    ("psx-chemicals", "EPCL", "Engro Polymer and Chemicals", "stock", "marketCap", PSX, "EPCL", "PVC and caustic soda."),
    ("psx-chemicals", "BIFO", "Biafo Industries", "stock", "marketCap", PSX, "BIFO", "Commercial explosives and chemicals."),
    ("psx-chemicals", "ARPL", "Archroma Pakistan", "stock", "marketCap", PSX, "ARPL", "Specialty chemicals and dyes."),

    ("psx-steel", "ASL", "Aisha Steel Mills", "stock", "marketCap", PSX, "ASL", "Cold rolled and galvanised flat steel."),
    ("psx-steel", "ASTL", "Amreli Steels", "stock", "marketCap", PSX, "ASTL", "Rebar for construction."),
    ("psx-steel", "MUGHAL", "Mughal Iron and Steel", "stock", "marketCap", PSX, "MUGHAL", "Rebar, girders and copper products."),
    ("psx-steel", "BECO", "Beco Steel", "stock", "marketCap", PSX, "BECO", "Steel re-rolling."),
    ("psx-steel", "ISL", "International Steels", "stock", "marketCap", PSX, "ISL", "Cold rolled and galvanised coil."),
    ("psx-steel", "INIL", "International Industries", "stock", "marketCap", PSX, "INIL", "Steel pipe and polymer pipe."),
    ("psx-steel", "CSAP", "Crescent Steel and Allied Products", "stock", "marketCap", PSX, "CSAP", "Line pipe and steel fabrication."),
    ("psx-steel", "AGHA", "Agha Steel Industries", "stock", "marketCap", PSX, "AGHA", "Rebar from an electric arc furnace."),

    ("psx-food", "FCEPL", "FrieslandCampina Engro Pakistan", "stock", "marketCap", PSX, "FCEPL", "Packaged dairy."),
    ("psx-food", "MFL", "Matco Foods", "stock", "marketCap", PSX, "MFL", "Rice processing and export."),
    ("psx-food", "TREET", "Treet Corporation", "stock", "marketCap", PSX, "TREET", "Razors, batteries and consumer goods."),
    ("psx-food", "PREMA", "At-Tahur", "stock", "marketCap", PSX, "PREMA", "Fresh dairy under the Prema brand."),
    ("psx-food", "NATF", "National Foods", "stock", "marketCap", PSX, "NATF", "Spices, sauces and recipe mixes."),
    ("psx-food", "TOMCL", "The Organic Meat Company", "stock", "marketCap", PSX, "TOMCL", "Halal meat processing and export."),
    ("psx-food", "FFL", "Fauji Foods", "stock", "marketCap", PSX, "FFL", "Dairy and juice under the Nurpur brand."),
    ("psx-food", "UNITY", "Unity Foods", "stock", "marketCap", PSX, "UNITY", "Edible oil refining and feed."),
    ("psx-food", "BBFL", "Big Bird Foods", "stock", "marketCap", PSX, "BBFL", "Poultry processing and feed."),
    ("psx-food", "QUICE", "Quice Food Industries", "stock", "marketCap", PSX, "QUICE", "Confectionery and snacks."),
    ("psx-food", "SOYASUP", "Agro Processors and Atmospheric Gases", "stock", "marketCap", PSX, "SOYASUP", "Soya crushing and industrial gases."),
    ("psx-food", "COLG", "Colgate-Palmolive Pakistan", "stock", "marketCap", PSX, "COLG", "Oral care, detergents and personal care."),
    ("psx-food", "GDL", "Ghani Dairies", "stock", "marketCap", PSX, "GDL", "Dairy processing."),
    ("psx-food", "CLOV", "Clover Pakistan", "stock", "marketCap", PSX, "CLOV", "Food trading and distribution."),
    ("psx-food", "BNL", "Bunnys", "stock", "marketCap", PSX, "BNL", "Bakery products."),
    ("psx-food", "WAHDAT", "Wahdat Poultry Farms", "stock", "marketCap", PSX, "WAHDAT", "Poultry farming."),
    ("psx-food", "NESTLE", "Nestle Pakistan", "stock", "marketCap", PSX, "NESTLE", "Dairy, water and nutrition."),

    ("psx-investment", "SPAC1", "LSE SPAC-I", "stock", "marketCap", PSX, "SPAC1", "Special purpose acquisition company."),
    ("psx-investment", "PIAHCLA", "PIA Holding Company", "stock", "marketCap", PSX, "PIAHCLA", "Holding company of the national airline's estate."),
    # The exchange's own listing is deliberately absent. Its Karachi ticker is PSX, which
    # is also Phillips 66 in New York, and this project has followed Phillips 66 since the
    # first seed. Two assets cannot share a symbol here -- /asset/[symbol] resolves by
    # symbol alone and one of them would be unreachable, and the re-filing UPDATE below
    # matches on symbol and would read it as a cross-market move, which it refuses. Rs.29.9M
    # a day, measured and left out on purpose.
    ("psx-investment", "FCSC", "First Capital Securities", "stock", "marketCap", PSX, "FCSC", "Brokerage and corporate finance."),
    ("psx-investment", "TSBL", "Trust Securities and Brokerage", "stock", "marketCap", PSX, "TSBL", "Equity brokerage."),
    ("psx-investment", "FNEL", "First National Equities", "stock", "marketCap", PSX, "FNEL", "Equity brokerage."),
    ("psx-investment", "AHL", "Arif Habib Limited", "stock", "marketCap", PSX, "AHL", "Brokerage, research and investment banking."),
    ("psx-investment", "LSEVL", "LSE Ventures", "stock", "marketCap", PSX, "LSEVL", "Investment holding."),
    ("psx-investment", "LSECL", "LSE Capital", "stock", "marketCap", PSX, "LSECL", "Investment holding."),

    ("psx-pharma", "SEARL", "The Searle Company", "stock", "marketCap", PSX, "SEARL", "Branded generics and consumer health."),
    ("psx-pharma", "CPHL", "Citi Pharma", "stock", "marketCap", PSX, "CPHL", "Active ingredients and finished dosage."),
    ("psx-pharma", "GLAXO", "GlaxoSmithKline Pakistan", "stock", "marketCap", PSX, "GLAXO", "Prescription medicines and vaccines."),
    ("psx-pharma", "AGP", "AGP Limited", "stock", "marketCap", PSX, "AGP", "Branded generics."),
    ("psx-pharma", "HALEON", "Haleon Pakistan", "stock", "marketCap", PSX, "HALEON", "Consumer health brands."),
    ("psx-pharma", "BFBIO", "BF Biosciences", "stock", "marketCap", PSX, "BFBIO", "Biological and oncology products."),
    ("psx-pharma", "HINOON", "Highnoon Laboratories", "stock", "marketCap", PSX, "HINOON", "Branded generics."),
    ("psx-pharma", "FEROZ", "Ferozsons Laboratories", "stock", "marketCap", PSX, "FEROZ", "Branded generics and hepatology."),

    ("psx-spinning", "DSIL", "D.S. Industries", "stock", "marketCap", PSX, "DSIL", "Yarn spinning."),
    ("psx-spinning", "ASTM", "Asim Textile Mills", "stock", "marketCap", PSX, "ASTM", "Yarn spinning."),
    ("psx-spinning", "DFSM", "Dewan Farooque Spinning", "stock", "marketCap", PSX, "DFSM", "Yarn spinning."),
    ("psx-spinning", "ARCTM", "Arctic Textile Mills", "stock", "marketCap", PSX, "ARCTM", "Yarn spinning."),
    ("psx-spinning", "TATM", "Tata Textile Mills", "stock", "marketCap", PSX, "TATM", "Yarn spinning."),
    ("psx-spinning", "JDMT", "Janana De Malucho Textile", "stock", "marketCap", PSX, "JDMT", "Yarn spinning."),
    ("psx-spinning", "KOHTM", "Kohat Textile Mills", "stock", "marketCap", PSX, "KOHTM", "Yarn spinning."),
]

ASSETS = ASSETS + MORE_US_3 + MORE_PSX_3



# slug, name, category, summary, wiki title, trends term, subreddits
PRODUCTS = [
    ("standing-desk", "Standing desk", "Furniture", "Sit stand desks sold for home and office use.", "Standing desk", "standing desk", "buyitforlife,Fitness"),
    ("air-fryer", "Air fryer", "Kitchen", "Countertop convection fryers, one of the fastest moving small kitchen appliances.", "Convection oven", "air fryer", "buyitforlife,Cooking"),
    ("electric-bike", "Electric bike", "Transport", "Pedal assist and throttle e-bikes, plus the batteries they need.", "E-bike", "electric bike", "electricvehicles,buyitforlife"),
    ("sunscreen", "Sunscreen", "Health", "Mineral and chemical sun care, including SPF and reef safe claims.", "Sunscreen", "sunscreen", "skincare,buyitforlife"),
    ("weighted-blanket", "Weighted blanket", "Sleep", "Blankets and covers filled with glass beads or steel pellets.", "Weighted blanket", "weighted blanket", "sleep,buyitforlife"),
    ("robot-vacuum", "Robot vacuum", "Home", "Self emptying and mopping robot vacuums.", "Robotic vacuum cleaner", "robot vacuum", "homeautomation,buyitforlife"),
    ("portable-power-station", "Portable power station", "Power", "Battery backed generators for camping, backup and solar storage.", "", "portable power station", "buyitforlife,homeautomation"),
    ("dashcam", "Dash cam", "Transport", "Hardwired and front camera recorders sold to drivers.", "Dashcam", "dash cam", "buyitforlife"),
    ("heat-pump", "Heat pump", "HVAC", "Air source and geothermal heat pumps replacing gas boilers and furnace air.", "Heat pump", "heat pump", "buyitforlife,homeautomation"),
    ("water-flosser", "Water flosser", "Health", "Countertop and handheld oral irrigators.", "Oral irrigator", "water flosser", "buyitforlife"),
    ("espresso-machine", "Espresso machine", "Kitchen", "Home espresso machines and the pods or beans they consume.", "Espresso machine", "espresso machine", "buyitforlife,Cooking"),
    ("pickleball", "Pickleball", "Sports", "Paddles, balls and portable nets, mainly a US and Canada sport.", "Pickleball", "pickleball", "Fitness,buyitforlife"),
    ("smart-ring", "Smart ring", "Wearables", "Finger worn sleep and activity trackers, subscription based.", "Smart ring", "smart ring", "buyitforlife"),
    ("noise-cancelling-headphones", "Noise cancelling headphones", "Audio", "Over ear and in ear active noise cancelling headsets.", "Noise-cancelling headphones", "noise cancelling headphones", "buyitforlife,gadgets"),
    ("mechanical-keyboard", "Mechanical keyboard", "Computing", "Hot swappable mechanical keyboards and their switches.", "Keyboard technology", "mechanical keyboard", "MechanicalKeyboards,buyitforlife"),
    ("yoga-mat", "Yoga mat", "Fitness", "Home practice mats, with most demand linked to home workouts.", "Yoga mat", "yoga mat", "Fitness,buyitforlife"),
    ("infrared-sauna", "Infrared sauna", "Wellness", "Portable infrared sauna tents and cabin heaters.", "Infrared sauna", "infrared sauna", "buyitforlife"),
    ("home-battery", "Home battery", "Power", "Grid tied home storage sold for backup and self consumption.", "Home energy storage", "home battery", "homeautomation,investing"),
    ("satellite-internet", "Satellite internet", "Connectivity", "Low earth orbit satellite broadband terminals and subscriptions.", "Starlink", "starlink", "buyitforlife"),
    ("protein-supplement", "Protein supplement", "Nutrition", "Protein powders, bars and ready to drink products.", "Protein supplement", "protein supplement", "Fitness"),
    ("sleeping-bag", "Sleeping bag", "Outdoors", "Cold weather sleeping bags for camping and backpacking.", "Sleeping bag", "sleeping bag", "buyitforlife"),
    ("coffee-grinder", "Coffee grinder", "Kitchen", "Burr and blade grinders, a common upgrade inside espresso setups.", "Coffee grinder", "coffee grinder", "buyitforlife,Cooking"),
    ("ev-charging", "EV charging", "Transport", "Home and public charging hardware, cables and connectors.", "Charging station", "ev charging", "electricvehicles"),
    ("gpu-cloud", "GPU compute", "Infrastructure", "Rentable GPU capacity sold by the hour to AI developers.", "Graphics processing unit", "gpu rental", "investing,AskScience"),
    ("nuclear-power", "Nuclear power", "Power", "Existing reactor life extensions, restarts and new build, sold as long dated power.", "Nuclear power", "nuclear power", "investing"),
    ("vertical-farming", "Vertical farming", "Food", "Indoor stacked growing for herbs and leafy vegetables.", "Vertical farming", "vertical farming", "Homestead"),
    ("drone-delivery", "Drone delivery", "Transport", "Short range delivery drones and the airworthiness work behind them.", "Delivery drone", "drone delivery", "gadgets"),
    ("solid-state-battery", "Solid state battery", "Power", "Solid electrolyte cells for vehicles and consumer devices.", "Solid-state battery", "solid state battery", "electricvehicles,investing"),
    ("ai-glasses", "Smart glasses", "Wearables", "Camera and audio glasses that run assistant models on the device.", "Smart glasses", "smart glasses", "gadgets,buyitforlife"),
    ("home-generator", "Home generator", "Power", "Home standby and portable generators, most often bought for outages.", "Portable generator", "home generator", "buyitforlife,investing"),
]

# product slug -> [(industry slug, symbol, relation, note)]
LINKS = {
    "standing-desk": [("financials", "JPM", "Companies sell equipment on credit and leases", None)],
    "air-fryer": [("financials", "AXP", "Retail purchases move through card networks", None)],
    "electric-bike": [("financials", "SCHW", "Many buyers finance the purchase", None)],
    "sunscreen": [("healthcare", "JNJ", "Consumer health products are sold through the same retail channels", None)],
    "weighted-blanket": [("healthcare", "DHR", "Sleep and wellness retail overlaps with life science products", None)],
    "robot-vacuum": [("financials", "AXP", "High ticket consumer electronics are often bought on card", None)],
    "portable-power-station": [("financials", "BAC", "Battery backed generators are often financed", None)],
    "dashcam": [("insurance", "PGR", "Drivers buy recorders partly for insurance evidence", None)],
    "heat-pump": [("energy", "XOM", "Heat pumps displace gas boilers in the same homes that use gas heating", None)],
    "water-flosser": [("healthcare", "MRK", "Sold through pharmacies alongside over the counter health products", None)],
    "espresso-machine": [("financials", "SCHW", "Discretionary durable purchases are financed", None)],
    "pickleball": [("financials", "C", "Sporting goods retail runs through consumer lenders", None)],
    "smart-ring": [("mega-cap-tech", "AAPL", "Competes for the same wearable budget as a watch and a phone upgrade", None)],
    "noise-cancelling-headphones": [("mega-cap-tech", "NFLX", "Streaming and listening are often bundled in the same account", None)],
    "mechanical-keyboard": [("semiconductors", "INTC", "Keyboards ship inside PCs made with Intel silicon", None)],
    "yoga-mat": [("healthcare", "LLY", "Home fitness demand tracks with the wider weight loss category", None)],
    "infrared-sauna": [("financials", "AXP", "Higher ticket wellness purchases are often financed", None)],
    "home-battery": [
        ("energy", "CVX", "Grid scale batteries and rooftop solar change the same demand curve", None),
        ("financials", "GS", "Home storage is bought with tax credit financing", None),
    ],
    "satellite-internet": [("financials", "JPM", "Terminals and subscriptions are sold on credit", None)],
    "protein-supplement": [("healthcare", "AMGN", "Nutrition and protein sit inside the same consumer health channel", None)],
    "sleeping-bag": [("financials", "SCHW", "Outdoors gear is frequently bought on a payment plan", None)],
    "coffee-grinder": [("financials", "BAC", "Kitchen durables are bought on store cards", None)],
    "ev-charging": [
        ("energy", "SHEL", "Charging demand tracks the same electricity volumes as any other new load", None),
        ("financials", "BAC", "Charging equipment is frequently financed", None),
    ],
    "gpu-cloud": [
        ("mega-cap-tech", "NVDA", "Rentable GPU capacity runs on data centre GPUs", None),
        ("semiconductors", "TSM", "Demand for rented GPUs starts with orders for new chips", None),
    ],
    "nuclear-power": [
        ("energy", "COP", "Long dated firm power competes against gas and renewables for the same contracts", None),
        ("financials", "BLK", "Infrastructure investors finance long life generation assets", None),
    ],
    "vertical-farming": [("energy", "EOG", "Indoor growing competes for the same power and gas contracts", None)],
    "drone-delivery": [("financials", "GS", "Drone networks need insurance and financing like any delivery fleet", None)],
    "solid-state-battery": [
        ("mega-cap-tech", "TSLA", "Solid state cells are being announced for vehicle programmes", None),
        ("energy", "VLO", "Cell manufacturing draws on the same industrial power market", None),
    ],
    "ai-glasses": [
        ("mega-cap-tech", "META", "Camera glasses are a stated product line", None),
        ("mega-cap-tech", "NVDA", "On device models need the silicon this industry builds", None),
    ],
    "home-generator": [("energy", "PSX", "Refiners and fuel suppliers see the same outage driven fuel demand", None)],
}


def main() -> None:
    conn = db()
    with conn, conn.cursor() as cur:
        step("industries")
        for slug, name, summary, sort in INDUSTRIES:
            # The slug carries the exchange, so the market and the currency are derived
            # rather than repeated on every row where they could drift out of step.
            pk = slug.startswith("psx-")
            # A currency pair is not listed on an exchange, so "which market" is a different
            # question for it than for a share. FX keeps these out of the US and PK groups the
            # home page sets side by side: those two are separated because a rupee size figure
            # next to a dollar one compares to nothing, and a pair has no size at all. The
            # currency column stays USD because every pair here is quoted against the dollar
            # and nothing on an FX page prints a size anyway.
            fx = slug.startswith("fx-")
            cur.execute(
                """
                INSERT INTO "Industry" (slug, name, summary, sort, market, currency,
                                        "createdAt")
                VALUES (%s,%s,%s,%s,%s,%s, now())
                ON CONFLICT (slug) DO UPDATE
                SET name = EXCLUDED.name, summary = EXCLUDED.summary,
                    sort = EXCLUDED.sort, market = EXCLUDED.market,
                    currency = EXCLUDED.currency
                """,
                (
                    slug,
                    name,
                    summary,
                    sort,
                    "FX" if fx else "PK" if pk else "US",
                    "PKR" if pk else "USD",
                ),
            )
        cur.execute("SELECT count(*) AS n FROM \"Industry\"")
        print(f"  industries: {cur.fetchone()['n']}")

        # Re-file before inserting, because `Asset` is unique on ("industryId", symbol) and not
        # on the symbol alone. Moving a name between groups in ASSETS therefore reads to the
        # upsert below as a *different* asset: it would insert a second row and leave the first
        # one in place, so the site would carry the name twice and the old copy would keep being
        # priced and ranked. Deleting the old copy is not the alternative -- every history table
        # is `onDelete: Cascade`, so it would trade six years of closes for a tidy key.
        #
        # An UPDATE moves the row itself, which keeps its id and therefore keeps every snapshot,
        # setup, decision and news item already attached to it. The conflict clause below then
        # matches the row that has just been moved, and the move is a no-op on every later run.
        #
        # Restricted to moves **within one market**, which is the guard that matters. The market
        # decides the staleness rule, the currency and which page a name appears on, so a typo in
        # a slug must not be able to silently reclassify a Karachi name as a US one and start
        # printing its rupee close as dollars. A cross-market move is reported and refused: it is
        # a schema decision, not a seed edit.
        #
        # One statement over a VALUES list rather than a query per asset. 273 round trips is the
        # shape `QueryBudget` exists to refuse, and from a non-US host at 238ms each it would be
        # a minute of waiting to move, on almost every run, nothing at all.
        step("re-filing")
        pairs = [(symbol, slug) for slug, symbol, *_rest in ASSETS]
        cur.execute(
            """
            UPDATE "Asset" a
               SET "industryId" = want.id, currency = want.currency
              FROM (VALUES """
            + ",".join(["(%s,%s)"] * len(pairs))
            + """) AS seeded(symbol, slug),
                   "Industry" want, "Industry" have
             WHERE a.symbol = seeded.symbol
               AND want.slug = seeded.slug
               AND have.id = a."industryId"
               AND want.id <> have.id
               AND want.market = have.market
            RETURNING a.symbol, have.slug AS "from", want.slug AS "to"
            """,
            [v for pair in pairs for v in pair],
        )
        moved = cur.fetchall()
        for row in moved:
            print(f"  {row['symbol']}: {row['from']} -> {row['to']}")

        # Whatever the move refused to touch, named. A name seeded into another market's group
        # stays where it is, and saying so is the point: silence here would read as a successful
        # re-file and the asset would keep the staleness rule and currency of the wrong market.
        cur.execute(
            """
            SELECT a.symbol, have.slug AS "from", have.market AS "haveMarket",
                   seeded.slug AS "to", want.market AS "wantMarket"
              FROM (VALUES """
            + ",".join(["(%s,%s)"] * len(pairs))
            + """) AS seeded(symbol, slug)
              JOIN "Asset" a ON a.symbol = seeded.symbol
              JOIN "Industry" have ON have.id = a."industryId"
              JOIN "Industry" want ON want.slug = seeded.slug
             WHERE have.slug <> seeded.slug
            """,
            [v for pair in pairs for v in pair],
        )
        stuck = cur.fetchall()
        for row in stuck:
            print(
                f"  REFUSED {row['symbol']}: filed under {row['from']} ({row['haveMarket']}), "
                f"seeded under {row['to']} ({row['wantMarket']}) -- a cross-market move changes "
                "the staleness rule and the currency, so it is not applied here"
            )
        print(f"  re-filed: {len(moved)}" + (f", refused: {len(stuck)}" if stuck else ""))

        step("assets")
        for slug, symbol, name, atype, cap, source, ref, note in ASSETS:
            cur.execute(
                """
                INSERT INTO "Asset"
                  ("industryId", symbol, name, "assetType", "capBasis", source,
                   "sourceRef", description, note, currency, "createdAt")
                SELECT i.id, %s, %s, %s::"AssetType", %s::"CapBasis", %s, %s, %s, %s,
                       i.currency, now()
                FROM "Industry" i WHERE i.slug = %s
                ON CONFLICT ("industryId", symbol) DO UPDATE
                SET name = EXCLUDED.name, "assetType" = EXCLUDED."assetType",
                    "capBasis" = EXCLUDED."capBasis", source = EXCLUDED.source,
                    "sourceRef" = EXCLUDED."sourceRef", note = EXCLUDED.note,
                    currency = EXCLUDED.currency
                """,
                (symbol, name, atype, cap, source, ref, None, note, slug),
            )
        cur.execute("SELECT count(*) AS n FROM \"Asset\"")
        print(f"  assets: {cur.fetchone()['n']}")

        step("products")
        for slug, name, cat, summary, wiki, term, subs in PRODUCTS:
            cur.execute(
                """
                INSERT INTO "Product"
                  (slug, name, category, summary, "wikiTitle", "trendsTerm",
                   subreddits, "relatedTickers", status, "createdAt")
                VALUES (%s,%s,%s,%s,%s,%s,%s,'', 'unknown', now())
                ON CONFLICT (slug) DO UPDATE
                SET name = EXCLUDED.name, category = EXCLUDED.category,
                    summary = EXCLUDED.summary, "wikiTitle" = EXCLUDED."wikiTitle",
                    "trendsTerm" = EXCLUDED."trendsTerm", subreddits = EXCLUDED.subreddits
                """,
                (slug, name, cat, summary, wiki, term, subs),
            )
        cur.execute("SELECT count(*) AS n FROM \"Product\"")
        print(f"  products: {cur.fetchone()['n']}")

        step("product to asset links")
        kept = dropped = 0
        for pslug, targets in LINKS.items():
            for islug, symbol, relation, note in targets:
                got = cur.execute(
                    """
                    INSERT INTO "ProductAssetLink"
                      ("productId", "assetId", relation, note)
                    SELECT p.id, a.id, %s, %s
                    FROM "Product" p, "Asset" a
                    JOIN "Industry" i ON i.id = a."industryId"
                    WHERE p.slug = %s AND i.slug = %s AND a.symbol = %s
                    ON CONFLICT ("productId","assetId") DO UPDATE
                    SET relation = EXCLUDED.relation, note = EXCLUDED.note
                    RETURNING id
                    """,
                    (relation, note, pslug, islug, symbol),
                ).fetchone()
                if got:
                    kept += 1
                else:
                    dropped += 1
                    print(f"  no match for {pslug} -> {islug}/{symbol}")
        print(f"  links kept {kept}, skipped {dropped}")
    conn.close()


if __name__ == "__main__":
    main()

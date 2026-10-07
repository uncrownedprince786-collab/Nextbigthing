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
        "fx-emerging",
        "Higher volatility currencies",
        "The dollar against four currencies that move on domestic inflation and politics far "
        "more than on anything happening in the US.",
        32,
    ),
    (
        "fx-europe",
        "European currencies outside the euro",
        "The dollar against the Scandinavian currencies and the zloty. They track the euro "
        "closely enough that a divergence is the thing worth reading.",
        33,
    ),
]

INDUSTRIES = INDUSTRIES + PSX_INDUSTRIES + FOREX_INDUSTRIES

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
    ("financials", "PGR", "The Progressive", "stock", "marketCap", YAHOO, "PGR", "Auto and property insurance."),
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

    ("psx-fertilizer", "ENGROH", "Engro Holdings", "stock", "marketCap", PSX, "ENGROH", "Holding company of the Engro fertilizer and energy group."),

    ("psx-cement", "THCCL", "Thatta Cement", "stock", "marketCap", PSX, "THCCL", "Cement manufacturer in southern Sindh."),

    ("psx-power", "SGPL", "S.G. Power", "stock", "marketCap", PSX, "SGPL", "Independent power generation."),

    ("psx-technology", "TISL", "Tasdeeq Information Services", "stock", "marketCap", PSX, "TISL", "Credit information and data services."),
    ("psx-technology", "SELECT", "Select Technologies", "stock", "marketCap", PSX, "SELECT", "Information technology services."),
    ("psx-technology", "STL", "Supernet Technologies", "stock", "marketCap", PSX, "STL", "Network and satellite connectivity services."),
    ("psx-technology", "ITANZ", "Itanz Technologies", "stock", "marketCap", PSX, "ITANZ", "Information technology products and services."),

    ("psx-textile", "KOSM", "Kohinoor Spinning", "stock", "marketCap", PSX, "KOSM", "Yarn spinning and textile manufacture."),
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
    ("fx-europe", "USDSEK", "US Dollar / Swedish Krona", "forex", "none", "yahoo", "USDSEK=X",
     "Kronor per dollar."),
    ("fx-europe", "USDNOK", "US Dollar / Norwegian Krone", "forex", "none", "yahoo", "USDNOK=X",
     "Kroner per dollar. Moves with crude."),
    ("fx-europe", "USDPLN", "US Dollar / Polish Zloty", "forex", "none", "yahoo", "USDPLN=X",
     "Zloty per dollar."),
]

ASSETS = ASSETS + FOREX_ASSETS

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
    "dashcam": [("financials", "PGR", "Drivers buy recorders partly for insurance evidence", None)],
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

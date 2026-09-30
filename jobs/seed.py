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
        "Precious metal funds and futures. Used here as the non risk asset comparison "
        "against the AI trade.",
        4,
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
INDUSTRIES = INDUSTRIES + PSX_INDUSTRIES

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
    ("precious-metals", "CPER", "United States Copper Index Fund", "etf", "fundAssets", YAHOO, "CPER", "Copper futures based fund."),
    ("precious-metals", "COPX", "Global X Copper Miners", "etf", "fundAssets", YAHOO, "COPX", "Global copper miner equities."),
    ("precious-metals", "GC=F", "Gold futures", "commodity", "none", YAHOO, "GC=F", "Front month gold futures on COMEX."),
    ("precious-metals", "SI=F", "Silver futures", "commodity", "none", YAHOO, "SI=F", "Front month silver futures on COMEX."),
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
ASSETS = ASSETS + PSX_ASSETS

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
                (slug, name, summary, sort, "PK" if pk else "US", "PKR" if pk else "USD"),
            )
        cur.execute("SELECT count(*) AS n FROM \"Industry\"")
        print(f"  industries: {cur.fetchone()['n']}")

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

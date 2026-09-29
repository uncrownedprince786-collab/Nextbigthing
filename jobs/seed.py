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
]

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
            cur.execute(
                """
                INSERT INTO "Industry" (slug, name, summary, sort, "createdAt")
                VALUES (%s,%s,%s,%s, now())
                ON CONFLICT (slug) DO UPDATE
                SET name = EXCLUDED.name, summary = EXCLUDED.summary, sort = EXCLUDED.sort
                """,
                (slug, name, summary, sort),
            )
        cur.execute("SELECT count(*) AS n FROM \"Industry\"")
        print(f"  industries: {cur.fetchone()['n']}")

        step("assets")
        for slug, symbol, name, atype, cap, source, ref, note in ASSETS:
            cur.execute(
                """
                INSERT INTO "Asset"
                  ("industryId", symbol, name, "assetType", "capBasis", source,
                   "sourceRef", description, note, "createdAt")
                SELECT i.id, %s, %s, %s::"AssetType", %s::"CapBasis", %s, %s, %s, %s, now()
                FROM "Industry" i WHERE i.slug = %s
                ON CONFLICT ("industryId", symbol) DO UPDATE
                SET name = EXCLUDED.name, "assetType" = EXCLUDED."assetType",
                    "capBasis" = EXCLUDED."capBasis", source = EXCLUDED.source,
                    "sourceRef" = EXCLUDED."sourceRef", note = EXCLUDED.note
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

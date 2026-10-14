"""Candidate events for the historical event corpus. NOT evidence: events.py verifies each one.

A candidate is a name, a category, the date it is claimed to have happened, a search phrase used to
find the Wikipedia article about it, and the instrument whose price reaction is checked. The list
is written from memory, so any entry may be wrong; the point of events.py is that a wrong date
or a wrong event fails verification and is reported as such instead of counted.

Instrument keys: MKT (equal-weight US stocks in the database), PSX (equal-weight Pakistan stocks),
BTC, ETH, OIL (CL=F), GOLD (GC=F), a forex symbol such as EURUSD, or a stock ticker.

`cluster` groups candidates that share one root cause, so a cascade is one cluster and not many;
omitted means the event is its own cluster.
"""

E = []


def ev(name, cat, date, q, inst="MKT", cluster=None):
    E.append(dict(name=name, category=cat, date=date, query=q, instrument=inst,
                  cluster=cluster or name))


# ---- health ----
ev("Wuhan lockdown begins", "health", "2020-01-23", "Wuhan lockdown 23 January 2020", cluster="covid-crash")
ev("Italy national COVID lockdown", "health", "2020-03-09", "Italy nationwide lockdown 9 March 2020 COVID-19", cluster="covid-crash")
ev("WHO declares COVID-19 a pandemic", "health", "2020-03-11", "WHO declares COVID-19 pandemic 11 March 2020", cluster="covid-crash")
ev("Pfizer announces 90% vaccine efficacy", "health", "2020-11-09", "Pfizer BioNTech vaccine 90% effective interim results 9 November 2020")
ev("Moderna announces 94.5% vaccine efficacy", "health", "2020-11-16", "Moderna vaccine 94.5% efficacy 16 November 2020")
ev("First COVID-19 vaccine emergency authorisation in the US", "health", "2020-12-11", "FDA emergency use authorization Pfizer BioNTech vaccine 11 December 2020")
ev("Omicron variant designated of concern", "health", "2021-11-26", "Omicron variant designated variant of concern 26 November 2021")
ev("Shanghai lockdown", "health", "2022-03-28", "2022 Shanghai lockdown 28 March 2022")
ev("China ends zero-COVID measures", "health", "2022-12-07", "China ends zero-COVID ten new measures 7 December 2022")
ev("WHO declares mpox emergency", "health", "2022-07-23", "mpox public health emergency of international concern 23 July 2022")
ev("WHO ends COVID-19 emergency", "health", "2023-05-05", "WHO ends COVID-19 public health emergency of international concern 5 May 2023")

# ---- geopolitics and conflict ----
ev("Abqaiq-Khurais attack", "geopolitical", "2019-09-14", "Abqaiq Khurais attack 14 September 2019", "OIL")
ev("Pulwama attack", "geopolitical", "2019-02-14", "2019 Pulwama attack 14 February 2019", "PSX")
ev("Balakot airstrike", "geopolitical", "2019-02-26", "2019 Balakot airstrike 26 February 2019", "PSX")
ev("Soleimani killed", "geopolitical", "2020-01-03", "Killing of Qasem Soleimani 3 January 2020", "OIL")
ev("Taliban take Kabul", "geopolitical", "2021-08-15", "Fall of Kabul 15 August 2021")
ev("Russia recognises Donetsk and Luhansk", "geopolitical", "2022-02-21", "Russia recognition of Donetsk and Luhansk 21 February 2022", cluster="ukraine-invasion")
ev("Russia invades Ukraine", "geopolitical", "2022-02-24", "Russian invasion of Ukraine 24 February 2022", "OIL", cluster="ukraine-invasion")
ev("Pelosi visits Taiwan", "geopolitical", "2022-08-02", "Nancy Pelosi visit to Taiwan 2 August 2022")
ev("Nord Stream pipelines sabotage", "geopolitical", "2022-09-26", "Nord Stream pipeline sabotage 26 September 2022")
ev("Russia annexes four Ukrainian regions", "geopolitical", "2022-09-30", "Russian annexation of Donetsk Kherson Luhansk Zaporizhzhia 30 September 2022")
ev("Wagner mutiny", "geopolitical", "2023-06-23", "Wagner Group rebellion 23 June 2023")
ev("Hamas attack on Israel", "geopolitical", "2023-10-07", "7 October attacks Hamas Israel", "OIL")
ev("Houthis seize Galaxy Leader", "geopolitical", "2023-11-19", "Galaxy Leader hijacking 19 November 2023 Red Sea", "OIL")
ev("US and UK strike Houthi targets", "geopolitical", "2024-01-12", "Operation Poseidon Archer 12 January 2024", "OIL")
ev("Iran attacks Israel with drones and missiles", "geopolitical", "2024-04-13", "April 2024 Iranian strikes on Israel 13 April 2024", "OIL")
ev("Israel pager attacks in Lebanon", "geopolitical", "2024-09-17", "2024 Lebanon electronic device attacks 17 September 2024", "OIL")
ev("Iran missile attack on Israel", "geopolitical", "2024-10-01", "October 2024 Iranian strikes on Israel 1 October 2024", "OIL")
ev("Assad regime falls", "geopolitical", "2024-12-08", "Fall of the Assad regime 8 December 2024")
ev("India-Pakistan strikes (Operation Sindoor)", "geopolitical", "2025-05-07", "Operation Sindoor 7 May 2025", "PSX")
ev("India-Pakistan ceasefire", "geopolitical", "2025-05-10", "2025 India-Pakistan ceasefire 10 May 2025", "PSX")
ev("Israel launches strikes on Iran", "geopolitical", "2025-06-13", "Operation Rising Lion 13 June 2025", "OIL", cluster="israel-iran-2025")
ev("US strikes Iranian nuclear sites", "geopolitical", "2025-06-22", "Operation Midnight Hammer 22 June 2025", "OIL", cluster="israel-iran-2025")

# ---- central banks and policy ----
ev("Fed signals patience on rates (Powell)", "monetary", "2019-01-04", "Powell patient January 4 2019 Federal Reserve")
ev("Fed cuts rates for first time since 2008", "monetary", "2019-07-31", "July 2019 FOMC rate cut 31 July 2019")
ev("US repo market spike", "monetary", "2019-09-17", "September 2019 repurchase agreement market turmoil 17 September 2019")
ev("Fed emergency 50bp cut", "monetary", "2020-03-03", "Federal Reserve emergency rate cut 3 March 2020", cluster="fed-covid-response")
ev("Fed cuts to zero and restarts QE", "monetary", "2020-03-15", "Federal Reserve cuts rates to zero 15 March 2020", cluster="fed-covid-response")
ev("Fed announces unlimited QE", "monetary", "2020-03-23", "Federal Reserve unlimited quantitative easing 23 March 2020", cluster="fed-covid-response")
ev("ECB Lagarde spreads remark", "monetary", "2020-03-12", "Lagarde not here to close spreads 12 March 2020", "EURUSD")
ev("ECB launches PEPP", "monetary", "2020-03-18", "Pandemic Emergency Purchase Programme 18 March 2020", "EURUSD")
ev("Fed adopts average inflation targeting", "monetary", "2020-08-27", "Powell Jackson Hole 27 August 2020 average inflation targeting")
ev("Fed hawkish dot plot shift", "monetary", "2021-06-16", "June 2021 FOMC dot plot 16 June 2021")
ev("Fed announces taper of asset purchases", "monetary", "2021-11-03", "Federal Reserve taper announcement 3 November 2021")
ev("Fed raises rates for first time in the cycle", "monetary", "2022-03-16", "Federal Reserve raises rates 16 March 2022 first hike")
ev("Fed raises 75bp", "monetary", "2022-06-15", "Federal Reserve 75 basis point hike 15 June 2022")
ev("ECB first rate hike in 11 years", "monetary", "2022-07-21", "ECB raises rates 50 basis points 21 July 2022", "EURUSD")
ev("Powell Jackson Hole 'pain' speech", "monetary", "2022-08-26", "Powell Jackson Hole 26 August 2022 speech", cluster="powell-jh-2022")
ev("UK mini-budget", "monetary", "2022-09-23", "Growth Plan 2022 mini-budget 23 September 2022", "GBPUSD", cluster="uk-gilt-crisis")
ev("Bank of England gilt intervention", "monetary", "2022-09-28", "Bank of England emergency gilt purchases 28 September 2022", "GBPUSD", cluster="uk-gilt-crisis")
ev("BoJ widens yield curve control band", "monetary", "2022-12-20", "Bank of Japan yield curve control 20 December 2022", "USDJPY")
ev("Fed pivot dot plot", "monetary", "2023-12-13", "December 2023 FOMC rate cuts projected 13 December 2023")
ev("BoJ ends negative interest rates", "monetary", "2024-03-19", "Bank of Japan ends negative interest rate 19 March 2024", "USDJPY")
ev("BoJ raises rates", "monetary", "2024-07-31", "Bank of Japan raises rate 0.25 31 July 2024", "USDJPY", cluster="aug-2024-unwind")
ev("Fed first cut of the cycle, 50bp", "monetary", "2024-09-18", "Federal Reserve cuts rates 50 basis points 18 September 2024")
ev("Fed hawkish cut", "monetary", "2024-12-18", "December 2024 FOMC 18 December 2024 rate cut")
ev("Powell dovish Jackson Hole", "monetary", "2025-08-22", "Powell Jackson Hole 22 August 2025")
ev("Fed cuts rates (September 2025)", "monetary", "2025-09-17", "Federal Reserve cut rates 17 September 2025")
ev("Turkish central bank governor dismissed", "monetary", "2021-03-20", "Naci Ağbal dismissed 20 March 2021 Turkey central bank", "USDTRY")

# ---- macro data shocks ----
ev("Hot US CPI, September 2022", "macro-data", "2022-09-13", "CPI 13 September 2022 inflation report stocks plunge")
ev("Cool US CPI, November 2022", "macro-data", "2022-11-10", "CPI 10 November 2022 inflation report stocks rally")
ev("Weak US payrolls trigger Sahm rule", "macro-data", "2024-08-02", "July 2024 jobs report 2 August 2024 Sahm rule", cluster="aug-2024-unwind")
ev("Payroll revisions shock", "macro-data", "2025-08-01", "August 2025 jobs report revisions 1 August 2025")

# ---- banks and credit ----
ev("Greensill collapse", "banking", "2021-03-08", "Greensill Capital collapse 8 March 2021")
ev("Archegos margin calls", "banking", "2021-03-26", "Archegos Capital Management collapse 26 March 2021 block trades")
ev("Evergrande misses bond payment", "banking", "2021-12-09", "Evergrande default December 2021 9 December")
ev("Silvergate wind-down", "banking", "2023-03-08", "Silvergate Bank wind down 8 March 2023", cluster="march-2023-banks")
ev("Silicon Valley Bank collapse", "banking", "2023-03-10", "Collapse of Silicon Valley Bank 10 March 2023", cluster="march-2023-banks")
ev("Signature Bank closed", "banking", "2023-03-12", "Signature Bank closure 12 March 2023", cluster="march-2023-banks")
ev("UBS agrees to buy Credit Suisse", "banking", "2023-03-19", "UBS takeover of Credit Suisse 19 March 2023", cluster="march-2023-banks")
ev("First Republic seized", "banking", "2023-05-01", "First Republic Bank failure 1 May 2023")
ev("Fitch downgrades US credit rating", "banking", "2023-08-01", "Fitch downgrades United States credit rating 1 August 2023")
ev("Evergrande liquidation ordered", "banking", "2024-01-29", "Evergrande liquidation order Hong Kong 29 January 2024")
ev("Moody's downgrades US credit rating", "banking", "2025-05-16", "Moody's downgrades United States credit rating 16 May 2025")

# ---- market structure and crashes ----
ev("Oil price war sparks crash", "market-structure", "2020-03-09", "2020 stock market crash 9 March 2020 oil price war", cluster="covid-crash")
ev("Worst day of the COVID crash", "market-structure", "2020-03-16", "2020 stock market crash 16 March 2020 Dow Jones", cluster="covid-crash")
ev("GameStop short squeeze peak", "market-structure", "2021-01-28", "GameStop short squeeze 28 January 2021 Robinhood", "GME")
ev("Silver squeeze rally", "market-structure", "2021-02-01", "silver short squeeze 1 February 2021 Reddit")
ev("Global volatility spike and carry-trade unwind", "market-structure", "2024-08-05", "2024 stock market selloff 5 August 2024 yen carry trade", cluster="aug-2024-unwind")
ev("DeepSeek selloff", "market-structure", "2025-01-27", "DeepSeek Nvidia market capitalization loss 27 January 2025", "NVDA")
ev("Liberation Day tariffs announced", "market-structure", "2025-04-02", "Liberation Day tariffs 2 April 2025", cluster="tariff-shock-2025")
ev("US tariff pause rally", "market-structure", "2025-04-09", "9 April 2025 tariff pause stock market surge", cluster="tariff-shock-2025")
ev("Record crypto liquidations", "market-structure", "2025-10-10", "10 October 2025 cryptocurrency liquidations", "BTC")

# ---- energy and commodities ----
ev("OPEC+ talks collapse", "energy", "2020-03-06", "2020 Russia-Saudi Arabia oil price war OPEC+ 6 March 2020", "OIL")
ev("WTI crude settles negative", "energy", "2020-04-20", "WTI crude oil negative price 20 April 2020", "OIL")
ev("Texas winter storm", "energy", "2021-02-15", "February 2021 North American winter storm Texas power crisis 15 February 2021", "OIL")
ev("Suez Canal blocked by Ever Given", "energy", "2021-03-23", "2021 Suez Canal obstruction Ever Given 23 March 2021", "OIL")
ev("Colonial Pipeline ransomware", "energy", "2021-05-07", "Colonial Pipeline ransomware attack 7 May 2021", "OIL")
ev("Brent reaches $139", "energy", "2022-03-07", "Brent crude 7 March 2022 highest since 2008", "OIL")
ev("LME nickel squeeze", "energy", "2022-03-08", "2022 LME nickel short squeeze 8 March 2022", "OIL")
ev("Nord Stream 1 shut", "energy", "2022-09-02", "Nord Stream 1 shutdown 2 September 2022", "OIL")
ev("OPEC+ announces deep cut", "energy", "2022-10-05", "OPEC+ 2 million barrels per day cut 5 October 2022", "OIL")
ev("G7 Russian oil price cap", "energy", "2022-12-05", "G7 price cap Russian oil 5 December 2022", "OIL")
ev("Saudi-led surprise OPEC+ cut", "energy", "2023-04-02", "OPEC+ surprise cut 2 April 2023", "OIL")

# ---- technology and corporate ----
ev("Boeing 737 MAX grounded in the US", "corporate", "2019-03-13", "Boeing 737 MAX groundings 13 March 2019", "BA")
ev("Tesla added to S&P 500", "corporate", "2020-12-21", "Tesla S&P 500 inclusion 21 December 2020", "TSLA")
ev("Microsoft agrees to buy Activision", "corporate", "2022-01-18", "Microsoft acquisition of Activision Blizzard 18 January 2022", "MSFT")
ev("Meta shares plunge after earnings", "corporate", "2022-02-03", "Meta Platforms stock drop 3 February 2022 earnings", "META")
ev("Netflix reports first subscriber loss", "corporate", "2022-04-20", "Netflix loses subscribers 20 April 2022", "NFLX")
ev("Musk agrees to buy Twitter", "corporate", "2022-04-25", "Twitter acquisition by Elon Musk 25 April 2022", "TWTR")
ev("ChatGPT released", "corporate", "2022-11-30", "ChatGPT launch 30 November 2022")
ev("Google Bard demo error", "corporate", "2023-02-08", "Google Bard demonstration error 8 February 2023", "GOOGL")
ev("Nvidia blowout guidance", "corporate", "2023-05-24", "Nvidia earnings 24 May 2023 guidance stock surges", "NVDA")
ev("OpenAI board fires Altman", "corporate", "2023-11-17", "Removal of Sam Altman 17 November 2023 OpenAI")
ev("Boeing 737 MAX 9 door plug blowout", "corporate", "2024-01-05", "Alaska Airlines Flight 1282 5 January 2024", "BA")
ev("Nvidia becomes most valuable company", "corporate", "2024-06-18", "Nvidia becomes world's most valuable company 18 June 2024", "NVDA")
ev("CrowdStrike outage", "corporate", "2024-07-19", "2024 CrowdStrike incident 19 July 2024", "CRWD")
ev("Intel plunges on earnings and layoffs", "corporate", "2024-08-02", "Intel stock plunge 2 August 2024 layoffs", "INTC")
ev("Oracle surges on cloud backlog", "corporate", "2025-09-10", "Oracle stock surge 10 September 2025 remaining performance obligations", "ORCL")
ev("Nvidia and OpenAI announce investment deal", "corporate", "2025-09-22", "Nvidia OpenAI 100 billion investment 22 September 2025", "NVDA")

# ---- crypto ----
ev("Bitcoin third halving", "crypto", "2020-05-11", "Bitcoin halving 11 May 2020", "BTC")
ev("Tesla buys $1.5bn of Bitcoin", "crypto", "2021-02-08", "Tesla 1.5 billion Bitcoin purchase 8 February 2021", "BTC")
ev("Coinbase direct listing", "crypto", "2021-04-14", "Coinbase direct listing Nasdaq 14 April 2021", "BTC")
ev("May 2021 crypto crash", "crypto", "2021-05-19", "May 2021 cryptocurrency crash 19 May 2021 China", "BTC")
ev("China bans crypto transactions", "crypto", "2021-09-24", "China cryptocurrency ban 24 September 2021", "BTC")
ev("TerraUSD depeg", "crypto", "2022-05-09", "Terra Luna collapse 9 May 2022 TerraUSD depeg", "BTC")
ev("Celsius freezes withdrawals", "crypto", "2022-06-12", "Celsius Network freeze withdrawals 12 June 2022", "BTC")
ev("Ethereum Merge", "crypto", "2022-09-15", "The Merge Ethereum 15 September 2022", "ETH")
ev("FTX collapse", "crypto", "2022-11-08", "Bankruptcy of FTX 8 November 2022 Binance", "BTC")
ev("Binance pleads guilty, CZ resigns", "crypto", "2023-11-21", "Changpeng Zhao pleads guilty 21 November 2023", "BTC")
ev("Spot Bitcoin ETFs approved", "crypto", "2024-01-10", "SEC approves spot Bitcoin ETFs 10 January 2024", "BTC")
ev("Bitcoin fourth halving", "crypto", "2024-04-19", "Bitcoin halving 19 April 2024", "BTC")
ev("Spot Ether ETFs begin trading", "crypto", "2024-07-23", "spot Ethereum ETF begin trading 23 July 2024", "ETH")
ev("Bybit hack", "crypto", "2025-02-21", "Bybit hack 21 February 2025 Lazarus", "ETH")
ev("US Strategic Bitcoin Reserve order", "crypto", "2025-03-06", "Strategic Bitcoin Reserve executive order 6 March 2025", "BTC")
ev("GENIUS Act signed", "crypto", "2025-07-18", "GENIUS Act signed 18 July 2025 stablecoin", "BTC")

# ---- politics, trade and law ----
ev("Trump raises China tariff threat on Twitter", "political", "2019-05-05", "Trump tariffs China 5 May 2019 tweet 25 percent")
ev("Trump announces tariffs on remaining Chinese goods", "political", "2019-08-01", "1 August 2019 Trump tariff $300 billion Chinese goods")
ev("China lets yuan weaken past 7", "political", "2019-08-05", "5 August 2019 yuan breaks 7 currency manipulator")
ev("UK general election", "political", "2019-12-12", "2019 United Kingdom general election 12 December 2019", "GBPUSD")
ev("US-China phase one trade deal signed", "political", "2020-01-15", "Phase one trade deal signed 15 January 2020")
ev("Brexit takes effect", "political", "2020-01-31", "Brexit 31 January 2020 withdrawal agreement takes effect", "GBPUSD")
ev("US presidential election day 2020", "political", "2020-11-03", "2020 United States presidential election 3 November 2020")
ev("Georgia Senate runoffs", "political", "2021-01-05", "2021 United States Senate runoff elections in Georgia 5 January 2021")
ev("US Capitol attack", "political", "2021-01-06", "January 6 United States Capitol attack 6 January 2021")
ev("American Rescue Plan signed", "political", "2021-03-11", "American Rescue Plan Act signed 11 March 2021")
ev("Infrastructure bill signed", "political", "2021-11-15", "Infrastructure Investment and Jobs Act signed 15 November 2021")
ev("Inflation Reduction Act signed", "political", "2022-08-16", "Inflation Reduction Act signed 16 August 2022")
ev("Imran Khan ousted", "political", "2022-04-10", "2022 vote of no confidence Imran Khan 10 April 2022", "PSX")
ev("Imran Khan arrested", "political", "2023-05-09", "arrest of Imran Khan 9 May 2023", "PSX")
ev("Pakistan general election", "political", "2024-02-08", "2024 Pakistani general election 8 February 2024", "PSX")
ev("US debt ceiling suspension signed", "political", "2023-06-03", "Fiscal Responsibility Act of 2023 signed 3 June 2023")
ev("US presidential election day 2024", "political", "2024-11-05", "2024 United States presidential election 5 November 2024")
ev("Trump says he could fire Powell", "political", "2025-04-21", "Trump Powell fire 21 April 2025 Federal Reserve independence")
ev("US federal government shutdown", "political", "2025-10-01", "2025 United States federal government shutdown 1 October 2025")
ev("IMF approves Pakistan 2019 programme", "political", "2019-07-03", "IMF Pakistan $6 billion Extended Fund Facility 3 July 2019", "PSX")
ev("IMF approves Pakistan 2024 programme", "political", "2024-09-25", "IMF Pakistan $7 billion Extended Fund Facility 25 September 2024", "PSX")

# ---- natural disasters and accidents ----
ev("Hurricane Ian landfall", "disaster", "2022-09-28", "Hurricane Ian Florida landfall 28 September 2022")
ev("Turkey-Syria earthquake", "disaster", "2023-02-06", "2023 Turkey-Syria earthquake 6 February 2023", "USDTRY")
ev("Noto Peninsula earthquake", "disaster", "2024-01-01", "2024 Noto earthquake 1 January 2024", "USDJPY")
ev("Baltimore Key Bridge collapse", "disaster", "2024-03-26", "Francis Scott Key Bridge collapse 26 March 2024")
ev("Hurricane Helene", "disaster", "2024-09-26", "Hurricane Helene 26 September 2024 landfall")
ev("Los Angeles wildfires", "disaster", "2025-01-07", "January 2025 Southern California wildfires 7 January 2025")
ev("Pakistan floods", "disaster", "2022-08-25", "2022 Pakistan floods 25 August 2022 national emergency", "PSX")


# ---- official primary documents, keyed by event date (only monetary and macro-data events) ----
# The Federal Reserve and the Bureau of Labor Statistics publish each statement and release at a
# stable URL that encodes its date. events.py fetches each one and requires the claimed date to
# appear in the document itself; a 200 response alone is not accepted.
FED = "https://www.federalreserve.gov/newsevents/"
BLS = "https://www.bls.gov/news.release/archives/"
OFFICIAL = {
    "2019-01-04": [FED + "speech/powell20190104a.htm"],
    "2019-07-31": [FED + "pressreleases/monetary20190731a.htm"],
    "2020-03-03": [FED + "pressreleases/monetary20200303a.htm"],
    "2020-03-15": [FED + "pressreleases/monetary20200315a.htm"],
    "2020-03-23": [FED + "pressreleases/monetary20200323a.htm", FED + "pressreleases/monetary20200323b.htm"],
    "2020-08-27": [FED + "speech/powell20200827a.htm"],
    "2021-06-16": [FED + "pressreleases/monetary20210616a.htm"],
    "2021-11-03": [FED + "pressreleases/monetary20211103a.htm"],
    "2022-03-16": [FED + "pressreleases/monetary20220316a.htm"],
    "2022-06-15": [FED + "pressreleases/monetary20220615a.htm"],
    "2022-08-26": [FED + "speech/powell20220826a.htm"],
    "2023-12-13": [FED + "pressreleases/monetary20231213a.htm"],
    "2024-09-18": [FED + "pressreleases/monetary20240918a.htm"],
    "2024-12-18": [FED + "pressreleases/monetary20241218a.htm"],
    "2025-08-22": [FED + "speech/powell20250822a.htm"],
    "2025-09-17": [FED + "pressreleases/monetary20250917a.htm"],
    "2022-09-13": [BLS + "cpi_09132022.htm"],
    "2022-11-10": [BLS + "cpi_11102022.htm"],
    "2024-08-02": [BLS + "empsit_08022024.htm"],
    "2025-08-01": [BLS + "empsit_08012025.htm"],
}

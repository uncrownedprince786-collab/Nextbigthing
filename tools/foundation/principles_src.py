"""Source list for the trading-principles corpus. Verified against Crossref by principles.py.

Each entry names a published finding and turns it into a hypothesis this repository could test
with its own data. Nothing here is a claim that the effect holds in this universe or after costs:
`status` stays "untested" until a walk-forward result exists. `needs` lists the inputs a test
requires; `testable_now` is True only when every one of them is already stored.

Inputs available today: price (OHLC), volume, industry membership, news counts and tone, scheduled
events, and the macro series in data/foundation/macro. Not available: company fundamentals,
analyst estimates, short interest, options, order books.

Fields: id, name, family, finding (what the paper reports, one sentence), doi, author, year,
title (a distinctive fragment for matching), signal (how to compute it), horizon, sign (expected
direction), needs, test (the pre-registered comparison), universe.
"""

P = []


def add(id, name, family, finding, doi, author, year, title, signal, horizon, sign, needs, test,
        universe="equity"):
    P.append(dict(id=id, name=name, family=family, finding=finding, doi=doi, author=author,
                  year=year, title=title, signal=signal, horizon=horizon, sign=sign,
                  needs=needs, test=test, universe=universe))


PX = ["price"]
PV = ["price", "volume"]
XS = "top-minus-bottom quintile of the signal, rebalanced at the horizon, net of the assumed cost band"
TS = "position sign follows the signal; compare with buy-and-hold on the same asset, net of costs"

# ---- momentum and trend ----
add("MOM-XS-12-1", "Cross-sectional 12-1 month momentum", "momentum",
    "Stocks that did well over the prior 3-12 months continued to outperform over the next 3-12.",
    "10.1111/j.1540-6261.1993.tb04702.x", "Jegadeesh", 1993, "Returns to Buying Winners and Selling Losers",
    "return from t-252 to t-21 sessions, skipping the latest month", "21d", "+", PX, XS)
add("MOM-TS", "Time-series momentum", "momentum",
    "An asset's own past 1-12 month excess return predicts its next-month return across asset classes.",
    "10.1016/j.jfineco.2011.11.003", "Moskowitz", 2012, "Time series momentum",
    "sign of trailing 252-session return", "21d", "+", PX, TS, "all")
add("MOM-VALMOM", "Momentum and value across markets", "momentum",
    "Value and momentum premia exist across asset classes and are negatively correlated with each other.",
    "10.1111/jofi.12021", "Asness", 2013, "Value and Momentum Everywhere",
    "momentum leg only (value needs fundamentals): trailing 12-1 return rank within each asset class", "21d", "+", PX, XS, "all")
add("TREND-MA", "Moving-average timing rules", "momentum",
    "Simple moving-average and trading-range-break rules on the Dow index earned returns a random walk would not.",
    "10.1111/j.1540-6261.1992.tb04681.x", "Brock", 1992, "Simple Technical Trading Rules",
    "close above its 200-session mean => long, else flat", "daily", "+", PX, TS, "all")
add("TREND-FABER", "10-month trend filter for asset allocation", "momentum",
    "Holding an asset only while it is above its 10-month average reduced drawdowns at similar return.",
    "10.2139/ssrn.962461", "Faber", 2007, "Quantitative Approach to Tactical Asset Allocation",
    "month-end close above its 10-month mean", "monthly", "+", PX, TS, "all")
add("MOM-52WH", "Nearness to the 52-week high", "momentum",
    "A stock's closeness to its 52-week high predicts returns better than past return does.",
    "10.1111/j.1540-6261.2004.00695.x", "George", 2004, "52-Week High and Momentum Investing",
    "close divided by the trailing 252-session maximum close", "21d", "+", PX, XS)
add("TREND-CENTURY", "Trend following over a century", "momentum",
    "A diversified trend-following rule was profitable in every decade from 1880 to 2013.",
    "10.3905/jpm.2017.44.1.015", "Hurst", 2017, "Century of Evidence on Trend-Following",
    "sign of trailing 1, 3 and 12 month return, equal-weighted vote", "monthly", "+", PX, TS, "all")
add("MOM-CRASH", "Momentum crashes in rebounding bear markets", "momentum",
    "Momentum loses heavily when a bear market turns and volatility is high.",
    "10.1016/j.jfineco.2015.12.002", "Daniel", 2016, "Momentum crashes",
    "momentum exposure scaled to zero when the market is below its 200-session mean and trailing volatility is in its top quintile", "21d", "+", PX,
    "momentum return in those regimes versus the unconditional momentum return")
add("MOM-VOLSCALE", "Volatility-scaled momentum", "momentum",
    "Scaling momentum by its own trailing volatility raises Sharpe and reduces crash risk.",
    "10.1016/j.jfineco.2014.11.010", "Barroso", 2015, "Momentum has its moments",
    "weight = target volatility / trailing 126-session realised volatility of the momentum leg", "21d", "+", PX,
    "scaled versus unscaled momentum, net of costs")
add("MOM-RECENT", "Intermediate-horizon momentum", "momentum",
    "Returns from 7-12 months ago predict future returns better than returns from the latest 6 months.",
    "10.1016/j.jfineco.2011.05.003", "Novy-Marx", 2012, "Is momentum really momentum",
    "trailing return from t-252 to t-126 versus t-126 to t-21", "21d", "+", PX, XS)
add("MOM-INDUSTRY", "Industry momentum", "momentum",
    "Much of stock momentum is explained by industry momentum.",
    "10.1111/0022-1082.00146", "Moskowitz", 1999, "Do Industries Explain Momentum",
    "trailing 6-month mean return of the asset's industry, in the stored industry map", "21d", "+", PX, XS)
add("MOM-INTRADAY", "Market intraday momentum", "momentum",
    "The first half-hour return predicts the last half-hour return on the same day.",
    "10.1016/j.jfineco.2018.05.003", "Gao", 2018, "Market intraday momentum",
    "sign of the first 30-minute return versus the last 30-minute return (IntradayBar)", "intraday", "+",
    ["intraday bars"], "hit rate and mean return of the last 30 minutes conditional on the first; needs more than the ~8 stored session days")
add("TECH-FOUND", "Pattern recognition in prices", "momentum",
    "Several technical patterns carry incremental information beyond unconditional returns when detected by kernel regression.",
    "10.1111/0022-1082.00265", "Lo", 2000, "Foundations of Technical Analysis",
    "kernel-smoothed price; count of head-and-shoulders and double-top detections", "5d", "-", PX,
    "conditional return distribution against its unconditional distribution, goodness-of-fit test")
add("TECH-PROFIT", "Profitability of technical analysis, survey", "momentum",
    "Early studies find technical rules profitable; later ones find profits shrink after costs and data snooping.",
    "10.1111/j.1467-6419.2007.00519.x", "Park", 2007, "profitability of technical analysis",
    "moving-average crossover 20/50", "daily", "+", PX, TS, "all")
add("MOM-FUND-ABN", "Momentum and persistence", "momentum",
    "A four-factor model with momentum explains much of fund performance persistence.",
    "10.1111/j.1540-6261.1997.tb03808.x", "Carhart", 1997, "Persistence in Mutual Fund Performance",
    "momentum factor loading of each asset on a long-short momentum portfolio", "63d", "+", PX,
    "alpha after the four factors is not distinguishable from zero")

# ---- reversal ----
add("REV-ST-1M", "One-month reversal", "reversal",
    "Last month's losers outperform last month's winners the following month.",
    "10.1111/j.1540-6261.1990.tb05110.x", "Jegadeesh", 1990, "Predictable Behavior of Security Returns",
    "negative of the trailing 21-session return", "21d", "+", PX, XS)
add("REV-WEEKLY", "Weekly reversal", "reversal",
    "Weekly returns of individual securities are negatively autocorrelated, profitably for contrarians.",
    "10.2307/2937928", "Lehmann", 1990, "Fads, Martingales, and Market Efficiency",
    "negative of the trailing 5-session return, weighted by deviation from the cross-sectional mean", "5d", "+", PX, XS)
add("REV-LOMAC", "Contrarian profits and overreaction", "reversal",
    "Contrarian profits arise partly from cross-autocorrelation, not only overreaction.",
    "10.1093/rfs/3.2.175", "Lo", 1990, "contrarian profits due to stock market overreaction",
    "own-lag versus cross-lag decomposition of weekly returns", "5d", "+", PX,
    "share of reversal profit from the own-asset component")
add("REV-LTR", "Long-term overreaction", "reversal",
    "Three-to-five-year losers outperform winners over the following three to five years.",
    "10.1111/j.1540-6261.1985.tb05004.x", "De Bondt", 1985, "Does the Stock Market Overreact",
    "trailing 36-month return, negated (needs >3y history per asset)", "36m", "+", PX, XS)
add("REV-LIQ", "Reversal as liquidity provision", "reversal",
    "Short-term reversals are the compensation for supplying liquidity and are larger when VIX is high.",
    "10.1093/rfs/hhr144", "Nagel", 2012, "Evaporating Liquidity",
    "one-month reversal conditioned on VIX above its trailing 252-session median (macro: VIXCLS)", "21d", "+",
    ["price", "macro:VIXCLS"], "reversal return in high-VIX versus low-VIX months")
add("REV-VOLUME", "Reversal conditioned on volume", "reversal",
    "Returns on high-volume days reverse less than on low-volume days.",
    "10.1111/j.1540-6261.2006.01070.x", "Avramov", 2006, "Liquidity and Autocorrelations",
    "one-week return interacted with turnover relative to its own 60-session mean", "5d", "+", PV, XS)
add("REV-NEWS", "Reversal separated by news", "reversal",
    "Reversal is concentrated in moves with no accompanying news; moves with news drift.",
    "10.1016/S0304-405X(03)00146-6", "Chan", 2003, "Stock price reaction to news and no-news",
    "weekly return split by whether the News table has any story for the asset that week", "21d", "+",
    ["price", "news"], "reversal in no-news weeks versus drift in news weeks")
add("REV-DA", "Reversal and the information in a move", "reversal",
    "Short-term reversal is stronger when the return is not backed by public news or volume.",
    "10.1287/mnsc.2013.1766", "Da", 2014, "Closer Look at the Short-Term Return Reversal",
    "one-month return divided into a news-driven and non-news-driven part using News counts", "21d", "+",
    ["price", "news"], XS)
add("SHOCK-INFO", "Returns after large price shocks", "reversal",
    "After large one-day moves, drift follows when there was news and reversal when there was not.",
    "10.1016/j.jfineco.2011.09.010", "Savor", 2012, "Stock returns after major price shocks",
    "a one-day move beyond 3 trailing standard deviations, split by presence of same-day news", "5d", "mixed",
    ["price", "news"], "mean 5-day return after shocks, with and without news")

# ---- volume and liquidity ----
add("VOL-HIGH", "High-volume return premium", "volume",
    "Stocks with unusually high volume over a day or week earn higher returns the next month.",
    "10.1111/0022-1082.00338", "Gervais", 2001, "High-Volume Return Premium",
    "volume divided by its own trailing 50-session mean", "21d", "+", PV, XS)
add("VOL-MOMVOL", "Momentum and trading volume", "volume",
    "Past winners with high volume continue; past losers with high volume continue to lose.",
    "10.1111/0022-1082.00280", "Lee", 2000, "Price Momentum and Trading Volume",
    "momentum quintile crossed with a volume-turnover tercile", "63d", "+", PV, XS)
add("LIQ-AMIHUD", "Illiquidity premium", "volume",
    "Less liquid stocks earn higher expected returns, measured by absolute return per dollar of volume.",
    "10.1016/S1386-4181(01)00024-6", "Amihud", 2002, "Illiquidity and stock returns",
    "mean of |daily return| / (close x volume) over 63 sessions", "21d", "+", PV, XS)
add("LIQ-TURNOVER", "Trading activity and returns", "volume",
    "Stocks with higher turnover have lower expected returns, the reverse of an illiquidity premium.",
    "10.1016/S0304-405X(00)00080-5", "Chordia", 2001, "Trading activity and expected stock returns",
    "mean daily share volume over 63 sessions divided by shares outstanding (shares outstanding not stored; use volume rank as the proxy)", "21d", "-", PV, XS)
add("COST-LESMOND", "Zero-return days as a cost proxy", "volume",
    "The share of zero-return days estimates the trading cost of an asset.",
    "10.1093/rfs/12.5.1113", "Lesmond", 1999, "New Estimate of Transaction Costs",
    "share of sessions with an unchanged close over 126 sessions", "21d", "-", PX,
    "use as a cost covariate: check that net returns fall as the proxy rises")

# ---- risk and quality (price-based legs only are testable now) ----
add("RISK-BAB", "Betting against beta", "risk",
    "Low-beta assets earn higher risk-adjusted returns than high-beta assets.",
    "10.1016/j.jfineco.2013.10.005", "Frazzini", 2014, "Betting against beta",
    "trailing 252-session beta to the equal-weighted universe return", "21d", "-", PX, XS)
add("RISK-IVOL", "Idiosyncratic volatility", "risk",
    "Stocks with high idiosyncratic volatility earn low subsequent returns.",
    "10.1111/j.1540-6261.2006.00836.x", "Ang", 2006, "Cross-Section of Volatility and Expected Returns",
    "standard deviation of residuals from a one-factor market regression over 63 sessions", "21d", "-", PX, XS)
add("RISK-VOLMGD", "Volatility-managed portfolios", "risk",
    "Scaling exposure inversely to recent realised volatility improves Sharpe ratios.",
    "10.1111/jofi.12513", "Moreira", 2017, "Volatility-Managed Portfolios",
    "weight = target / realised variance of the previous month", "21d", "+", PX,
    "scaled versus unscaled, net of the cost of the extra turnover")
add("RISK-VOLTARGET", "Volatility targeting", "risk",
    "Volatility targeting reduces tail risk for risk assets, with limited effect on Sharpe.",
    "10.3905/jpm.2018.45.1.014", "Harvey", 2018, "Impact of Volatility Targeting",
    "scale to 10% annualised volatility using a 60-session estimate", "daily", "+", PX,
    "drawdown and tail loss of targeted versus untargeted series")
add("RISK-STOP", "Stop-loss rules", "risk",
    "A stop-loss helps in a momentum world and costs in a random walk; its value depends on the return process.",
    "10.1016/j.finmar.2013.07.004", "Kaminski", 2014, "When do stop-loss rules stop losses",
    "exit when the close falls a fixed multiple of trailing volatility below the entry; compare with stored invalidate levels", "setup", "+", PX,
    "expectancy of the stop rule versus holding to the horizon, using the stored setup levels")
add("RISK-KELLY", "Growth-optimal sizing", "risk",
    "Maximising expected log wealth gives the bet size that grows capital fastest and is ruinous when over-bet.",
    "10.1002/j.1538-7305.1956.tb03809.x", "Kelly", 1956, "New Interpretation of Information Rate",
    "fractional Kelly from the measured hit rate and payoff ratio of a rule, with a shrinkage floor", "setup", "+", PX,
    "terminal wealth and drawdown for 0.25, 0.5 and 1.0 Kelly against fixed fractional sizing")
add("QUAL-PRICE", "Low-volatility anomaly (price proxy for quality)", "risk",
    "Low-risk stocks have earned higher risk-adjusted returns than high-risk stocks.",
    "10.1016/j.jfineco.2014.10.010", "Fama", 2015, "five-factor asset pricing model",
    "trailing 252-session volatility, negated (the profitability and investment legs need fundamentals)", "21d", "+", PX, XS)

# ---- events, news and announcements ----
add("EVT-PEAD", "Post-earnings-announcement drift", "events",
    "After earnings surprises, prices keep moving in the surprise's direction for about 60 days.",
    "10.2307/2491062", "Bernard", 1989, "Post-earnings-announcement drift",
    "return from the earnings session to +60d, ranked by the day-0 abnormal return (a price-based surprise proxy; analyst estimates are not stored)", "60d", "+",
    ["price", "event:earnings"], "drift after the top versus bottom decile of day-0 abnormal return")
add("EVT-BALLBROWN", "Earnings information is reflected in prices", "events",
    "Most of the information in annual earnings is already in prices before the announcement.",
    "10.2307/2490232", "Ball", 1968, "Empirical Evaluation of Accounting Income Numbers",
    "pre-announcement drift over the 60 sessions before the event, by sign of the day-0 move", "60d", "+",
    ["price", "event:earnings"], "share of the total move realised before the announcement")
add("EVT-FOMC-DRIFT", "Pre-FOMC announcement drift", "events",
    "US equities earn most of their annual excess return in the 24 hours before scheduled FOMC announcements.",
    "10.1111/jofi.12196", "Lucca", 2015, "Pre-FOMC Announcement Drift",
    "long the index from the close before the announcement day to the announcement", "1d", "+",
    ["price", "event:fomc"], "mean return on FOMC-eve sessions versus all other sessions")
add("EVT-FED-SURPRISE", "Market reaction to policy surprises", "events",
    "An unexpected 25 bp rate cut raises stock prices about 1%, working mainly through expected excess returns.",
    "10.1111/j.1540-6261.2005.00760.x", "Bernanke", 2005, "Stock Market's Reaction to Federal Reserve Policy",
    "index return on the decision day against the change in DFF over the following sessions as a surprise proxy", "1d", "-",
    ["price", "event:fomc", "macro:DFF"], "slope of day-0 return on the rate change")
add("EVT-UNEMP", "Unemployment news and stocks", "events",
    "Bad unemployment news lifts stocks in expansions and lowers them in recessions.",
    "10.1111/j.1540-6261.2005.00741.x", "Boyd", 2005, "Stock Market's Reaction to Unemployment News",
    "index return on payroll release days by sign of the UNRATE change and the regime from the 10y-3m spread", "1d", "mixed",
    ["price", "macro:UNRATE", "macro:T10Y3M"], "regime-conditional mean reaction")
add("EVT-MACRO-JUMPS", "Macro announcements and returns", "events",
    "Conditional means of FX, bond and equity returns jump on macro announcements, with bad news mattering more in good times.",
    "10.1257/000282803322157151", "Andersen", 2003, "Micro Effects of Macro Announcements",
    "absolute return on release days relative to non-release days, per series in data/foundation/macro", "1d", "+",
    ["price", "macro"], "ratio of mean absolute return on release days to other days, bootstrap interval")
add("NEWS-TONE", "Media pessimism and returns", "events",
    "High media pessimism predicts downward pressure on prices followed by reversion.",
    "10.1111/j.1540-6261.2007.01232.x", "Tetlock", 2007, "Giving content to investor sentiment",
    "daily share of negative tone across the stored News rows", "5d", "-", ["price", "news"],
    "next-5-day return by tone tercile, net of costs")
add("NEWS-UNDERREACT", "Disposition effect and underreaction", "events",
    "Prices underreact to news where holders are sitting on gains or losses.",
    "10.1111/j.1540-6261.2006.00896.x", "Frazzini", 2006, "Disposition Effect and Underreaction to News",
    "news-day return interacted with the capital-gains overhang proxy (price relative to the trailing 252-session volume-weighted close)", "21d", "+",
    ["price", "volume", "news"], XS)
add("LINK-CUSTOMER", "Economic links and predictable returns", "events",
    "A firm's returns are predicted by those of its customers' stocks, which investors process slowly.",
    "10.1111/j.1540-6261.2008.01379.x", "Cohen", 2008, "Economic Links and Predictable Returns",
    "lagged return of linked assets; customer-supplier links are not stored, industry peers are the proxy", "21d", "+",
    ["price", "industry"], XS)
add("LINK-INDUSTRY-LEAD", "Industry lead-lag", "events",
    "Returns of large industries lead returns of related smaller ones.",
    "10.1093/rfs/hhm003", "Hou", 2007, "Industry Information Diffusion and the Lead-lag Effect",
    "lagged industry mean return as a predictor of member returns, controlling for own-lag", "5d", "+",
    ["price", "industry"], XS)
add("SENT-BW", "Investor sentiment", "events",
    "Stocks that are hard to value and hard to arbitrage earn low returns after high-sentiment periods.",
    "10.1111/j.1540-6261.2006.00885.x", "Baker", 2006, "Investor Sentiment and the Cross-Section",
    "market sentiment proxy from VIXCLS and UMCSENT; interact with trailing volatility rank", "21d", "mixed",
    ["price", "macro:VIXCLS", "macro:UMCSENT"], "long-short return in high versus low sentiment states")
add("ATTN-BARBER", "Attention-driven buying", "events",
    "Individual investors buy stocks that grab attention: high volume, extreme returns, news.",
    "10.1093/rfs/hhm079", "Barber", 2008, "All That Glitters",
    "abnormal volume x absolute return x news-day indicator", "5d", "-", ["price", "volume", "news"],
    "next-week return by attention tercile")

# ---- macro and regimes ----
add("MACRO-CURVE", "The yield curve and recessions", "macro",
    "The slope of the yield curve predicts recessions and growth better than other financial variables.",
    "10.1162/003465398557320", "Estrella", 1998, "Predicting U.S. Recessions",
    "T10Y3M below zero (macro: T10Y3M, availableAt respected)", "12m", "-",
    ["price", "macro:T10Y3M"], "equity return over the next 12 months after inversion versus otherwise")
add("MACRO-PREDICT", "Equity premium prediction is hard", "macro",
    "Most variables proposed to predict the equity premium fail out of sample.",
    "10.1093/rfs/hhm014", "Welch", 2008, "Comprehensive Look at the Empirical Performance of Equity Premium Prediction",
    "single-variable regressions of next-month index return on each macro series", "21d", "mixed",
    ["price", "macro"], "out-of-sample R squared against the historical mean, per series")
add("MACRO-CONSTRAINED", "Constrained predictors help out of sample", "macro",
    "Imposing sign and non-negativity constraints makes equity-premium predictors usable out of sample.",
    "10.1093/rfs/hhm055", "Campbell", 2008, "Predicting excess stock returns out of sample",
    "constrained regression forecast of the next month's return from the macro set", "21d", "mixed",
    ["price", "macro"], "out-of-sample R squared and the certainty-equivalent gain")
add("MACRO-VIXPREM", "Variance premium predicts returns", "macro",
    "The gap between implied and realised variance predicts equity returns at short horizons.",
    "10.1016/j.jeconom.2014.05.008", "Bekaert", 2014, "VIX, the variance premium and stock market volatility",
    "VIXCLS squared minus trailing 21-session realised variance of the index", "63d", "+",
    ["price", "macro:VIXCLS"], "predictive regression with an out-of-sample split")
add("MACRO-FEARGAUGE", "VIX as fear gauge", "macro",
    "Rising implied volatility coincides with falling equity prices, and spikes mark short-horizon turning points.",
    "10.3905/jpm.2000.319728", "Whaley", 2000, "Investor Fear Gauge",
    "VIXCLS above its trailing 252-session 90th percentile", "5d", "+",
    ["price", "macro:VIXCLS"], "mean next-5-day return after VIX spikes versus other days")

# ---- seasonality and calendar ----
add("CAL-HALLOWEEN", "Halloween indicator", "calendar",
    "Stock returns are higher from November to April than from May to October in most markets.",
    "10.1257/000282802762024683", "Bouman", 2002, "Halloween Indicator",
    "long only between 1 November and 30 April", "6m", "+", PX, TS, "all")
add("CAL-SEASONAL", "Same-month return seasonality", "calendar",
    "A stock's return in a given calendar month predicts its return in the same month in later years.",
    "10.1016/j.jfineco.2007.07.002", "Heston", 2008, "Seasonality in the cross-section of stock returns",
    "mean return of the asset in the same calendar month over prior years", "21d", "+", PX, XS)
add("CAL-JAN", "January and size", "calendar",
    "Small-capitalisation stocks earn abnormal returns in January.",
    "10.1016/0304-405X(83)90020-6", "Keim", 1983, "Size-related anomalies and stock return seasonality",
    "January indicator interacted with volume-based size proxy (market cap is stored only for part of the universe)", "21d", "+", PV, XS)
add("CAL-WEEKEND", "Weekend effect", "calendar",
    "Mean Monday returns are lower than other days'.",
    "10.1016/0304-405X(80)90021-5", "French", 1980, "Stock returns and the weekend effect",
    "day-of-week indicator on the index", "1d", "-", PX, "mean return by weekday with a Newey-West interval over the full history")

# ---- crypto, FX, commodities ----
add("CRYPTO-MOM", "Cryptocurrency momentum and size", "crypto",
    "Crypto returns are predicted by momentum and market-cap-related factors; the effect weakens with liquidity.",
    "10.1093/rfs/hhaa113", "Liu", 2021, "Risks and Returns of Cryptocurrency",
    "trailing 1-4 week return of each stored coin", "7d", "+", PX, XS, "crypto")
add("CRYPTO-FACTORS", "Common risk factors in crypto", "crypto",
    "A three-factor model with market, size and momentum prices the cross-section of cryptocurrency returns.",
    "10.1111/jofi.13119", "Liu", 2022, "Common Risk Factors in Cryptocurrency",
    "market, size (price-volume proxy) and momentum factors from the stored coins", "7d", "+", PV, XS, "crypto")
add("FX-MOM", "Currency momentum", "fx",
    "Past 1-12 month winners among currencies keep outperforming losers.",
    "10.1016/j.jfineco.2012.08.007", "Menkhoff", 2012, "Currency momentum strategies",
    "trailing 6-month return of each stored pair, ranked", "21d", "+", PX, XS, "fx")
add("FX-CARRY", "Carry and global FX risk", "fx",
    "High-interest currencies earn excess returns that compensate global risk.",
    "10.1093/rfs/hhr068", "Lustig", 2011, "Common Risk Factors in Currency Markets",
    "interest rate differential needs short rates per country (only US rates are stored); carry is not testable until they are", "21d", "+",
    ["price", "foreign short rates"], XS, "fx")
add("CARRY-GLOBAL", "Carry across asset classes", "fx",
    "Carry predicts returns in every asset class, with a common global factor.",
    "10.1016/j.jfineco.2017.11.002", "Koijen", 2018, "Carry",
    "needs futures curves or yields per asset; not stored", "21d", "+", ["price", "term structure"], XS, "all")
add("CMDTY-FACTS", "Commodity futures facts", "commodities",
    "Commodity futures returns are positively correlated with inflation and negatively with stocks and bonds.",
    "10.2469/faj.v62.n2.4083", "Gorton", 2006, "Facts and Fantasies about Commodity Futures",
    "rolling correlation of each stored commodity with CPIAUCSL changes (macro, availableAt respected)", "12m", "+",
    ["price", "macro:CPIAUCSL"], "sign and stability of the correlation across subperiods", "commodities")
add("CMDTY-STRATEGIC", "Strategic and tactical value of commodities", "commodities",
    "Commodity futures can diversify a portfolio and earn a risk premium tied to backwardation.",
    "10.2469/faj.v62.n2.4084", "Erb", 2006, "Strategic and Tactical Value of Commodity Futures",
    "trailing 12-month return as a tactical signal for each stored commodity", "21d", "+", PX, XS, "commodities")

# ---- evidence discipline: how to test, not what to trade ----
add("DISC-DEFLATED", "Deflated Sharpe ratio", "discipline",
    "A Sharpe ratio must be discounted for the number of trials and the non-normality of returns before it means anything.",
    "10.3905/jpm.2014.40.5.094", "Bailey", 2014, "Deflated Sharpe Ratio",
    "compute the deflated Sharpe for every rule evaluated, using the logged number of variants tried", "any", "n/a", PX,
    "a rule is reported only if its deflated Sharpe probability exceeds 0.95", "all")
add("DISC-TSTAT", "Higher t-statistic hurdle for new factors", "discipline",
    "After hundreds of tested factors, a new factor needs t above about 3 to be credible.",
    "10.1093/rfs/hhv059", "Harvey", 2016, "and the Cross-Section of Expected Returns",
    "count every signal tested in this repository and apply the multiple-testing adjusted threshold", "any", "n/a", PX,
    "no rule is promoted below the adjusted t-statistic", "all")
add("DISC-BACKTEST", "Backtesting protocol", "discipline",
    "Backtest overfitting is the default outcome of searching; protocol must fix the rules and the evaluation in advance.",
    "10.3905/jpm.2015.42.1.013", "Harvey", 2015, "Backtesting",
    "pre-register the signal, horizon and cost band in this file before running the test", "any", "n/a", PX,
    "reject any result whose specification was changed after seeing it", "all")
add("DISC-DECAY", "Anomalies decay after publication", "discipline",
    "Predictability falls by about a third after a paper is published, and more for liquid stocks.",
    "10.1111/jofi.12365", "McLean", 2016, "Does Academic Research Destroy Stock Return Predictability",
    "split each tested effect at its publication year; compare in-sample and post-publication performance", "any", "-", PX,
    "post-publication mean return as a share of the in-sample mean", "all")
add("DISC-SNOOP", "Data snooping in technical rules", "discipline",
    "After accounting for the universe of rules searched, apparent technical-trading profits mostly disappear.",
    "10.1111/0022-1082.00163", "Sullivan", 1999, "Data-Snooping, Technical Trading Rule Performance",
    "bootstrap reality check over the full family of rules tested", "any", "n/a", PX,
    "report the family-wise p-value, not the best rule's raw p-value", "all")
add("DISC-CHARLATAN", "Pseudo-mathematics in backtests", "discipline",
    "The minimum backtest length needed to avoid overfitting grows with the number of configurations tried.",
    "10.1090/noti1105", "Bailey", 2014, "Pseudo-Mathematics and Financial Charlatanism",
    "minimum backtest length given the number of variants tried and the target Sharpe", "any", "n/a", PX,
    "reject results from histories shorter than the computed minimum", "all")
add("DISC-COSTS", "Anomaly returns net of trading costs", "discipline",
    "Many anomalies do not survive realistic trading costs once the portfolio is rebalanced as the signal demands.",
    "10.1093/rfs/hhv063", "Novy-Marx", 2016, "Taxonomy of Anomalies and Their Trading Costs",
    "net every rule at the low, central and high cost assumptions in tools/costs.py", "any", "-", PX,
    "a rule must stay positive at the central cost", "all")
add("DISC-ADAPTIVE", "Adaptive markets", "discipline",
    "Strategy profitability varies with market conditions and competition rather than being constant.",
    "10.3905/jpm.2004.442611", "Lo", 2004, "Adaptive Markets Hypothesis",
    "rolling-window performance of each rule across regimes defined by VIXCLS and T10Y3M", "any", "mixed",
    ["price", "macro"], "performance dispersion across regimes; a rule needs a stated regime", "all")

# ---- fundamentals-based, recorded so the gap is visible rather than quietly absent ----
add("FUND-VALUE", "Value: earnings-to-price", "fundamentals",
    "Stocks with low price-to-earnings ratios earned higher risk-adjusted returns.",
    "10.1111/j.1540-6261.1977.tb01979.x", "Basu", 1977, "Investment performance of common stocks",
    "earnings divided by price", "12m", "+", ["price", "fundamentals"], XS)
add("FUND-FF3", "Size and value factors", "fundamentals",
    "Three factors, market, size and book-to-market, capture most of the cross-section of average returns.",
    "10.1016/0304-405X(93)90023-5", "Fama", 1993, "Common risk factors in the returns on stocks and bonds",
    "book-to-market and market cap", "12m", "+", ["price", "fundamentals"], XS)
add("FUND-PROFIT", "Gross profitability premium", "fundamentals",
    "Gross profit scaled by assets predicts returns about as strongly as book-to-market.",
    "10.1016/j.jfineco.2013.01.003", "Novy-Marx", 2013, "other side of value",
    "(revenue - cost of goods sold) / total assets", "12m", "+", ["price", "fundamentals"], XS)
add("FUND-QUALITY", "Quality minus junk", "fundamentals",
    "High-quality stocks, profitable, growing, safe and well-paid-out, outperform junk after adjusting for risk.",
    "10.1007/s11142-018-9470-2", "Asness", 2019, "Quality minus junk",
    "composite of profitability, growth, safety and payout", "12m", "+", ["price", "fundamentals"], XS)
add("FUND-FSCORE", "Financial-statement scoring of value stocks", "fundamentals",
    "A nine-signal score separates winners from losers among high book-to-market stocks.",
    "10.2307/2672906", "Piotroski", 2000, "Value Investing: The Use of Historical Financial Statement",
    "nine-point F-score", "12m", "+", ["price", "fundamentals"], XS)
add("FUND-ISSUE", "Net share issuance", "fundamentals",
    "Firms that issue shares underperform; firms that repurchase outperform.",
    "10.1111/j.1540-6261.2008.01335.x", "Pontiff", 2008, "Share Issuance and Cross-sectional Returns",
    "change in shares outstanding over 12 months", "12m", "-", ["price", "fundamentals"], XS)
add("FUND-ASSETGROWTH", "Asset growth", "fundamentals",
    "Firms with high asset growth earn low subsequent returns.",
    "10.1111/j.1540-6261.2008.01370.x", "Cooper", 2008, "Asset growth and the cross-section of stock returns",
    "change in total assets over 12 months", "12m", "-", ["price", "fundamentals"], XS)
add("FUND-CONTRARIAN", "Contrarian investment and extrapolation", "fundamentals",
    "Value strategies beat glamour strategies because investors over-extrapolate past growth.",
    "10.1111/j.1540-6261.1994.tb04772.x", "Lakonishok", 1994, "Contrarian investment, extrapolation, and risk",
    "growth rate of sales and cash flow rank crossed with value rank", "12m", "+", ["price", "fundamentals"], XS)

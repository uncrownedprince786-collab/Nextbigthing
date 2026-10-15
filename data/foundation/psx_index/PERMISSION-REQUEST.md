# KSE-100 historical data — permission requests to send

Two requests, either of which closes part of the remaining gap. Neither is a technical task: the
data has been located and, where reachable, validated. What is missing is permission.

The gap, measured exactly from this project's own sweep of the exchange's daily archive:
**155 published PSX trading sessions, 2021-02-24 through 2021-10-14**, contiguous, with the
boundary on each side confirmed against a published session.

---

## Request 1 — Open Data Pakistan (cheapest, largest win)

**To:** the publisher of the resource at
`https://opendata.com.pk/dataset/572570b3-2d4f-46f4-83e0-4d860bf71bff/resource/12071eb8-c3ee-4686-a3d3-f7b49fab502d`

**What is being asked:** that a licence be stated on that resource, or written permission given for
internal research and model-development use of the data already published there.

**Why it matters here:** the file is already downloaded and validated — 3,206 observations,
2008-02-22 to 2021-02-23, with real Open, High, Low and Close. Its resource page currently reads
**"License: No License Provided"**, so it is held in private quarantine and used for nothing. A
stated licence would clear **2018-01-01 to 2021-02-23** immediately, leaving only the 155-session
stub above.

**Suggested wording**

> We are building a private research dataset of Pakistani market history. We have downloaded the
> KSE-100 resource published on Open Data Pakistan (resource id
> 12071eb8-c3ee-4686-a3d3-f7b49fab502d). The resource page states "License: No License Provided",
> so we have not used the data.
>
> Could you either state a licence on the resource, or confirm in writing whether we may use it for
> internal research and model development? We are not asking to redistribute it or republish it on
> any public surface. If reuse is not permitted, please say so and we will delete our copy.

---

## Request 2 — Karandaaz Pakistan (covers the 155-session stub)

**To:** Karandaaz Pakistan (KRN) and CS Solutions (Pvt) Limited (CS), the parties named in the
portal's Terms of Use.

**Dataset:** `https://portal.karandaaz.com.pk/dataset/kse100/1900` — "KSE - 100 index".

**Why written permission is required rather than assumed:** the portal's own Terms of Use state
that KRN & CS "retain all proprietary rights to that content" and grant no licence to use it
"without the **express written permission** of KRN & CS". The download control also sits behind an
account, and no account was created for this work.

**Suggested wording**

> We are assembling a private research dataset of Pakistani market history for internal model
> development. We already hold the KSE-100 daily series from 2021-10-15 onward from the Pakistan
> Stock Exchange's own published endpoint.
>
> We would like permission to download and store the KSE-100 daily index history for
> **2021-02-24 to 2021-10-14** (155 trading sessions) from your portal, for internal research and
> model development only. We are not asking to redistribute the data, publish it on any public
> surface, or make it available through any product.
>
> Please confirm whether this use is permitted, and on what terms. If a licence or data agreement
> is required, we would be glad to complete one.

---

## What has deliberately not been done

No account was registered and no sign-in was attempted; no access control was circumvented; no
restricted data was committed to this repository or written to any production table. The Open Data
Pakistan file stays in private cache and in the PC backup only.

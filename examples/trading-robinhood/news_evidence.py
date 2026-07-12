"""Evidence source: keyless news/macro feeds, per-feed tolerant.

Always exits 0 with valid JSON — a dead feed becomes a note, not a failure,
so one outage never blocks the briefing.
"""

import json
import re
import urllib.request

ITEMS = []


def fetch(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "caucus-evidence/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def add(source, ref, content):
    ITEMS.append({"source": source, "ref": str(ref), "content": str(content)[:400]})


try:
    xml = fetch("https://www.federalreserve.gov/feeds/press_all.xml")
    titles = re.findall(r"<title>(.*?)</title>", xml)[1:6]
    dates = re.findall(r"<pubDate>(.*?)</pubDate>", xml)[:5]
    for title, date in zip(titles, dates):
        add("fed-press", date, title)
except Exception as err:
    add("fed-press", "unavailable", "Fed press feed fetch failed: " + str(err))

try:
    hn = json.loads(
        fetch(
            "https://hn.algolia.com/api/v1/search_by_date?query=semiconductor%20OR%20NVDA%20OR%20AI%20chips&tags=story&hitsPerPage=5"
        )
    )
    for hit in hn.get("hits", [])[:5]:
        title = str(hit.get("title"))
        points = str(hit.get("points"))
        add("hackernews", hit.get("created_at", ""), title + " (" + points + " pts)")
except Exception as err:
    add("hackernews", "unavailable", "HN fetch failed: " + str(err))

try:
    markets = json.loads(
        fetch(
            "https://gamma-api.polymarket.com/markets?closed=false&active=true&order=volumeNum&ascending=false&limit=30"
        )
    )
    kept = 0
    for market in markets:
        question = str(market.get("question", ""))
        if kept < 5 and re.search(r"fed|fomc|cpi|inflation|rate", question, re.I):
            prices = str(market.get("outcomePrices"))
            add("polymarket", question[:60], "active market, implied prices " + prices)
            kept += 1
    if kept == 0:
        add("polymarket", "no-matches", "no active Fed/CPI/inflation markets in top 30 by volume")
except Exception as err:
    add("polymarket", "unavailable", "Polymarket fetch failed: " + str(err))

print(json.dumps(ITEMS))

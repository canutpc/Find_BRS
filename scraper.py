import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# Requêtes ciblées via flux RSS Google News (sans clé API requise)
QUERIES = [
    '"BRS" ("Croix-Rousse" OR "Lyon 4" OR "Lyon 1" OR "69004" OR "69001") -Caluire -Saint-Clair',
    '"Bail Réel Solidaire" ("Croix-Rousse" OR "Lyon 4" OR "Lyon 1") -Caluire -Saint-Clair',
    '("programme neuf" OR "construction") ("Croix-Rousse" OR "69004" OR "69001") ("T4" OR "BRS") -Caluire -Saint-Clair',
]

INCLUDE_ZONES = ["croix-rousse", "croix rousse", "69004", "69001", "lyon 4", "lyon 1", "pentes", "plateau"]
EXCLUDE_WORDS = ["caluire", "saint-clair", "saint clair", "montessuy", "cuire"]

def matches_rules(text: str) -> bool:
    t = text.lower()
    if any(bad in t for bad in EXCLUDE_WORDS):
        return False
    return any(zone in t for zone in INCLUDE_ZONES)

def fetch_rss(query: str):
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=fr&gl=FR&ceid=FR:fr"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    items = []
    with urllib.request.urlopen(req, timeout=15) as resp:
        xml_data = resp.read()
    root = ET.fromstring(xml_data)
    for item in root.findall("./channel/item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        pub_date = item.findtext("pubDate") or ""
        source = item.findtext("source") or "Web"
        if matches_rules(title):
            items.append({
                "title": title,
                "url": link,
                "date": pub_date,
                "source": source,
                "summary": "Correspondance détectée sur le périmètre Croix-Rousse (69004 / 69001)."
            })
    return items

def main():
    seen_urls = set()
    results = []
    for q in QUERIES:
        try:
            for item in fetch_rss(q):
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    results.append(item)
        except Exception as e:
            print(f"Erreur sur requête {q}: {e}")

    payload = {
        "updated_at": datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
        "items": results[:30]
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()

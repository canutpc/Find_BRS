import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# 1. SOURCES PRESSE / WEB (Google News RSS)
QUERIES = [
    '"BRS" ("Croix-Rousse" OR "Lyon 4" OR "Lyon 1" OR "69004" OR "69001") -Caluire -Saint-Clair',
    '"Bail Réel Solidaire" ("Croix-Rousse" OR "Lyon 4" OR "Lyon 1") -Caluire -Saint-Clair',
    '("programme neuf" OR "construction") ("Croix-Rousse" OR "69004" OR "69001") ("T4" OR "BRS") -Caluire -Saint-Clair',
]

# 2. SITES DIRECTS DES ORGANISMES BRS & PROMOTEURS LOCAUX
PROMOTER_PAGES = [
    {
        "name": "Foncière Solidaire du Grand Lyon",
        "url": "https://www.fonciere-solidaire-grand-lyon.fr/nos-operations/",
        "base": "https://www.fonciere-solidaire-grand-lyon.fr"
    },
    {
        "name": "GrandLyon Habitat (Accession)",
        "url": "https://www.grandlyonhabitat.fr/acheter-un-logement/",
        "base": "https://www.grandlyonhabitat.fr"
    },
    {
        "name": "Rhône Saône Habitat (BRS / Neuf)",
        "url": "https://www.rhonesaonehabitat.fr/acheter/",
        "base": "https://www.rhonesaonehabitat.fr"
    },
    {
        "name": "Alliade Habitat (Accession)",
        "url": "https://www.alliade.com/acheter/",
        "base": "https://www.alliade.com"
    },
    {
        "name": "Est Métropole Habitat (Accession)",
        "url": "https://www.est-metropole-habitat.fr/acheter/",
        "base": "https://www.est-metropole-habitat.fr"
    },
    {
        "name": "Nexity (Neuf Lyon 4e)",
        "url": "https://www.nexity.fr/neuf/0070__69004",
        "base": "https://www.nexity.fr"
    },
    {
        "name": "Nexity (Neuf Lyon 1er)",
        "url": "https://www.nexity.fr/neuf/0070__69001",
        "base": "https://www.nexity.fr"
    },
    {
        "name": "Bouygues Immobilier (Lyon 4e)",
        "url": "https://www.bouygues-immobilier.com/programme-neuf-lyon-4",
        "base": "https://www.bouygues-immobilier.com"
    },
]

INCLUDE_ZONES = [
    "croix-rousse", "croix rousse", "69004", "69001",
    "lyon 4", "lyon 1", "lyon-4", "lyon-1", "pentes", "plateau"
]
EXCLUDE_WORDS = ["caluire", "saint-clair", "saint clair", "montessuy", "cuire"]


def matches_rules(text: str) -> bool:
    t = text.lower()
    if any(bad in t for bad in EXCLUDE_WORDS):
        return False
    return any(zone in t for zone in INCLUDE_ZONES)


def detect_tags(text: str, source_type: str = "") -> list[str]:
    t = text.lower()
    tags = []
    if source_type == "Promoteur":
        tags.append("Site Promoteur")
    if "brs" in t or "bail réel solidaire" in t or "bail reel solidaire" in t or "foncière solidaire" in t:
        tags.append("BRS")
    if "neuf" in t or "construction" in t or "programme" in t or source_type == "Promoteur":
        tags.append("Neuf")
    if "69004" in t or "lyon 4" in t or "lyon-4" in t or "plateau" in t:
        tags.append("69004 (Plateau)")
    if "69001" in t or "lyon 1" in t or "lyon-1" in t or "pentes" in t:
        tags.append("69001 (Pentes)")
    if "t4" in t or "4 pièces" in t or "4 pieces" in t:
        tags.append("T4")
    return list(dict.fromkeys(tags)) or ["Croix-Rousse"]


def parse_pub_date(pub_date_str: str):
    try:
        dt = parsedate_to_datetime(pub_date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp()), dt.strftime("%d/%m/%Y à %H:%M")
    except Exception:
        now = datetime.now(timezone.utc)
        return int(now.timestamp()), now.strftime("%d/%m/%Y à %H:%M")


def load_existing_items() -> dict:
    """Conserve la date exacte de première apparition des liens déjà détectés."""
    if not os.path.exists("data.json"):
        return {}
    try:
        with open("data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return {item["url"]: item for item in data.get("items", []) if "url" in item}
    except Exception:
        return {}


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
        source = item.findtext("source") or "Web / Presse"
        if matches_rules(title):
            ts, formatted_date = parse_pub_date(pub_date)
            items.append({
                "title": title.strip(),
                "url": link.strip(),
                "timestamp": ts,
                "date": formatted_date,
                "source": source,
                "tags": detect_tags(title, "Presse"),
                "summary": "Article ou annonce détecté sur le périmètre Croix-Rousse (69004 / 69001)."
            })
    return items


def clean_html_text(raw_html: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", raw_html)
    unescaped = html.unescape(no_tags)
    return re.sub(r"\s+", " ", unescaped).strip()


def fetch_promoter_page(site: dict, existing_map: dict):
    req = urllib.request.Request(
        site["url"],
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
            "Accept-Language": "fr-FR,fr;q=0.9"
        }
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        page_html = resp.read().decode("utf-8", errors="ignore")

    items = []
    now = datetime.now(timezone.utc)
    now_ts = int(now.timestamp())
    now_str = now.strftime("%d/%m/%Y à %H:%M")

    # Extraction de tous les blocs <a href="...">...</a>
    links = re.findall(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', page_html, flags=re.IGNORECASE | re.DOTALL)

    for href, inner_html in links:
        text = clean_html_text(inner_html)
        combined = f"{text} {href}"

        # Ignore les liens vides, ancres ou menus génériques
        if len(text) < 6 or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue

        if matches_rules(combined):
            full_url = urllib.parse.urljoin(site["base"], href)
            # Si déjà vu lors d'un précédent passage, on garde sa date d'apparition d'origine
            if full_url in existing_map:
                ts = existing_map[full_url]["timestamp"]
                date_str = existing_map[full_url]["date"]
            else:
                ts = now_ts
                date_str = f"Détecté le {now_str}"

            display_title = text if len(text) <= 120 else text[:117] + "..."
            items.append({
                "title": f"[{site['name']}] {display_title}",
                "url": full_url,
                "timestamp": ts,
                "date": date_str,
                "source": site["name"],
                "tags": detect_tags(f"{site['name']} {combined}", "Promoteur"),
                "summary": f"Programme ou fiche repérée directement sur le site de {site['name']}."
            })

    return items


def main():
    existing_map = load_existing_items()
    seen_urls = set()
    results = []

    # 1. Scan direct des sites promoteurs et organismes BRS
    for site in PROMOTER_PAGES:
        try:
            for item in fetch_promoter_page(site, existing_map):
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    results.append(item)
        except Exception as e:
            print(f"[Promoteur] Erreur sur {site['name']}: {e}")

    # 2. Scan des flux RSS presse / web
    for q in QUERIES:
        try:
            for item in fetch_rss(q):
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    results.append(item)
        except Exception as e:
            print(f"[RSS] Erreur sur requête {q}: {e}")

    # Tri du plus récent au plus ancien
    results.sort(key=lambda x: x["timestamp"], reverse=True)

    payload = {
        "updated_at": datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC"),
        "monitored_promoters": [s["name"] for s in PROMOTER_PAGES],
        "items": results[:80]
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

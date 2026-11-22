import html
import json
import os
import re
import smtplib
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime

# 1. REQUÊTES WEB RÉCENTES UNIQUEMENT (when:60d limite aux 60 derniers jours)
QUERIES = [
    '"BRS" ("Croix-Rousse" OR "Lyon 4" OR "Lyon 1" OR "69004" OR "69001") -Caluire -Saint-Clair when:60d',
    '"Bail Réel Solidaire" ("Croix-Rousse" OR "Lyon 4" OR "Lyon 1") -Caluire -Saint-Clair when:60d',
    '("nouveau programme" OR "lancement commercial" OR "prochainement") ("Croix-Rousse" OR "69004" OR "69001") -Caluire -Saint-Clair when:60d',
]

# 2. SITES DIRECTS DES ORGANISMES BRS & PROMOTEURS LOCAUX
PROMOTER_PAGES = [
    {
        "name": "Foncière Solidaire du Grand Lyon",
        "url": "https://www.fonciere-solidaire-grand-lyon.fr/nos-operations/",
        "base": "https://www.fonciere-solidaire-grand-lyon.fr",
    },
    {
        "name": "GrandLyon Habitat (Accession)",
        "url": "https://www.grandlyonhabitat.fr/acheter-un-logement/",
        "base": "https://www.grandlyonhabitat.fr",
    },
    {
        "name": "Rhône Saône Habitat (BRS / Neuf)",
        "url": "https://www.rhonesaonehabitat.fr/acheter/",
        "base": "https://www.rhonesaonehabitat.fr",
    },
    {
        "name": "Alliade Habitat (Accession)",
        "url": "https://www.alliade.com/acheter/",
        "base": "https://www.alliade.com",
    },
    {
        "name": "Est Métropole Habitat (Accession)",
        "url": "https://www.est-metropole-habitat.fr/acheter/",
        "base": "https://www.est-metropole-habitat.fr",
    },
    {
        "name": "Nexity (Neuf Lyon 4e)",
        "url": "https://www.nexity.fr/neuf/0070__69004",
        "base": "https://www.nexity.fr",
    },
    {
        "name": "Nexity (Neuf Lyon 1er)",
        "url": "https://www.nexity.fr/neuf/0070__69001",
        "base": "https://www.nexity.fr",
    },
    {
        "name": "Bouygues Immobilier (Lyon 4e)",
        "url": "https://www.bouygues-immobilier.com/programme-neuf-lyon-4",
        "base": "https://www.bouygues-immobilier.com",
    },
]

# Périmètre strict : Plateau (69004) et Pentes (69001)
INCLUDE_ZONES = [
    "croix-rousse",
    "croix rousse",
    "69004",
    "69001",
    "lyon 4",
    "lyon 1",
    "lyon-4",
    "lyon-1",
    "pentes",
    "plateau",
]

# Secteurs et anciens programmes déjà connus/vendus à écarter
EXCLUDE_WORDS = [
    "caluire",
    "saint-clair",
    "saint clair",
    "montessuy",
    "cuire",
    "jardin des balmes",
    "maurice-scève",
    "maurice sceve",
    "maurice-sceve",
]

# Mentions sur une fiche programme indiquant qu'il n'y a plus rien à vendre
SOLD_OUT_MARKERS = [
    "tout vendu",
    "100% vendu",
    "100 % vendu",
    "tous vendus",
    "commercialisation terminée",
    "commercialisation terminee",
    "plus de lots disponibles",
    "programme épuisé",
    "programme epuise",
    "aucun lot disponible",
    "réservé à 100%",
    "reserve a 100%",
]

# Âge maximum des articles de presse en jours
MAX_NEWS_AGE_DAYS = 45


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
    if (
        "brs" in t
        or "bail réel solidaire" in t
        or "bail reel solidaire" in t
        or "foncière solidaire" in t
    ):
        tags.append("BRS")
    if (
        "neuf" in t
        or "construction" in t
        or "programme" in t
        or source_type == "Promoteur"
    ):
        tags.append("Neuf")
    if "69004" in t or "lyon 4" in t or "lyon-4" in t or "plateau" in t:
        tags.append("69004 (Plateau)")
    if "69001" in t or "lyon 1" in t or "lyon-1" in t or "pentes" in t:
        tags.append("69001 (Pentes)")
    if re.search(r"\bt4\b|4\s*pi[èe]ces", t):
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
            return {
                item["url"]: item
                for item in data.get("items", [])
                if "url" in item
            }
    except Exception:
        return {}


def fetch_url_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "fr-FR,fr;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def clean_html_text(raw_html: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", raw_html)
    unescaped = html.unescape(no_tags)
    return re.sub(r"\s+", " ", unescaped).strip()


def inspect_program_detail(url: str) -> dict:
    """Ouvre la page du programme chez le promoteur pour vérifier s'il est vendu ou si un T4 est cité."""
    try:
        detail_html = fetch_url_text(url)
        detail_text = clean_html_text(detail_html).lower()

        if any(bad in detail_text for bad in EXCLUDE_WORDS):
            return {"valid": False}
        if any(sold in detail_text for sold in SOLD_OUT_MARKERS):
            return {"valid": False}

        has_t4 = bool(re.search(r"\bt4\b|4\s*pi[èe]ces", detail_text))
        has_brs = ("brs" in detail_text) or (
            "bail réel solidaire" in detail_text
        )
        return {"valid": True, "has_t4": has_t4, "has_brs": has_brs}
    except Exception:
        return {"valid": True, "has_t4": False, "has_brs": False}


def fetch_rss(query: str):
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=fr&gl=FR&ceid=FR:fr"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    items = []
    now_ts = int(datetime.now(timezone.utc).timestamp())
    max_age_sec = MAX_NEWS_AGE_DAYS * 86400

    with urllib.request.urlopen(req, timeout=15) as resp:
        xml_data = resp.read()
    root = ET.fromstring(xml_data)

    for item in root.findall("./channel/item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        pub_date = item.findtext("pubDate") or ""
        source = item.findtext("source") or "Web / Presse"

        if not matches_rules(title):
            continue

        ts, formatted_date = parse_pub_date(pub_date)
        if (now_ts - ts) > max_age_sec:
            continue

        items.append({
            "title": title.strip(),
            "url": link.strip(),
            "timestamp": ts,
            "date": formatted_date,
            "source": source,
            "tags": detect_tags(title, "Presse"),
            "summary": (
                "Actualité récente sur le périmètre Croix-Rousse (69004 /"
                " 69001)."
            ),
        })
    return items


def fetch_promoter_page(site: dict, existing_map: dict):
    page_html = fetch_url_text(site["url"])
    items = []
    now = datetime.now(timezone.utc)
    now_ts = int(now.timestamp())
    now_str = now.strftime("%d/%m/%Y à %H:%M")

    links = re.findall(
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )

    for href, inner_html in links:
        text = clean_html_text(inner_html)
        combined = f"{text} {href}"

        if (
            len(text) < 6
            or href.startswith("#")
            or href.startswith("mailto:")
            or href.startswith("tel:")
        ):
            continue

        if matches_rules(combined):
            full_url = urllib.parse.urljoin(site["base"], href)
            detail = inspect_program_detail(full_url)
            if not detail.get("valid", True):
                continue

            if full_url in existing_map:
                ts = existing_map[full_url]["timestamp"]
                date_str = existing_map[full_url]["date"]
            else:
                ts = now_ts
                date_str = f"Détecté le {now_str}"

            tags = detect_tags(f"{site['name']} {combined}", "Promoteur")
            if detail.get("has_t4") and "T4" not in tags:
                tags.append("T4")
            if detail.get("has_brs") and "BRS" not in tags:
                tags.append("BRS")

            display_title = text if len(text) <= 120 else text[:117] + "..."
            items.append({
                "title": f"[{site['name']}] {display_title}",
                "url": full_url,
                "timestamp": ts,
                "date": date_str,
                "source": site["name"],
                "tags": tags,
                "summary": f"Page active repérée sur {site['name']}.",
            })

    return items


def send_email_report(results: list, new_items: list):
    sender = os.environ.get("EMAIL_SENDER", "").strip()
    password = os.environ.get("EMAIL_PASSWORD", "").strip()
    recipients_raw = os.environ.get("EMAIL_RECIPIENTS", "").strip()

    if not (sender and password and recipients_raw):
        print("Variables e-mail non configurées, envoi ignoré.")
        return

    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    today_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")

    if new_items:
        subject = (
            f"🚨 {len(new_items)} nouveau(x) logement(s) BRS/Neuf — Croix-Rousse"
            f" ({today_str})"
        )
    else:
        subject = (
            f"🏙️ Veille Immo Croix-Rousse ({today_str}) — Rien de nouveau"
            " aujourd'hui"
        )

    if new_items:
        new_html = (
            "<h3>🆕 Nouveautés détectées aujourd'hui :</h3><ul>"
            + "".join(
                f'<li><strong><a href="{i["url"]}">{i["title"]}</a></strong>'
                f'<br><small>{i["source"]} • {i["date"]}</small></li>'
                for i in new_items
            )
            + "</ul>"
        )
    else:
        new_html = (
            "<p>Aucune nouvelle sortie détectée aujourd'hui sur le Plateau"
            " (69004) ou les Pentes (69001).</p>"
        )

    all_html = ""
    if results:
        all_html = (
            "<hr><h4>📋 Récapitulatif des opérations actives suivies :</h4><ul>"
            + "".join(
                f'<li><a href="{i["url"]}">{i["title"]}</a>'
                f' <small>({i["date"]})</small></li>'
                for i in results[:15]
            )
            + "</ul>"
        )

    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #1e293b; line-height: 1.5;">
        <h2>🏙️ Veille BRS & Neuf — Lyon Croix-Rousse</h2>
        <p style="color: #64748b; font-size: 13px;">Périmètre strict : Plateau (69004) & Pentes (69001) • T4 ~300 000 € • Hors Caluire</p>
        {new_html}
        {all_html}
        <p style="margin-top: 20px;">
          <a href="https://canutpc.github.io/Find_BRS/" style="background:#2563eb;color:#fff;padding:10px 16px;text-decoration:none;border-radius:6px;font-weight:bold;">
            Ouvrir le tableau de bord complet
          </a>
        </p>
      </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login

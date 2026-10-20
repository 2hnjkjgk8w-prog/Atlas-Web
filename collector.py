
import os
import re
import json
import time
import hashlib
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import requests
import feedparser
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(ROOT, "data")
SOURCES_FILE = os.path.join(DATA_DIR, "sources.json")
ARTICLES_FILE = os.path.join(DATA_DIR, "articles.json")

USER_AGENT = "AtlasWebCollector/1.0 (respectful research bot)"
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

session = requests.Session()
session.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/rss+xml,application/atom+xml,application/xml;q=0.9,*/*;q=0.7"
})


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp_path = path + ".tmp"

    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    os.replace(temp_path, path)


def clean_text(value, limit=1000):
    text = BeautifulSoup(str(value or ""), "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def normalize_url(url):
    if not url:
        return ""

    url, _ = urldefrag(url.strip())
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return ""

    if not parsed.hostname:
        return ""

    if parsed.username or parsed.password:
        return ""

    return url


def get_host(url):
    hostname = urlparse(url).hostname or ""
    return hostname.lower().removeprefix("www.")


def make_id(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]


def fetch_url(url):
    try:
        response = session.get(
            url,
            timeout=15,
            allow_redirects=True
        )

        if response.status_code >= 400:
            print(f"[SKIP] HTTP {response.status_code}: {url}")
            return None

        if len(response.content) > 3_000_000:
            print(f"[SKIP] Fichier trop volumineux: {url}")
            return None

        return response

    except requests.RequestException as error:
        print(f"[ERREUR] {url}: {error}")
        return None


def robots_allows(url):
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    try:
        response = session.get(robots_url, timeout=8)

        if response.status_code == 404:
            return True

        if response.status_code >= 400:
            return False

        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())

        return parser.can_fetch(USER_AGENT, url)

    except requests.RequestException:
        # En cas de doute, ne pas explorer la page.
        return False


def parse_feed(url, source_name):
    response = fetch_url(url)

    if response is None:
        return []

    feed = feedparser.parse(response.content)
    items = []

    for entry in feed.entries[:200]:
        link = normalize_url(entry.get("link", ""))

        if not link:
            continue

        title = clean_text(
            entry.get("title", "Sans titre"),
            300
        )

        summary = clean_text(
            entry.get("summary", entry.get("description", "")),
            900
        )

        parsed_date = (
            entry.get("published_parsed")
            or entry.get("updated_parsed")
        )

        date = None

        if parsed_date:
            try:
                date = datetime(
                    *parsed_date[:6],
                    tzinfo=timezone.utc
                ).isoformat()
            except (TypeError, ValueError):
                pass

        items.append({
            "id": make_id(link),
            "title": title,
            "url": link,
            "summary": summary,
            "source": source_name,
            "kind": "rss",
            "date": date,
            "collected_at": NOW
        })

    return items


def parse_page(url, source_name, same_domain=True):
    if not robots_allows(url):
        print(f"[ROBOTS] Page ignorée: {url}")
        return None, []

    response = fetch_url(url)

    if response is None:
        return None, []

    content_type = response.headers.get(
        "content-type", ""
    ).lower()

    if "html" not in content_type:
        return None, []

    final_url = normalize_url(response.url)

    if not final_url:
        return None, []

    soup = BeautifulSoup(response.text, "html.parser")

    title_tag = soup.find("title")
    title = clean_text(
        title_tag.get_text() if title_tag else final_url,
        300
    )

    description_tag = soup.find(
        "meta",
        attrs={"name": re.compile("^description$", re.I)}
    )

    if description_tag:
        summary = clean_text(
            description_tag.get("content", ""),
            900
        )
    else:
        summary = clean_text(soup.get_text(" "), 900)

    article = {
        "id": make_id(final_url),
        "title": title or final_url,
        "url": final_url,
        "summary": summary,
        "source": source_name,
        "kind": "web",
        "date": None,
        "collected_at": NOW
    }

    links = []
    seen = set()
    start_host = get_host(final_url)

    for anchor in soup.find_all("a", href=True):
        target = normalize_url(
            urljoin(final_url, anchor["href"])
        )

        if not target or target in seen:
            continue

        if same_domain and get_host(target) != start_host:
            continue

        if get_host(target) == "":
            continue

        if target.lower().endswith((
            ".pdf", ".jpg", ".jpeg", ".png",
            ".gif", ".zip", ".mp3", ".mp4"
        )):
            continue

        seen.add(target)

        links.append({
            "name": clean_text(anchor.get_text(" "), 100)
                    or get_host(target),
            "url": target,
            "type": "web",
            "enabled": True
        })

        if len(links) >= 30:
            break

    return article, links


def main():
    config = read_json(
        SOURCES_FILE,
        {"sources": [], "settings": {}}
    )

    settings = config.get("settings", {})

    max_pages = max(
        1, min(int(settings.get("max_pages_per_source", 20)), 50)
    )

    max_discovered = max(
        0, min(int(settings.get("max_discovered_sources", 100)), 300)
    )

    max_items = max(
        100, min(int(settings.get("max_items", 1500)), 5000)
    )

    same_domain = bool(
        settings.get("crawl_same_domain_only", True)
    )

    initial_sources = [
        source for source in config.get("sources", [])
        if source.get("enabled", True)
        and normalize_url(source.get("url", ""))
    ]

    previous = read_json(
        ARTICLES_FILE,
        {"items": []}
    )

    items_by_id = {}

    for item in previous.get("items", []):
        if item.get("url"):
            items_by_id[item.get("id") or make_id(item["url"])] = item

    known_sources = {}

    for source in initial_sources:
        url = normalize_url(source["url"])
        source["url"] = url
        known_sources[url] = source

    queue = list(initial_sources)
    processed = set()
    seed_hosts = {get_host(s["url"]) for s in initial_sources}
    max_total_pages = max_pages * max(1, len(initial_sources))
    discovered_count = 0

    while queue and len(processed) < max_total_pages:
        source = queue.pop(0)
        url = normalize_url(source.get("url", ""))

        if not url or url in processed:
            continue

        processed.add(url)
        name = clean_text(
            source.get("name") or get_host(url), 150
        )
        source_type = source.get("type", "auto").lower()

        looks_like_feed = (
            source_type == "rss"
            or "feed" in url.lower()
            or "rss" in url.lower()
            or "atom" in url.lower()
        )

        if looks_like_feed:
            new_items = parse_feed(url, name)
            discovered_links = []
        else:
            article, discovered_links = parse_page(
                url, name, same_domain=same_domain
            )
            new_items = [article] if article else []

        for item in new_items:
            if item and item.get("url"):
                items_by_id[item["id"]] = item

        for discovered in discovered_links:
            target = normalize_url(discovered.get("url", ""))

            if not target or target in known_sources:
                continue

            if discovered_count >= max_discovered:
                break

            known_sources[target] = discovered
            discovered_count += 1

            # Ne suivre que les liens internes au domaine d'origine.
            # Cela évite de partir explorer arbitrairement tout le Web.
            if get_host(target) == get_host(url):
                queue.append(discovered)

        print(
            f"[OK] {url} | "
            f"{len(new_items)} élément(s)"
        )

        time.sleep(1)

    items = sorted(
        items_by_id.values(),
        key=lambda item: (
            item.get("date")
            or item.get("collected_at")
            or ""
        ),
        reverse=True
    )[:max_items]

    source_list = list(known_sources.values())

    write_json(
        SOURCES_FILE,
        {
            "description": config.get(
                "description",
                "Catalogue des sources d'Atlas Web"
            ),
            "settings": settings,
            "sources": source_list
        }
    )

    write_json(
        ARTICLES_FILE,
        {
            "updated_at": NOW,
            "discovered_sources": max(
                0, len(source_list) - len(initial_sources)
            ),
            "items": items
        }
    )

    print("===================================")
    print(f"Pages traitées : {len(processed)}")
    print(f"Sources connues : {len(source_list)}")
    print(f"Éléments conservés : {len(items)}")
    print(f"Dernière collecte : {NOW}")
    print("Collecte terminée.")


if __name__ == "__main__":
    main()

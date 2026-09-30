"""Generate short redirect URLs for HML texts published on CUNY Manifold."""

import argparse
import csv
import html
import json
import re
import unicodedata
from pathlib import Path
from string import Template

import requests

BASE_URL = "https://cuny.manifoldapp.org"
API_URL = f"{BASE_URL}/api/v1"
JOURNAL_SLUG = "hml"
SHORT_BASE_URL = "https://docs.humanitiesmethods.org"

SHORTENER_DIR = Path(__file__).parent.parent  # _shortener/
SITE_ROOT = SHORTENER_DIR.parent  # the docs repo, served at SHORT_BASE_URL
LINKS_CSV = SHORTENER_DIR / "links.csv"
TEMPLATE = SHORTENER_DIR / "templates" / "redirect.html"
COLUMNS = ["path", "kind", "manifold_id", "category", "title", "subtitle", "target"]

# Allowed links.csv paths: "1" for an issue, "1/some-code" for a text.
PATH_PATTERNS = {
    "issue": re.compile(r"[1-9][0-9]*"),
    "text": re.compile(r"[1-9][0-9]*/[a-z0-9]+(-[a-z0-9]+)*"),
}

# Small words that don't count toward the two content words in a short code.
STOPWORDS = set(
    "a an and as at by for from in into is it its of on or the to with".split()
)


def find_journal_id(journals_response):
    """Return the HML journal's id. The API ignores its slug filter, so
    the response lists every journal on the server."""
    for journal in journals_response["data"]:
        if journal["attributes"]["slug"] == JOURNAL_SLUG:
            return journal["id"]


def parse_issues(issues_response):
    """Return the issues numbered 1 and up. Issue 0 holds the journal's own
    pages, and -1 is a stray copy of issue 1."""
    issues = []
    for item in issues_response["data"]:
        attrs = item["attributes"]
        if attrs["number"].isdigit() and int(attrs["number"]) >= 1:
            issues.append(
                {
                    "number": int(attrs["number"]),
                    "project_id": attrs["projectId"],
                    "project_slug": attrs["projectSlug"],
                    "title": attrs["title"],
                }
            )
    return issues


def parse_texts(project_response):
    """Return an issue's published texts in table-of-contents order:
    by category (Peer Reviewed, CREATIVE, ...), then position within it."""
    included = project_response["included"]
    categories = {
        item["id"]: item["attributes"]
        for item in included
        if item["type"] == "categories"
    }
    texts = [
        item
        for item in included
        if item["type"] == "texts" and item["attributes"]["published"]
    ]

    def category_of(text):
        return categories[text["relationships"]["category"]["data"]["id"]]

    texts.sort(
        key=lambda text: (category_of(text)["position"], text["attributes"]["position"])
    )
    return [
        {
            "id": text["id"],
            "title": text["attributes"]["title"],
            "subtitle": text["attributes"]["subtitlePlaintext"],
            "category": category_of(text)["title"],
            "target": f"{BASE_URL}/read/{text['attributes']['slug']}",
        }
        for text in texts
    ]


def current_targets(project_response):
    """Map the issue's project id and each text id to its current title,
    subtitle and Manifold URL."""
    project = project_response["data"]
    current = {
        project["id"]: {
            "title": project["attributes"]["title"],
            "subtitle": "",
            "target": f"{BASE_URL}/projects/{project['attributes']['slug']}",
        }
    }
    for text in parse_texts(project_response):
        current[text["id"]] = {
            "title": text["title"],
            "subtitle": text["subtitle"],
            "target": text["target"],
        }
    return current


def propose_code(title):
    """Propose a short code from a title: the words of the main title (before
    any colon) up to and including the second content word. Book reviews
    ("Review of X") become "review-" plus the code for X."""
    if title.startswith("Review of "):
        return "review-" + propose_code(title.removeprefix("Review of "))
    # Drop straight and curly apostrophes so "It’s" becomes "its".
    main_title = title.split(":")[0].replace("'", "").replace("’", "")
    plain = unicodedata.normalize("NFKD", main_title).encode("ascii", "ignore")
    words = re.findall(r"[a-z0-9]+", plain.decode().lower())
    code_words = []
    content_words = 0
    for word in words:
        code_words.append(word)
        if word not in STOPWORDS:
            content_words += 1
        if content_words == 2:
            break
    return "-".join(code_words)


def new_rows(issue, texts, existing):
    """Return links.csv rows for an issue and its texts that aren't listed
    yet. Existing rows are matched by Manifold id, so codes that editors
    have changed are left alone."""
    listed_ids = {row["manifold_id"] for row in existing}
    used_paths = {row["path"] for row in existing}
    rows = []
    if issue["project_id"] not in listed_ids:
        rows.append(
            {
                "path": str(issue["number"]),
                "kind": "issue",
                "manifold_id": issue["project_id"],
                "category": "",
                "title": issue["title"],
                "subtitle": "",
                "target": f"{BASE_URL}/projects/{issue['project_slug']}",
            }
        )
    for text in texts:
        if text["id"] in listed_ids:
            continue
        path = unused_path(
            f"{issue['number']}/{propose_code(text['title'])}", used_paths
        )
        used_paths.add(path)
        rows.append(
            {
                "path": path,
                "kind": "text",
                "manifold_id": text["id"],
                "category": text["category"],
                "title": text["title"],
                "subtitle": text["subtitle"],
                "target": text["target"],
            }
        )
    return rows


def unused_path(path, used_paths):
    """Return path, or path-2, path-3, ... if it's already taken."""
    candidate = path
    number = 2
    while candidate in used_paths:
        candidate = f"{path}-{number}"
        number += 1
    return candidate


def refresh_rows(rows, current):
    """Update each row's title, subtitle and target from current_targets().
    Paths never change; rows missing from Manifold keep their last values."""
    return [row | current.get(row["manifold_id"], {}) for row in rows]


def render_page(row):
    """Return the redirect page for one links.csv row."""
    description = ""
    if row["subtitle"]:
        description = (
            f'<meta property="og:description" content="{html.escape(row["subtitle"])}">'
        )
    return Template(TEMPLATE.read_text(encoding="utf-8")).substitute(
        title=html.escape(row["title"]),
        description=description,
        target=html.escape(row["target"]),
        target_js=json.dumps(row["target"]),
    )


def write_pages(rows, site_root):
    """Write <site_root>/<path>/index.html for every row. Nothing else in
    the site is touched, and nothing is deleted."""
    for row in rows:
        page = site_root / row["path"] / "index.html"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(render_page(row), encoding="utf-8")


def read_links(csv_path):
    """Read links.csv into a list of row dicts."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_links(csv_path, rows):
    """Write rows to links.csv with the columns in a fixed order."""
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def validate_links(rows):
    """Return a list of problems with links.csv rows; empty means all good."""
    problems = []
    seen = set()
    for row in rows:
        path = row["path"]
        if row["kind"] not in PATH_PATTERNS:
            problems.append(f"{path}: unknown kind {row['kind']!r}")
        elif not PATH_PATTERNS[row["kind"]].fullmatch(path):
            problems.append(f"{path}: not a valid {row['kind']} path")
        if path in seen:
            problems.append(f"{path}: path is used more than once")
        seen.add(path)
    return problems


def fetch_json(url):
    """Get a Manifold API URL; an HTTP error stops the run."""
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def fetch_issues():
    """Fetch HML's issues numbered 1 and up."""
    journals = fetch_json(f"{API_URL}/journals?filter[slug]={JOURNAL_SLUG}")
    journal_id = find_journal_id(journals)
    return parse_issues(
        fetch_json(
            f"{API_URL}/journals/{journal_id}/relationships/journal_issues"
            "?page[size]=100"
        )
    )


def fetch_project(project_id):
    """Fetch an issue's project with its texts and their categories."""
    return fetch_json(f"{API_URL}/projects/{project_id}?include=texts,textCategories")


def add(number, csv_path=LINKS_CSV):
    """Append rows for one issue to links.csv and print the new short URLs."""
    issues_by_number = {item["number"]: item for item in fetch_issues()}
    issue = issues_by_number[number]
    rows = read_links(csv_path) if csv_path.exists() else []
    added = new_rows(issue, parse_texts(fetch_project(issue["project_id"])), rows)
    write_links(csv_path, rows + added)
    print(f"Added {len(added)} links to {csv_path.name}")
    for row in added:
        print(f"  {SHORT_BASE_URL}/{row['path']}  {row['title']}")


def build(csv_path=LINKS_CSV, site_root=SITE_ROOT):
    """Refresh every row's target from Manifold, then write the redirect pages."""
    rows = read_links(csv_path)
    current = {}
    for row in rows:
        if row["kind"] == "issue":
            current |= current_targets(fetch_project(row["manifold_id"]))
    rows = refresh_rows(rows, current)
    write_links(csv_path, rows)
    write_pages(rows, site_root)
    print(f"Wrote {len(rows)} redirect pages")


def issue_number(text):
    """Check the issue number given to `add`: only issues 1 and up."""
    if not text.isdigit() or int(text) < 1:
        raise argparse.ArgumentTypeError(f"issue must be 1 or higher, not {text!r}")
    return int(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    add_command = commands.add_parser("add", help="add a new issue's links")
    add_command.add_argument("issue", type=issue_number, help="issue number, 1 or up")
    commands.add_parser("build", help="refresh targets and write redirect pages")
    args = parser.parse_args()
    if args.command == "add":
        add(args.issue)
    else:
        build()


if __name__ == "__main__":
    main()

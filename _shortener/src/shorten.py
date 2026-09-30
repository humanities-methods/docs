"""Generate short redirect URLs for HML texts published on CUNY Manifold."""

import re
import unicodedata

BASE_URL = "https://cuny.manifoldapp.org"
JOURNAL_SLUG = "hml"

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

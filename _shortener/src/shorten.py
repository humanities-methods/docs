"""Generate short redirect URLs for HML texts published on CUNY Manifold."""

BASE_URL = "https://cuny.manifoldapp.org"
JOURNAL_SLUG = "hml"


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

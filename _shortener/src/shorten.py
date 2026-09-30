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

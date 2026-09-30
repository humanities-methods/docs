"""Generate short redirect URLs for HML texts published on CUNY Manifold."""

BASE_URL = "https://cuny.manifoldapp.org"
JOURNAL_SLUG = "hml"


def find_journal_id(journals_response):
    """Return the HML journal's id. The API ignores its slug filter, so
    the response lists every journal on the server."""
    for journal in journals_response["data"]:
        if journal["attributes"]["slug"] == JOURNAL_SLUG:
            return journal["id"]

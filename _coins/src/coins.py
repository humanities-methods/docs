"""Generate COinS spans for HML texts, so Zotero saves them as journal articles.

Reads _shortener/links.csv (the same list of texts the short links come
from) and prints one <span class="Z3988"> per text in an issue, ready to paste
into the article's HTML before it's ingested into Manifold. Nothing on the
site is changed.

    uv run python src/coins.py 1 --date 2026

Or write a file of spans for every issue to _coins/spans/<issue>.html, taking
each issue's date from _coins/issue_dates.csv (this is what the GitHub
Actions workflow runs):

    uv run python src/coins.py --write

Authors come from each text's byline (the subtitle column). To spell out
authors the byline can't express, such as a compound surname, add a row to
_coins/coins_authors.csv: the text's path, then its authors as "Last, First",
separated by semicolons.
"""

import argparse
import csv
import html
import re
import sys
from pathlib import Path
from urllib.parse import quote

COINS_DIR = Path(__file__).parent.parent  # _coins/
LINKS_CSV = COINS_DIR.parent / "_shortener" / "links.csv"
AUTHORS_CSV = COINS_DIR / "coins_authors.csv"
ISSUE_DATES_CSV = COINS_DIR / "issue_dates.csv"
SPANS_DIR = COINS_DIR / "spans"
NEEDED_COLUMNS = {"path", "kind", "title", "subtitle", "target"}

JOURNAL_TITLE = "Humanities Methods in Librarianship"
# Fill in once HML has an ISSN, e.g. "1234-5678"; left out of the spans while empty.
ISSN = ""
LANGUAGE = "en"

# Splits "A, B, and C", "A and B" or "A & B" into separate names.
BYLINE_SEPARATORS = re.compile(r"\s*,\s*and\s+|\s+and\s+|\s*&\s*|\s*,\s*")
DATE = re.compile(r"\d{4}(-\d{2}(-\d{2})?)?")


def read_links(csv_path):
    """Read links.csv into a list of row dicts, stopping with a readable
    message if the file is missing or doesn't have the columns used here."""
    if not csv_path.exists():
        sys.exit(f"Can't find {csv_path}; _coins expects to sit next to _shortener.")
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = NEEDED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            sys.exit(f"{csv_path.name} is missing columns: {', '.join(sorted(missing))}")
        rows = list(reader)
    # csv.DictReader files extra values under the key None and fills missing
    # values with None, both signs of an unquoted comma or a short row.
    bad = [row.get("path") or "?" for row in rows if None in row or None in row.values()]
    if bad:
        sys.exit(
            f"{csv_path.name} has rows with the wrong number of columns: {', '.join(bad)}"
        )
    return rows


def byline_authors(byline):
    """Turn a byline like "Lisa M. Longenecker" into ["Longenecker, Lisa M."].
    The last word is taken as the surname, so a compound surname needs an
    entry in coins_authors.csv."""
    names = [name for name in BYLINE_SEPARATORS.split(byline.strip()) if name]
    authors = []
    for name in names:
        first, _, last = name.rpartition(" ")
        authors.append(f"{last}, {first}" if first else last)
    return authors


def read_author_overrides(csv_path):
    """Map a text's path to its authors from coins_authors.csv, if it exists."""
    if not csv_path.exists():
        return {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        return {
            row["path"]: [a.strip() for a in row["authors"].split(";") if a.strip()]
            for row in csv.DictReader(f)
        }


def context_object(row, issue, date, authors, issn=ISSN):
    """Return the OpenURL ContextObject for one text, encoded for a COinS
    title attribute (before HTML escaping)."""
    pairs = [
        ("ctx_ver", "Z39.88-2004"),
        ("rft_val_fmt", "info:ofi/fmt:kev:mtx:journal"),
        ("rft.genre", "article"),
        ("rft.atitle", row["title"]),
        ("rft.jtitle", JOURNAL_TITLE),
        ("rft.issue", str(issue)),
    ]
    if date:
        pairs.append(("rft.date", date))
    pairs += [("rft.au", author) for author in authors]
    if issn:
        pairs.append(("rft.issn", issn))
    pairs += [("rft_id", row["target"]), ("rft.language", LANGUAGE)]
    return "&".join(f"{key}={quote(value, safe='')}" for key, value in pairs)


def coins_span(row, issue, date, authors, issn=ISSN, filler=""):
    """Return the <span class="Z3988"> for one text."""
    title = html.escape(context_object(row, issue, date, authors, issn), quote=True)
    return f'<span class="Z3988" title="{title}">{filler}</span>'


def issue_texts(rows, issue):
    """Return the links.csv rows for the texts in one issue."""
    return [
        row
        for row in rows
        if row["kind"] == "text" and row["path"].split("/")[0] == str(issue)
    ]


def generate(issue, date, csv_path=LINKS_CSV, authors_csv=AUTHORS_CSV, filler=""):
    """Return (output, warnings): a span per text with a comment naming it,
    and notes about texts whose spans have no authors."""
    rows = read_links(csv_path)
    overrides = read_author_overrides(authors_csv)
    texts = issue_texts(rows, issue)
    if not texts:
        sys.exit(f"links.csv has no texts for issue {issue}.")
    blocks, warnings = [], []
    for row in texts:
        authors = overrides.get(row["path"]) or byline_authors(row["subtitle"])
        if not authors:
            warnings.append(
                f"{row['path']}: no byline, so the span has no authors."
                " Zotero may look the text up elsewhere; add its authors"
                " to coins_authors.csv."
            )
        if "+" in row["title"] or any("+" in author for author in authors):
            warnings.append(
                f"{row['path']}: Zotero reads a plus sign as a space, even"
                " when encoded, so it will show one there instead."
            )
        span = coins_span(row, issue, date, authors, filler=filler)
        label = row["title"].replace("--", "–")
        blocks.append(f"<!-- {row['path']}: {label} -->\n{span}")
    return "\n\n".join(blocks) + "\n", warnings


def read_issue_dates(csv_path):
    """Map each issue number to its publication date from issue_dates.csv,
    stopping with a readable message on a date in the wrong format."""
    if not csv_path.exists():
        return {}
    dates = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            issue, date = row["issue"].strip(), row["date"].strip()
            if not DATE.fullmatch(date):
                sys.exit(f"{csv_path.name}: issue {issue} has date {date!r};"
                         " use YYYY or YYYY-MM-DD")
            dates[issue] = date
    return dates


def issues_in(rows):
    """Return the issue numbers that have texts in links.csv, in order."""
    numbers = {int(row["path"].split("/")[0]) for row in rows if row["kind"] == "text"}
    return sorted(numbers)


def write_all(
    csv_path=LINKS_CSV,
    authors_csv=AUTHORS_CSV,
    dates_csv=ISSUE_DATES_CSV,
    spans_dir=SPANS_DIR,
    filler="",
):
    """Write spans/<issue>.html for every issue in links.csv. Return the
    warnings, including one for each issue without a date."""
    dates = read_issue_dates(dates_csv)
    spans_dir.mkdir(parents=True, exist_ok=True)
    warnings = []
    for issue in issues_in(read_links(csv_path)):
        date = dates.get(str(issue))
        if not date:
            warnings.append(
                f"issue {issue}: no date in {dates_csv.name}, so its spans have none."
            )
        output, issue_warnings = generate(issue, date, csv_path, authors_csv, filler)
        (spans_dir / f"{issue}.html").write_text(output, encoding="utf-8")
        warnings += issue_warnings
    return warnings


def issue_number(text):
    """Check the issue number: only issues 1 and up."""
    if not text.isdigit() or int(text) < 1:
        raise argparse.ArgumentTypeError(f"issue must be 1 or higher, not {text!r}")
    return int(text)


def publication_date(text):
    """Check --date: YYYY, YYYY-MM or YYYY-MM-DD."""
    if not DATE.fullmatch(text):
        raise argparse.ArgumentTypeError(f"use YYYY or YYYY-MM-DD, not {text!r}")
    return text


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "issue", type=issue_number, nargs="?", help="issue number, 1 or up"
    )
    parser.add_argument(
        "--date",
        type=publication_date,
        help="publication date: YYYY (enough for a journal article) or YYYY-MM-DD",
    )
    parser.add_argument("--out", type=Path, help="also write the spans to this file")
    parser.add_argument(
        "--write",
        action="store_true",
        help="write spans/<issue>.html for every issue, dated from issue_dates.csv",
    )
    parser.add_argument(
        "--zwsp",
        action="store_true",
        help="put a zero-width space inside each span, in case Manifold drops empty ones",
    )
    args = parser.parse_args()
    filler = "&#8203;" if args.zwsp else ""
    if args.write:
        if args.issue or args.date or args.out:
            parser.error("--write covers every issue; leave out the issue, --date and --out")
        warnings = write_all(filler=filler)
        print(f"Wrote spans for {len(issues_in(read_links(LINKS_CSV)))} issue(s) to {SPANS_DIR}")
    elif args.issue:
        output, warnings = generate(args.issue, args.date, filler=filler)
        print(output, end="")
        if args.out:
            args.out.write_text(output, encoding="utf-8")
    else:
        parser.error("give an issue number, or --write for every issue")
    for warning in warnings:
        print(f"Note: {warning}", file=sys.stderr)


if __name__ == "__main__":
    main()

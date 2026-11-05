"""Tests for the COinS span generator."""

import html
import re
from urllib.parse import unquote

import pytest

import coins

ROW = {
    "path": "1/care-and-compliance",
    "kind": "text",
    "manifold_id": "f2fc31dd-9f74-4e13-af18-0e94b12d6bc3",
    "category": "Peer Reviewed",
    "title": "Care and Compliance: Problematising Access in Open Publishing,"
    " Libraries, and Disability Culture",
    "subtitle": "Scout Bell",
    "target": "https://cuny.manifoldapp.org/read/care-and-compliance-problematising"
    "-access-in-open-publishing-libraries-and-disability-culture"
    "-d3f5fb34-afad-4f5d-b183-054021aef621",
}


def pairs(span):
    """Decode a span's title attribute back into (key, value) pairs."""
    title = html.unescape(re.search(r'title="([^"]*)"', span).group(1))
    return [tuple(unquote(p) for p in pair.split("=", 1)) for pair in title.split("&")]


# Bylines


def test_byline_with_one_author():
    assert coins.byline_authors("Lisa M. Longenecker") == ["Longenecker, Lisa M."]


def test_byline_keeps_a_hyphenated_surname():
    assert coins.byline_authors("J. Morgan Rowe-Morris") == ["Rowe-Morris, J. Morgan"]


def test_byline_with_two_authors():
    assert coins.byline_authors("Ana Ruiz and Ben Okafor") == ["Ruiz, Ana", "Okafor, Ben"]


def test_byline_with_three_authors_and_a_serial_comma():
    assert coins.byline_authors("Ana Ruiz, Ben Okafor, and Cy Tran") == [
        "Ruiz, Ana",
        "Okafor, Ben",
        "Tran, Cy",
    ]


def test_byline_with_an_ampersand():
    assert coins.byline_authors("Ana Ruiz & Ben Okafor") == ["Ruiz, Ana", "Okafor, Ben"]


def test_byline_with_a_single_name():
    assert coins.byline_authors("Prince") == ["Prince"]


def test_empty_byline_has_no_authors():
    assert coins.byline_authors("") == []


# Spans


def test_span_has_the_class_zotero_looks_for():
    span = coins.coins_span(ROW, 1, "2026-10-23", ["Bell, Scout"])
    assert span.startswith('<span class="Z3988" title="')
    assert span.endswith("></span>")


def test_span_describes_a_journal_article():
    found = dict(pairs(coins.coins_span(ROW, 1, "2026-10-23", ["Bell, Scout"])))
    assert found["ctx_ver"] == "Z39.88-2004"
    assert found["rft_val_fmt"] == "info:ofi/fmt:kev:mtx:journal"
    assert found["rft.genre"] == "article"


def test_span_round_trips_the_citation():
    found = dict(pairs(coins.coins_span(ROW, 1, "2026-10-23", ["Bell, Scout"])))
    assert found["rft.atitle"] == ROW["title"]
    assert found["rft.jtitle"] == "Humanities Methods in Librarianship"
    assert found["rft.issue"] == "1"
    assert found["rft.date"] == "2026-10-23"
    assert found["rft.au"] == "Bell, Scout"
    assert found["rft_id"] == ROW["target"]
    assert found["rft.language"] == "en"


def test_span_has_one_au_per_author_in_byline_order():
    span = coins.coins_span(ROW, 1, None, ["Ruiz, Ana", "Okafor, Ben"])
    assert [v for k, v in pairs(span) if k == "rft.au"] == ["Ruiz, Ana", "Okafor, Ben"]


def test_span_never_uses_aulast_or_aufirst():
    span = coins.coins_span(ROW, 1, None, ["Bell, Scout"])
    assert not any(k in ("rft.aulast", "rft.aufirst") for k, _ in pairs(span))


def test_span_leaves_out_a_missing_date_and_issn():
    keys = [k for k, _ in pairs(coins.coins_span(ROW, 1, None, ["Bell, Scout"]))]
    assert "rft.date" not in keys
    assert "rft.issn" not in keys


def test_span_includes_an_issn_once_set():
    span = coins.coins_span(ROW, 1, None, ["Bell, Scout"], issn="1234-5678")
    assert dict(pairs(span))["rft.issn"] == "1234-5678"


def test_span_escapes_ampersands_between_pairs():
    span = coins.coins_span(ROW, 1, None, ["Bell, Scout"])
    title = re.search(r'title="([^"]*)"', span).group(1)
    assert "&amp;rft.atitle=" in title
    assert "&rft" not in title.replace("&amp;rft", "")


def test_span_percent_encodes_spaces_commas_and_colons():
    title = coins.context_object(ROW, 1, None, ["Bell, Scout"])
    assert "rft.au=Bell%2C%20Scout" in title
    assert "Care%20and%20Compliance%3A%20" in title
    assert " " not in title


def test_span_percent_encodes_curly_apostrophes_as_utf8():
    row = ROW | {"title": "Pretend It’s Magic"}
    assert "It%E2%80%99s" in coins.context_object(row, 1, None, [])


def test_span_never_contains_a_bare_quote():
    row = ROW | {"title": 'A "quoted" title'}
    span = coins.coins_span(row, 1, None, [])
    assert span.count('"') == 4  # only the two attributes' own quotes


def test_span_can_hold_a_zero_width_space():
    span = coins.coins_span(ROW, 1, None, [], filler="&#8203;")
    assert span.endswith(">&#8203;</span>")


# Generating an issue


def write_links(tmp_path, rows_csv):
    path = tmp_path / "links.csv"
    path.write_text(
        "path,kind,manifold_id,category,title,subtitle,target\n" + rows_csv,
        encoding="utf-8",
    )
    return path


LINKS = (
    "1,issue,p1,,\"Humanities Methods in Librarianship, no. 1\",,https://x/p\n"
    "1/one,text,t1,Peer Reviewed,First Title,Ana Ruiz,https://x/read/one\n"
    "1/editorial,text,t2,Editorial,Editorial,,https://x/read/ed\n"
    "2/next,text,t3,Peer Reviewed,Next Issue,Cy Tran,https://x/read/next\n"
)


def test_generate_makes_one_span_per_text_in_the_issue(tmp_path):
    output, _ = coins.generate(
        1, "2026-10-23", write_links(tmp_path, LINKS), tmp_path / "none.csv"
    )
    assert output.count('class="Z3988"') == 2
    assert "<!-- 1/one: First Title -->" in output
    assert "Next%20Issue" not in output


def test_generate_warns_about_a_text_without_authors(tmp_path):
    _, warnings = coins.generate(
        1, None, write_links(tmp_path, LINKS), tmp_path / "none.csv"
    )
    assert len(warnings) == 1
    assert warnings[0].startswith("1/editorial:")


def test_generate_prefers_authors_from_coins_authors_csv(tmp_path):
    authors = tmp_path / "coins_authors.csv"
    authors.write_text(
        "path,authors\n1/editorial,\"Eaton, Mark; de la Cruz, Ana\"\n", encoding="utf-8"
    )
    output, warnings = coins.generate(
        1, None, write_links(tmp_path, LINKS), authors
    )
    assert warnings == []
    assert "rft.au=Eaton%2C%20Mark&amp;rft.au=de%20la%20Cruz%2C%20Ana" in output


def test_generate_warns_about_a_plus_sign_zotero_would_drop(tmp_path):
    links = LINKS + "1/plus,text,t5,Essay,C++ in the Library,Ana Ruiz,https://x/read/p\n"
    _, warnings = coins.generate(1, None, write_links(tmp_path, links), tmp_path / "x")
    assert any(w.startswith("1/plus:") for w in warnings)


def test_generate_stops_for_an_issue_with_no_texts(tmp_path):
    with pytest.raises(SystemExit):
        coins.generate(3, None, write_links(tmp_path, LINKS), tmp_path / "none.csv")


def test_comments_never_contain_a_double_hyphen(tmp_path):
    links = LINKS + "1/dash,text,t4,Essay,Before--After,Ana Ruiz,https://x/read/d\n"
    output, _ = coins.generate(1, None, write_links(tmp_path, links), tmp_path / "x")
    for comment in re.findall(r"<!--(.*?)-->", output, re.S):
        assert "--" not in comment


def test_read_links_stops_when_links_csv_is_missing(tmp_path):
    with pytest.raises(SystemExit, match="next to _shortener"):
        coins.read_links(tmp_path / "links.csv")


def test_read_links_stops_when_a_needed_column_is_missing(tmp_path):
    path = tmp_path / "links.csv"
    path.write_text("path,kind,title,target\n1/a,text,A,https://x\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="subtitle"):
        coins.read_links(path)


def test_read_links_stops_on_an_unquoted_comma(tmp_path):
    path = write_links(tmp_path, "1/a,text,t1,Essay,Title, With Comma,Ana Ruiz,https://x\n")
    with pytest.raises(SystemExit, match="1/a"):
        coins.read_links(path)


def test_links_csv_is_found_next_to_coins():
    assert coins.LINKS_CSV.parent.name == "_shortener"
    assert coins.LINKS_CSV.parent.parent == coins.COINS_DIR.parent


def test_issue_number_accepts_1():
    assert coins.issue_number("1") == 1


def test_issue_number_refuses_0_and_words():
    for bad in ("0", "-1", "one"):
        with pytest.raises(Exception):
            coins.issue_number(bad)


def test_publication_date_accepts_a_year():
    assert coins.publication_date("2026") == "2026"


def test_publication_date_accepts_a_full_date():
    assert coins.publication_date("2026-10-23") == "2026-10-23"


def test_publication_date_refuses_another_format():
    with pytest.raises(Exception):
        coins.publication_date("10/23/2026")


def test_committed_links_csv_makes_spans_for_issue_1():
    output, _ = coins.generate(1, "2026-10-23")
    assert output.count('class="Z3988"') == 11


# Writing every issue (what the GitHub Actions workflow runs)


def write_dates(tmp_path, text):
    path = tmp_path / "issue_dates.csv"
    path.write_text("issue,date\n" + text, encoding="utf-8")
    return path


def test_issues_in_lists_each_issue_with_texts_once(tmp_path):
    rows = coins.read_links(write_links(tmp_path, LINKS))
    assert coins.issues_in(rows) == [1, 2]


def test_write_all_writes_one_file_per_issue(tmp_path):
    spans = tmp_path / "spans"
    coins.write_all(
        write_links(tmp_path, LINKS),
        tmp_path / "none.csv",
        write_dates(tmp_path, "1,2026\n2,2027\n"),
        spans,
    )
    assert sorted(p.name for p in spans.iterdir()) == ["1.html", "2.html"]
    assert "rft.date=2026&amp;" in (spans / "1.html").read_text(encoding="utf-8")
    assert "rft.date=2027&amp;" in (spans / "2.html").read_text(encoding="utf-8")


def test_write_all_warns_about_an_issue_without_a_date(tmp_path):
    spans = tmp_path / "spans"
    warnings = coins.write_all(
        write_links(tmp_path, LINKS),
        tmp_path / "none.csv",
        write_dates(tmp_path, "1,2026\n"),
        spans,
    )
    assert any(w.startswith("issue 2:") for w in warnings)
    assert "rft.date" not in (spans / "2.html").read_text(encoding="utf-8")


def test_write_all_passes_the_zero_width_space_through(tmp_path):
    spans = tmp_path / "spans"
    coins.write_all(
        write_links(tmp_path, LINKS),
        tmp_path / "none.csv",
        write_dates(tmp_path, "1,2026\n"),
        spans,
        filler="&#8203;",
    )
    assert ">&#8203;</span>" in (spans / "1.html").read_text(encoding="utf-8")


def test_write_all_is_stable_when_run_twice(tmp_path):
    spans = tmp_path / "spans"
    args = (
        write_links(tmp_path, LINKS),
        tmp_path / "none.csv",
        write_dates(tmp_path, "1,2026\n2,2027\n"),
        spans,
    )
    coins.write_all(*args)
    first = (spans / "1.html").read_text(encoding="utf-8")
    coins.write_all(*args)
    assert (spans / "1.html").read_text(encoding="utf-8") == first


def test_issue_dates_refuse_a_badly_formatted_date(tmp_path):
    with pytest.raises(SystemExit, match="issue 1"):
        coins.read_issue_dates(write_dates(tmp_path, "1,Oct 2026\n"))


def test_committed_issue_dates_cover_every_issue_in_links_csv():
    dates = coins.read_issue_dates(coins.ISSUE_DATES_CSV)
    for issue in coins.issues_in(coins.read_links(coins.LINKS_CSV)):
        assert str(issue) in dates, f"add issue {issue} to issue_dates.csv"

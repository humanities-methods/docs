"""Tests for the HML short URL generator.

The JSON files in tests/fixtures/ are real Manifold API responses for issue 1,
saved on 2026-09-30 so these tests never touch the network:

- journals.json: GET /api/v1/journals?filter[slug]=hml (trimmed to id/slug/title)
- journal_issues.json: GET /api/v1/journals/{id}/relationships/journal_issues?page[size]=100
- project_issue_1.json: GET /api/v1/projects/{id}?include=texts,textCategories
  (trimmed to the texts and categories; user records removed)
"""

import argparse
import json
from pathlib import Path

import pytest

import shorten

FIXTURES = Path(__file__).parent / "fixtures"
LINKS_CSV = Path(__file__).parent.parent / "links.csv"

ISSUE_1_PROJECT_ID = "3691fe2b-8a51-4d25-880e-14997c4074e0"
ISSUE_1_TARGET = (
    "https://cuny.manifoldapp.org/projects/humanities-methods-in-librarianship-no-1"
)
METADATA_ID = "306e4de4-0664-46fd-beba-b05ce6989a41"
METADATA_TITLE = "Metadata as Care: Cultivating Meaningful Access in Digital Archives"
METADATA_TARGET = (
    "https://cuny.manifoldapp.org/read/"
    "metadata-as-care-cultivating-meaningful-access-in-digital-archives"
    "-ad5fe943-33ae-40e7-96f5-82695273d06f"
)


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def issue_1():
    return {
        "number": 1,
        "project_id": ISSUE_1_PROJECT_ID,
        "project_slug": "humanities-methods-in-librarianship-no-1",
        "title": "Humanities Methods in Librarianship, no. 1",
    }


def issue_1_texts():
    return shorten.parse_texts(load_fixture("project_issue_1.json"))


# Rows as they appear in links.csv. Pass keyword arguments to change a field,
# e.g. metadata_row(path="1/care").


def issue_row(**changes):
    row = {
        "path": "1",
        "kind": "issue",
        "manifold_id": ISSUE_1_PROJECT_ID,
        "category": "",
        "title": "Humanities Methods in Librarianship, no. 1",
        "subtitle": "",
        "target": ISSUE_1_TARGET,
    }
    return row | changes


def metadata_row(**changes):
    row = {
        "path": "1/metadata-as-care",
        "kind": "text",
        "manifold_id": METADATA_ID,
        "category": "Peer Reviewed",
        "title": METADATA_TITLE,
        "subtitle": "Lisa M. Longenecker",
        "target": METADATA_TARGET,
    }
    return row | changes


# --- Reading the Manifold API responses ---


def test_find_journal_id_picks_hml_out_of_all_journals():
    journals = load_fixture("journals.json")
    assert shorten.find_journal_id(journals) == "3d645582-2b7d-4ff6-8c63-e72872e86961"


def test_parse_issues_keeps_only_issue_numbers_1_and_up():
    issues = shorten.parse_issues(load_fixture("journal_issues.json"))
    assert [issue["number"] for issue in issues] == [1]


def test_parse_issues_gives_project_details_for_issue_1():
    issues = shorten.parse_issues(load_fixture("journal_issues.json"))
    assert issues[0] == issue_1()


def test_parse_issues_skips_issues_without_a_number():
    response = {
        "data": [
            {
                "id": "x",
                "type": "journalIssues",
                "attributes": {
                    "number": "Special",
                    "projectId": "p",
                    "projectSlug": "s",
                    "title": "t",
                },
            }
        ]
    }
    assert shorten.parse_issues(response) == []


def test_parse_texts_lists_texts_in_table_of_contents_order():
    texts = shorten.parse_texts(load_fixture("project_issue_1.json"))
    assert [text["title"] for text in texts] == [
        "Metadata as Care: Cultivating Meaningful Access in Digital Archives",
        "Embracing Place and Naming Placelessness in Librarianship",
        "Reading Disrepair: Library Space and Institutional Value",
        "Ode to The Abode of All Known",
        "Pretend It’s Magic: The Story of a Library Management System",
        "Review of Triptych: Death, AI, and Librarianship",
        "Review of Hayek’s Bastards: The Neoliberal Roots of the Populist Right",
        "Review of How to Study Public Life",
    ]


def test_parse_texts_gives_id_category_subtitle_and_manifold_url():
    texts = shorten.parse_texts(load_fixture("project_issue_1.json"))
    assert texts[0] == {
        "id": METADATA_ID,
        "title": METADATA_TITLE,
        "subtitle": "Lisa M. Longenecker",
        "category": "Peer Reviewed",
        "target": METADATA_TARGET,
    }


def test_parse_texts_skips_unpublished_texts():
    project = {
        "included": [
            {
                "id": "c1",
                "type": "categories",
                "attributes": {"title": "Peer Reviewed", "position": 1},
            },
            {
                "id": "t1",
                "type": "texts",
                "attributes": {
                    "title": "Draft",
                    "subtitlePlaintext": "",
                    "slug": "draft",
                    "published": False,
                    "position": 1,
                },
                "relationships": {"category": {"data": {"id": "c1"}}},
            },
            {
                "id": "t2",
                "type": "texts",
                "attributes": {
                    "title": "Final",
                    "subtitlePlaintext": "",
                    "slug": "final",
                    "published": True,
                    "position": 2,
                },
                "relationships": {"category": {"data": {"id": "c1"}}},
            },
        ]
    }
    assert [text["title"] for text in shorten.parse_texts(project)] == ["Final"]


def test_current_targets_maps_the_issue_project_to_its_manifold_page():
    current = shorten.current_targets(load_fixture("project_issue_1.json"))
    assert current[ISSUE_1_PROJECT_ID] == {
        "title": "Humanities Methods in Librarianship, no. 1",
        "subtitle": "",
        "target": ISSUE_1_TARGET,
    }


def test_current_targets_maps_each_text_to_its_reading_url():
    current = shorten.current_targets(load_fixture("project_issue_1.json"))
    assert current[METADATA_ID] == {
        "title": METADATA_TITLE,
        "subtitle": "Lisa M. Longenecker",
        "target": METADATA_TARGET,
    }


def test_current_targets_covers_the_issue_and_all_8_texts():
    current = shorten.current_targets(load_fixture("project_issue_1.json"))
    assert len(current) == 9


# --- Proposing a short code from a title ---


def test_code_uses_the_main_title_before_the_colon():
    title = "Reading Disrepair: Library Space and Institutional Value"
    assert shorten.propose_code(title) == "reading-disrepair"


def test_code_stops_after_two_content_words():
    title = "Embracing Place and Naming Placelessness in Librarianship"
    assert shorten.propose_code(title) == "embracing-place"


def test_code_keeps_small_words_between_the_two_content_words():
    title = "Metadata as Care: Cultivating Meaningful Access in Digital Archives"
    assert shorten.propose_code(title) == "metadata-as-care"


def test_code_is_lowercase():
    assert shorten.propose_code("Ode to The Abode of All Known") == "ode-to-the-abode"


def test_code_drops_curly_and_straight_apostrophes():
    assert shorten.propose_code("Pretend It’s Magic: The Story") == "pretend-its-magic"
    assert shorten.propose_code("Pretend It's Magic: The Story") == "pretend-its-magic"


def test_code_turns_accented_letters_into_plain_letters():
    assert shorten.propose_code("Émigré Archives: A Study") == "emigre-archives"


def test_code_for_a_review_starts_with_review():
    title = "Review of Triptych: Death, AI, and Librarianship"
    assert shorten.propose_code(title) == "review-triptych"


def test_code_for_a_review_uses_the_reviewed_title():
    title = "Review of Hayek’s Bastards: The Neoliberal Roots of the Populist Right"
    assert shorten.propose_code(title) == "review-hayeks-bastards"


def test_code_for_a_review_without_a_colon():
    title = "Review of How to Study Public Life"
    assert shorten.propose_code(title) == "review-how-to-study"


def test_code_for_a_title_without_latin_letters_is_text():
    assert shorten.propose_code("日本の図書館") == "text"


def test_code_for_a_review_of_a_title_without_latin_letters():
    assert shorten.propose_code("Review of Библиотека") == "review-text"


# --- `add`: new rows for an issue ---


def test_new_rows_for_issue_1_match_the_planned_short_links():
    rows = shorten.new_rows(issue_1(), issue_1_texts(), [])
    assert [row["path"] for row in rows] == [
        "1",
        "1/metadata-as-care",
        "1/embracing-place",
        "1/reading-disrepair",
        "1/ode-to-the-abode",
        "1/pretend-its-magic",
        "1/review-triptych",
        "1/review-hayeks-bastards",
        "1/review-how-to-study",
    ]


def test_new_rows_start_with_a_row_for_the_issue_itself():
    assert shorten.new_rows(issue_1(), [], []) == [issue_row()]


def test_new_rows_describe_each_text():
    rows = shorten.new_rows(issue_1(), issue_1_texts(), [])
    assert rows[1] == metadata_row()


def test_new_rows_add_nothing_when_run_twice():
    first_run = shorten.new_rows(issue_1(), issue_1_texts(), [])
    assert shorten.new_rows(issue_1(), issue_1_texts(), first_run) == []


def test_new_rows_skip_a_text_whose_code_an_editor_changed():
    existing = [issue_row(), metadata_row(path="1/care")]
    rows = shorten.new_rows(issue_1(), issue_1_texts()[:1], existing)
    assert rows == []


def test_new_rows_number_a_repeated_code():
    texts = [
        {
            "id": "a",
            "title": "Review of Triptych",
            "subtitle": "",
            "category": "Book Reviews",
            "target": "https://example.org/a",
        },
        {
            "id": "b",
            "title": "Review of Triptych: A Second Look",
            "subtitle": "",
            "category": "Book Reviews",
            "target": "https://example.org/b",
        },
    ]
    rows = shorten.new_rows(issue_1(), texts, [])
    assert [row["path"] for row in rows] == [
        "1",
        "1/review-triptych",
        "1/review-triptych-2",
    ]


def test_new_rows_avoid_a_code_already_in_links_csv():
    existing = [issue_row(), metadata_row()]
    texts = [
        {
            "id": "new",
            "title": "Metadata as Care, Again",
            "subtitle": "",
            "category": "Peer Reviewed",
            "target": "https://example.org/new",
        }
    ]
    rows = shorten.new_rows(issue_1(), texts, existing)
    assert [row["path"] for row in rows] == ["1/metadata-as-care-2"]


# --- `add`: which issue numbers are allowed ---


def test_issue_number_accepts_1():
    assert shorten.issue_number("1") == 1


def test_issue_number_refuses_0():
    with pytest.raises(argparse.ArgumentTypeError):
        shorten.issue_number("0")


def test_issue_number_refuses_minus_1():
    with pytest.raises(argparse.ArgumentTypeError):
        shorten.issue_number("-1")


def test_issue_number_refuses_words():
    with pytest.raises(argparse.ArgumentTypeError):
        shorten.issue_number("one")


# --- `build`: refreshing targets from Manifold ---


def test_refresh_rows_follow_a_changed_manifold_slug():
    new_target = "https://cuny.manifoldapp.org/read/metadata-as-care-new-slug"
    current = {
        METADATA_ID: {
            "title": METADATA_TITLE,
            "subtitle": "Lisa M. Longenecker",
            "target": new_target,
        }
    }
    rows = shorten.refresh_rows([metadata_row()], current)
    assert rows == [metadata_row(target=new_target)]


def test_refresh_rows_update_the_title_but_never_the_path():
    current = {
        METADATA_ID: {
            "title": "Metadata as Care (Revised)",
            "subtitle": "Lisa M. Longenecker",
            "target": METADATA_TARGET,
        }
    }
    rows = shorten.refresh_rows([metadata_row()], current)
    assert rows == [metadata_row(title="Metadata as Care (Revised)")]


def test_refresh_rows_keep_the_last_target_when_a_text_is_missing():
    assert shorten.refresh_rows([metadata_row()], {}) == [metadata_row()]


def test_refresh_rows_update_the_issue_row_too():
    new_target = "https://cuny.manifoldapp.org/projects/hml-issue-1"
    current = {
        ISSUE_1_PROJECT_ID: {
            "title": "Humanities Methods in Librarianship, no. 1",
            "subtitle": "",
            "target": new_target,
        }
    }
    rows = shorten.refresh_rows([issue_row()], current)
    assert rows == [issue_row(target=new_target)]


# --- The redirect page ---


def test_render_page_redirects_in_three_ways():
    page = shorten.render_page(metadata_row())
    assert f'<link rel="canonical" href="{METADATA_TARGET}">' in page
    assert f'<meta http-equiv="refresh" content="0; url={METADATA_TARGET}">' in page
    assert f'location.replace("{METADATA_TARGET}")' in page


def test_render_page_is_in_english():
    assert '<html lang="en">' in shorten.render_page(metadata_row())


def test_render_page_names_the_text_in_the_browser_tab():
    page = shorten.render_page(metadata_row())
    assert f"<title>{METADATA_TITLE}</title>" in page


def test_render_page_shows_a_link_for_readers_without_redirects():
    page = shorten.render_page(metadata_row())
    assert f'<a href="{METADATA_TARGET}">{METADATA_TITLE}</a>' in page


def test_render_page_has_link_preview_tags():
    page = shorten.render_page(metadata_row())
    assert f'<meta property="og:title" content="{METADATA_TITLE}">' in page
    assert '<meta property="og:description" content="Lisa M. Longenecker">' in page
    assert f'<meta property="og:url" content="{METADATA_TARGET}">' in page
    assert (
        '<meta property="og:site_name" content="Humanities Methods in Librarianship">'
        in page
    )
    assert '<meta name="twitter:card" content="summary">' in page


def test_render_page_leaves_out_an_empty_description():
    assert "og:description" not in shorten.render_page(issue_row())


def test_render_page_escapes_the_title():
    page = shorten.render_page(metadata_row(title='Care & "Access" <Archives>'))
    assert "Care &amp; &quot;Access&quot; &lt;Archives&gt;" in page
    assert "<Archives>" not in page


def test_render_page_has_no_jekyll_front_matter():
    assert not shorten.render_page(metadata_row()).startswith("---")


# --- Writing the pages into the docs site ---


def test_write_pages_writes_one_index_html_per_row(tmp_path):
    shorten.write_pages([issue_row(), metadata_row()], tmp_path)
    issue_page = tmp_path / "1" / "index.html"
    text_page = tmp_path / "1" / "metadata-as-care" / "index.html"
    assert issue_page.read_text(encoding="utf-8") == shorten.render_page(issue_row())
    assert text_page.read_text(encoding="utf-8") == shorten.render_page(metadata_row())


def test_write_pages_leaves_the_rest_of_the_site_alone(tmp_path):
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "1014.1.jpg").write_bytes(b"image")
    shorten.write_pages([issue_row(), metadata_row()], tmp_path)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["1", "static"]
    assert (tmp_path / "static" / "1014.1.jpg").read_bytes() == b"image"


# --- links.csv ---


def test_links_csv_round_trip(tmp_path):
    csv_path = tmp_path / "links.csv"
    shorten.write_links(csv_path, [issue_row(), metadata_row()])
    assert shorten.read_links(csv_path) == [issue_row(), metadata_row()]


def test_links_csv_columns_are_in_a_fixed_order(tmp_path):
    csv_path = tmp_path / "links.csv"
    shorten.write_links(csv_path, [issue_row()])
    header = csv_path.read_text(encoding="utf-8").splitlines()[0]
    assert header == "path,kind,manifold_id,category,title,subtitle,target"


def test_validate_links_accepts_good_rows():
    assert shorten.validate_links([issue_row(), metadata_row()]) == []


def test_validate_links_flags_a_repeated_path():
    rows = [metadata_row(), metadata_row(manifold_id="another-text")]
    problems = shorten.validate_links(rows)
    assert len(problems) == 1
    assert "1/metadata-as-care" in problems[0]


def test_validate_links_flags_capital_letters_in_a_code():
    problems = shorten.validate_links([metadata_row(path="1/Metadata-As-Care")])
    assert len(problems) == 1


def test_validate_links_flags_spaces_in_a_code():
    problems = shorten.validate_links([metadata_row(path="1/metadata as care")])
    assert len(problems) == 1


def test_validate_links_flags_a_text_row_without_a_code():
    problems = shorten.validate_links([metadata_row(path="1")])
    assert len(problems) == 1


def test_validate_links_flags_a_path_outside_an_issue_folder():
    problems = shorten.validate_links([metadata_row(path="static/metadata-as-care")])
    assert len(problems) == 1


def test_validate_links_flags_issue_0():
    problems = shorten.validate_links([metadata_row(path="0/metadata-as-care")])
    assert len(problems) == 1


def test_validate_links_flags_a_path_that_climbs_out_of_the_site():
    problems = shorten.validate_links([metadata_row(path="1/../../etc")])
    assert len(problems) == 1


def test_validate_links_flags_an_unknown_kind():
    problems = shorten.validate_links([metadata_row(kind="article")])
    assert len(problems) == 1


def test_committed_links_csv_is_valid():
    # Guards hand edits: CI runs this before building any pages.
    assert shorten.validate_links(shorten.read_links(LINKS_CSV)) == []


# --- `add`: finding the requested issue ---


def test_find_issue_returns_the_requested_issue():
    issues = shorten.parse_issues(load_fixture("journal_issues.json"))
    assert shorten.find_issue(issues, 1) == issue_1()


def test_find_issue_explains_an_issue_not_on_manifold_yet():
    issues = shorten.parse_issues(load_fixture("journal_issues.json"))
    with pytest.raises(SystemExit, match="Issue 2 isn't on Manifold yet"):
        shorten.find_issue(issues, 2)


# --- `build`: refusing a broken links.csv ---


def test_check_links_lets_good_rows_through():
    shorten.check_links([issue_row(), metadata_row()])  # does not stop


def test_check_links_stops_and_names_the_bad_path():
    with pytest.raises(SystemExit, match="1/Metadata-As-Care"):
        shorten.check_links([metadata_row(path="1/Metadata-As-Care")])


def test_build_writes_nothing_from_a_broken_links_csv(tmp_path):
    csv_path = tmp_path / "links.csv"
    shorten.write_links(csv_path, [metadata_row(path="1/bad code")])
    with pytest.raises(SystemExit):
        shorten.build(csv_path, tmp_path / "site")
    assert not (tmp_path / "site").exists()

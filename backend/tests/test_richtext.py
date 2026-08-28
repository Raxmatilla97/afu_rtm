"""Tests for afu_shared/richtext.py — the sanitizer behind rich request descriptions.

Two things are being pinned down here, and they fail in opposite directions.

The **security** cases are the reason the module exists: `description_html` is written by a
user and rendered back into an administrator's browser, so anything that survives the
allowlist is script that runs with their session. Those tests assert on what is *absent*.

The **fidelity** cases are the reason it is not simply "strip all tags": the plain reading
produced here is what every Telegram surface prints, and a list that arrives as one run-on
line is a description nobody can act on.
"""

from afu_shared.richtext import html_to_text, safe_href, sanitize_html


class TestSanitizeDropsDanger:
    def test_script_tag_and_its_contents_are_gone(self):
        assert sanitize_html("<p>ok</p><script>alert(1)</script>") == "<p>ok</p>"

    def test_event_handler_attributes_do_not_survive(self):
        # The tag is rebuilt rather than filtered, so no attribute can be carried across.
        assert 'onclick' not in sanitize_html('<p onclick="steal()">matn</p>')

    def test_javascript_href_degrades_to_plain_text(self):
        result = sanitize_html('<a href="javascript:alert(1)">bosing</a>')
        assert "javascript" not in result
        assert html_to_text(result) == "bosing"

    def test_control_characters_cannot_smuggle_a_scheme(self):
        assert safe_href("java\tscript:alert(1)") is None

    def test_data_uri_is_refused(self):
        assert safe_href("data:text/html;base64,PHNjcmlwdD4=") is None

    def test_image_tag_is_dropped(self):
        # Images are attachments here, never markup — an <img> is only ever a way to reach
        # a remote host from inside somebody else's page.
        assert sanitize_html('<img src="x" onerror="alert(1)">') == ""

    def test_style_block_takes_its_contents_with_it(self):
        assert sanitize_html("<style>body{display:none}</style><p>bor</p>") == "<p>bor</p>"

    def test_unknown_wrapper_loses_its_tag_but_keeps_its_text(self):
        assert sanitize_html('<span style="color:red">rangli</span>') == "rangli"

    def test_bare_angle_brackets_are_escaped_not_dropped(self):
        assert html_to_text(sanitize_html("5 < 6 va 7 > 6")) == "5 < 6 va 7 > 6"


class TestSanitizeKeepsFormatting:
    def test_legacy_tags_are_normalised(self):
        assert sanitize_html("<b>qalin</b> <i>egik</i>") == "<strong>qalin</strong> <em>egik</em>"

    def test_div_becomes_a_paragraph(self):
        # contenteditable emits <div> for a line in some browsers and <p> in others.
        assert sanitize_html("<div>bir</div>") == "<p>bir</p>"

    def test_unclosed_tags_are_closed(self):
        assert sanitize_html("<p><b>tugallanmagan") == "<p><strong>tugallanmagan</strong></p>"

    def test_stray_end_tag_is_ignored(self):
        assert sanitize_html("<p>a</b></p>") == "<p>a</p>"

    def test_bare_domain_becomes_an_https_link(self):
        result = sanitize_html('<a href="rtm.afu.uz">RTM</a>')
        assert 'href="https://rtm.afu.uz"' in result
        assert 'rel="noopener noreferrer nofollow"' in result

    def test_lists_survive(self):
        assert sanitize_html("<ul><li>a</li><li>b</li></ul>") == "<ul><li>a</li><li>b</li></ul>"


class TestEmptiness:
    def test_a_paragraph_holding_only_a_non_breaking_space_is_empty(self):
        # What an untouched contenteditable actually contains. Without this it would pass
        # every "did they write anything?" check in the application.
        assert sanitize_html("<p>&nbsp;</p>") == ""

    def test_whitespace_only_markup_is_empty(self):
        assert sanitize_html("<p></p><p><br></p>") == ""

    def test_none_and_empty_input(self):
        assert sanitize_html(None) == ""
        assert sanitize_html("") == ""


class TestHtmlToText:
    def test_list_items_get_bullets_and_no_blank_lines_between_them(self):
        assert html_to_text("<ul><li>a</li><li>b</li></ul>") == "• a\n• b"

    def test_paragraphs_are_separated_by_one_blank_line(self):
        assert html_to_text("<p>bir</p><p>ikki</p>") == "bir\n\nikki"

    def test_line_break_is_a_single_newline(self):
        assert html_to_text("<p>bir<br>ikki</p>") == "bir\nikki"

    def test_entities_are_decoded(self):
        assert html_to_text("<p>A &amp; B</p>") == "A & B"

    def test_runs_of_blank_lines_collapse(self):
        assert html_to_text("<p>a</p><p></p><p></p><p>b</p>") == "a\n\nb"

    def test_plain_text_passes_through(self):
        assert html_to_text("oddiy matn") == "oddiy matn"

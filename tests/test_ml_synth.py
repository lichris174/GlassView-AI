"""Synthetic screen templates: tagging follows the labeling guide (string-level, no browser)."""

from __future__ import annotations

import random
import re

import pytest
from faker import Faker

from ml.synth import templates as T

ALL = {**T.SENSITIVE, **T.CLEAN}


def _render(template: T.Template, seed: int) -> str:
    fk = Faker()
    fk.seed_instance(seed)
    return template(random.Random(seed), fk)


def _find(template: T.Template, needle: str, tries: int = 200) -> str:
    """First rendering (over seeds) whose HTML contains ``needle``."""
    for seed in range(tries):
        html = _render(template, seed)
        if needle in html:
            return html
    pytest.fail(f"no rendering of {template.__name__} contains {needle!r}")


def _tagged_after(html: str, label: str) -> str | None:
    """The data-s class of the element right after ``<label>{label}</label>``."""
    m = re.search(rf"<label>{re.escape(label)}</label><(\w+)( data-s=\"(\w+)\")?", html)
    assert m, f"no {label!r} field"
    return m.group(3)


@pytest.mark.parametrize("name", sorted(ALL))
def test_no_doubled_class_attribute(name: str) -> None:
    for seed in range(40):
        html = _render(ALL[name], seed)
        assert 'class="class=' not in html
        # One class attribute per tag at most.
        for tag in re.findall(r"<[^>]+>", html):
            assert tag.count(" class=") <= 1, tag


def test_profile_tags_full_name_but_not_username() -> None:
    for label in ("Full name", "Phone"):
        html = _find(T.profile, f"<label>{label}</label>")
        assert _tagged_after(html, label) == "personal_id", label
    # A username is not a contact detail in the guide: hard negative.
    assert _tagged_after(_find(T.profile, "<label>Username</label>"), "Username") is None
    # Tagged profile fields keep the same .field styling as everything else,
    # so styling cannot give the label away.
    html = _find(T.profile, "<label>Phone</label>")
    assert re.search(r'<div data-s="personal_id" class="field">', html)


def test_filled_login_tags_email_as_credential() -> None:
    html = _find(T.login, 'type="password" value=')
    assert re.search(r'<label>Email</label><input data-s="credential" value="', html)
    # Empty sign-in forms stay untagged: they are hard negatives.
    empty = _find(T.login, 'placeholder="Email"')
    assert "data-s" not in empty


def test_bank_tags_customer_name_not_its_label() -> None:
    html = _find(T.bank, "Customer: ")
    assert re.search(r'Customer: <span data-s="personal_id">[^<]+</span>', html)


def test_email_reading_pane_includes_sender() -> None:
    html = _find(T.email, "<section")
    assert re.search(r'<div data-s="private_message"><div class="muted">[^<]+ &lt;', html)


def test_checkout_labels_stay_outside_tagged_regions() -> None:
    html = _render(T.checkout, 0)
    tagged = re.findall(r'<(\w+) data-s="\w+"[^>]*>', html)
    assert tagged and set(tagged) <= {"input", "textarea"}  # values only, never a <label>


def test_vault_tags_username_as_credential() -> None:
    html = _find(T.vault, "<label>Username</label>")
    assert _tagged_after(html, "Username") == "credential"


def test_checkout_tags_buyer_name_as_personal_id() -> None:
    html = _render(T.checkout, 0)
    assert _tagged_after(html, "Name") == "personal_id"


# --- layout in a real browser (skipped when Chromium is unavailable) ----------
# Per field: its tag, data-s class, rendered width, and the width of the form
# control inside it (or of itself, when the field is the control).
GEOMETRY_JS = """
() => [...document.querySelectorAll('input, textarea, .field')].map(el => {
  const box = el.getBoundingClientRect();
  const ctl = el.matches('input, textarea') ? el : el.querySelector('input, textarea');
  return {tag: el.tagName, cls: el.dataset.s || null, label: el.previousElementSibling?.textContent,
          w: box.width, ctl: ctl ? ctl.getBoundingClientRect().width : box.width};
})
"""


@pytest.fixture(scope="module")
def page():  # noqa: ANN201
    sync_api = pytest.importorskip("playwright.sync_api")
    # sync_playwright runs its own event loop; it must be stopped on every path
    # or later async tests fail with "This event loop is already running".
    pw = sync_api.sync_playwright().start()
    try:
        browser = pw.chromium.launch()
    except Exception as e:  # noqa: BLE001 - any launch failure means "no browser here"
        pw.stop()
        pytest.skip(f"Chromium unavailable: {e}")
    try:
        yield browser.new_page(viewport={"width": 1366, "height": 768})
    finally:
        browser.close()
        pw.stop()
    pw.stop()


def _measure(page, template: T.Template, seed: int, theme: int | None = None) -> list[dict]:  # noqa: ANN001
    from ml.synth.render import theme_css

    css = theme_css(random.Random(seed if theme is None else theme))
    html = (f"<!doctype html><html><head><meta charset='utf-8'><style>"
            f"{css}</style></head><body><div class='screen'>"
            f"<div class='pane'>{_render(template, seed)}</div></div></body></html>")
    page.set_content(html)
    return page.evaluate(GEOMETRY_JS)


@pytest.mark.parametrize("name", ["login", "checkout", "profile", "vault"])
def test_tagged_box_is_the_field_and_matches_untagged_layout(page, name: str) -> None:  # noqa: ANN001
    for seed in range(12):
        fields = _measure(page, ALL[name], seed)
        for f in fields:
            # A tagged box hugs its control: no wrapper wider than the input.
            assert abs(f["w"] - f["ctl"]) <= 2, (name, seed, f)
        # Tagged and untagged fields in the same column share one width, so
        # width cannot reveal which field is sensitive.
        # (The card expiry/CVC pair shares a row and has no label: skipped.)
        column = [f for f in fields if f["tag"] != "INPUT" or f["label"]]
        widths = {round(f["w"]) for f in column}
        assert max(widths) - min(widths) <= 2, (name, seed, column)


def test_filled_and_empty_login_inputs_have_equal_width(page) -> None:  # noqa: ANN001
    filled = empty = None
    for seed in range(40):  # same theme throughout: only the form content varies
        email = next(f for f in _measure(page, T.login, seed, theme=0) if f["label"] == "Email")
        if email["cls"]:
            filled = filled or email["w"]
        else:
            empty = empty or email["w"]
    assert filled and empty and abs(filled - empty) <= 1

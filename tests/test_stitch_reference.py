from app.stitches import STITCHES

EXPECTED_NAMES = [
    "chain",
    "single crochet",
    "double crochet",
    "half double crochet",
    "treble crochet",
    "magic ring",
    "increase",
    "decrease",
]

EXPECTED_CATEGORIES = {"foundational", "special", "increase", "decrease"}


def test_stitches_constant_has_the_eight_us_stitches():
    assert [stitch["name"] for stitch in STITCHES] == EXPECTED_NAMES


def test_stitches_entries_are_complete():
    for stitch in STITCHES:
        assert stitch["name"].strip()
        assert stitch["symbol"].strip()
        assert stitch["description"].strip()
        assert stitch["category"] in EXPECTED_CATEGORIES


async def test_panel_fragment_is_public_and_shows_all_stitches(async_client):
    """No session on purpose: the reference must work on logged-out pages."""
    response = await async_client.get("/stitches/panel")
    assert response.status_code == 200
    assert 'role="dialog"' in response.text
    # Popover, not a modal: it must sit beside the pattern, not trap focus
    # behind a full-screen backdrop.
    assert "aria-modal" not in response.text
    assert "stitch-panel-backdrop" not in response.text
    for stitch in STITCHES:
        assert stitch["name"] in response.text
        assert stitch["symbol"] in response.text


async def test_panel_fragment_is_available_when_logged_in(test_user, async_client):
    response = await async_client.get("/stitches/panel")
    assert response.status_code == 200
    assert "single crochet" in response.text


async def test_index_page_has_stitch_reference_toggle(async_client):
    response = await async_client.get("/")
    assert response.status_code == 200
    assert "stitch-reference-toggle" in response.text
    assert 'aria-controls="stitch-panel"' in response.text

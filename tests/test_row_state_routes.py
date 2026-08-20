import pytest
from sqlalchemy import delete, func, select

from app.models.pattern import Row
from app.models.progress import RowState, RowStateEnum
from app.models.project import Element, ElementRepetition, Project


@pytest.fixture
async def project_element_rows(test_user, async_client, db_session):
    """Create a Project + Element with rows pasted via the real route, so
    ElementRepetition/RowState rows exist exactly as production writes them.

    Teardown runs as fixture finalization (after yield), so it fires even if an
    assertion in the test body raises.
    """
    project = Project(user_id=test_user.id, name="Sunset shawl")
    db_session.add(project)
    await db_session.commit()

    element = Element(project_id=project.id, name="Body", repeat_count=1)
    db_session.add(element)
    await db_session.commit()

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}",
        data={"pattern_text": "Row 1\nRow 2\nRow 3"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    rows = (
        (
            await db_session.execute(
                select(Row)
                .where(Row.element_id == element.id)
                .order_by(Row.position.asc())
            )
        )
        .scalars()
        .all()
    )

    yield project, element, rows

    rep_ids_sub = select(ElementRepetition.id).where(
        ElementRepetition.element_id == element.id
    )
    await db_session.execute(
        delete(RowState).where(RowState.element_repetition_id.in_(rep_ids_sub))
    )
    await db_session.execute(delete(Row).where(Row.element_id == element.id))
    await db_session.execute(
        delete(ElementRepetition).where(ElementRepetition.element_id == element.id)
    )
    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.commit()


async def _row_state(db_session, row_id):
    # db_session's identity map isn't expired by the app's separate session commit, so a
    # stale cached object would otherwise be returned instead of the fresh row. Scoping
    # populate_existing to this query (rather than session-wide expire_all) avoids
    # expiring unrelated objects (e.g. test_user's `user`) still needed by teardown.
    result = await db_session.execute(
        select(RowState)
        .where(RowState.row_id == row_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _repetition(db_session, element_id, rep_number):
    result = await db_session.execute(
        select(ElementRepetition)
        .where(
            ElementRepetition.element_id == element_id,
            ElementRepetition.repetition_number == rep_number,
        )
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _rep_row_state(db_session, element_id, rep_number, row_id):
    rep = await _repetition(db_session, element_id, rep_number)
    result = await db_session.execute(
        select(RowState)
        .where(RowState.element_repetition_id == rep.id, RowState.row_id == row_id)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _rep_count(db_session, element_id):
    result = await db_session.execute(
        select(func.count(ElementRepetition.id)).where(
            ElementRepetition.element_id == element_id
        )
    )
    return result.scalar_one()


async def _state_count(db_session, element_id):
    rep_ids_sub = select(ElementRepetition.id).where(
        ElementRepetition.element_id == element_id
    )
    result = await db_session.execute(
        select(func.count(RowState.id)).where(
            RowState.element_repetition_id.in_(rep_ids_sub)
        )
    )
    return result.scalar_one()


async def test_toggle_cycles_not_started_to_in_progress(
    test_user, async_client, db_session, project_element_rows
):
    project, element, rows = project_element_rows
    row = rows[0]

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/reps/1/rows/{row.id}/state",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "◐" in response.text
    assert "row-item--in_progress" in response.text

    row_state = await _row_state(db_session, row.id)
    assert row_state.state == RowStateEnum.in_progress


async def test_toggle_full_cycle_returns_to_not_started(
    test_user, async_client, db_session, project_element_rows
):
    project, element, rows = project_element_rows
    row = rows[0]
    url = f"/projects/{project.id}/elements/{element.id}/reps/1/rows/{row.id}/state"

    await async_client.post(url, follow_redirects=False)
    await async_client.post(url, follow_redirects=False)
    row_state = await _row_state(db_session, row.id)
    assert row_state.state == RowStateEnum.done

    await async_client.post(url, follow_redirects=False)
    row_state = await _row_state(db_session, row.id)
    assert row_state.state == RowStateEnum.not_started


async def test_toggle_persists_across_reload(
    test_user, async_client, db_session, project_element_rows
):
    project, element, rows = project_element_rows
    row = rows[0]

    await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/reps/1/rows/{row.id}/state",
        follow_redirects=False,
    )

    response = await async_client.get(
        f"/projects/{project.id}/elements/{element.id}", follow_redirects=False
    )
    assert response.status_code == 200
    assert "◐" in response.text


async def test_toggle_bumps_project_updated_at(
    test_user, async_client, db_session, project_element_rows
):
    project, element, rows = project_element_rows
    row = rows[0]
    updated_before = project.updated_at

    await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/reps/1/rows/{row.id}/state",
        follow_redirects=False,
    )

    await db_session.refresh(project)
    assert project.updated_at > updated_before


async def test_toggle_other_user_sees_404_and_does_not_change_state(
    test_user, second_user, db_session, project_element_rows
):
    _second_user, second_client = second_user
    project, element, rows = project_element_rows
    row = rows[0]

    response = await second_client.post(
        f"/projects/{project.id}/elements/{element.id}/reps/1/rows/{row.id}/state",
        follow_redirects=False,
    )

    assert response.status_code == 404
    row_state = await _row_state(db_session, row.id)
    assert row_state.state == RowStateEnum.not_started


async def test_toggle_wrong_element_pairing_sees_404(
    test_user, async_client, db_session, project_element_rows
):
    project, element, rows = project_element_rows
    row = rows[0]

    other_project = Project(user_id=test_user.id, name="Other project")
    db_session.add(other_project)
    await db_session.commit()

    other_element = Element(project_id=other_project.id, name="Sleeve", repeat_count=1)
    db_session.add(other_element)
    await db_session.commit()

    # row belongs to `element`, not `other_element` — the URL pairing must 404
    # even though test_user owns both projects.
    response = await async_client.post(
        f"/projects/{other_project.id}/elements/{other_element.id}/reps/1/rows/{row.id}/state",
        follow_redirects=False,
    )

    assert response.status_code == 404

    await db_session.execute(delete(Element).where(Element.id == other_element.id))
    await db_session.execute(delete(Project).where(Project.id == other_project.id))
    await db_session.commit()


async def test_auto_jump_first_non_done_row(
    test_user, async_client, db_session, project_element_rows
):
    """Rows 1-2 done, rows 3+ not started — row 3 is the current row."""
    project, element, rows = project_element_rows
    url_base = f"/projects/{project.id}/elements/{element.id}/reps/1/rows"

    # Mark rows 1 and 2 done (two toggles each).
    for row in rows[:2]:
        await async_client.post(f"{url_base}/{row.id}/state", follow_redirects=False)
        await async_client.post(f"{url_base}/{row.id}/state", follow_redirects=False)

    response = await async_client.get(f"/projects/{project.id}/elements/{element.id}")
    assert response.status_code == 200
    # Row 3 (the third row) should be marked as current.
    third_row_id = str(rows[2].id)
    assert f'id="row-{third_row_id}"' in response.text
    assert "row-item--current" in response.text


async def test_auto_jump_all_done_no_current(
    test_user, async_client, db_session, project_element_rows
):
    """All rows done — no current row, page renders without error."""
    project, element, rows = project_element_rows
    url_base = f"/projects/{project.id}/elements/{element.id}/reps/1/rows"

    for row in rows:
        await async_client.post(f"{url_base}/{row.id}/state", follow_redirects=False)
        await async_client.post(f"{url_base}/{row.id}/state", follow_redirects=False)

    response = await async_client.get(f"/projects/{project.id}/elements/{element.id}")
    assert response.status_code == 200
    # No <li> should have the row-item--current class (the CSS rule itself
    # contains the string, so check for the class on an actual element).
    assert '<li class="row-item row-item--current' not in response.text


async def test_auto_jump_no_rows_no_crash(test_user, async_client, db_session):
    """Element with no pattern pasted — page renders without error."""
    project = Project(user_id=test_user.id, name="Empty project")
    db_session.add(project)
    await db_session.commit()

    element = Element(project_id=project.id, name="Empty element", repeat_count=1)
    db_session.add(element)
    await db_session.commit()

    response = await async_client.get(f"/projects/{project.id}/elements/{element.id}")
    assert response.status_code == 200
    assert "No pattern pasted yet" in response.text

    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.execute(delete(Project).where(Project.id == project.id))
    await db_session.commit()


async def test_stepper_increase_seeds_reps_and_states(
    test_user, async_client, db_session, project_element_rows
):
    """1 → 3: reps 2-3 are created and every row gets a not_started state per rep."""
    project, element, rows = project_element_rows

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/repeat-count",
        data={"repeat_count": 3},
        follow_redirects=False,
    )

    assert response.status_code == 303
    await db_session.refresh(element)
    assert element.repeat_count == 3
    assert await _rep_count(db_session, element.id) == 3
    assert await _state_count(db_session, element.id) == 3 * len(rows)
    for rep_number in (2, 3):
        for row in rows:
            row_state = await _rep_row_state(db_session, element.id, rep_number, row.id)
            assert row_state.state == RowStateEnum.not_started
            # The bulk Core insert must still get the model's updated_at default.
            assert row_state.updated_at is not None


async def test_stepper_decrease_deletes_top_reps_and_their_states(
    test_user, async_client, db_session, project_element_rows
):
    """3 → 2: rep 3 and only its RowStates are deleted; reps 1-2 keep theirs."""
    project, element, rows = project_element_rows
    row = rows[0]

    await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/repeat-count",
        data={"repeat_count": 3},
        follow_redirects=False,
    )
    # Distinct mark so we can tell a surviving rep's progress is intact.
    await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/reps/1/rows/{row.id}/state",
        follow_redirects=False,
    )

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/repeat-count",
        data={"repeat_count": 2},
        follow_redirects=False,
    )

    assert response.status_code == 303
    await db_session.refresh(element)
    assert element.repeat_count == 2
    assert await _rep_count(db_session, element.id) == 2
    assert await _state_count(db_session, element.id) == 2 * len(rows)
    row_state = await _rep_row_state(db_session, element.id, 1, row.id)
    assert row_state.state == RowStateEnum.in_progress


async def test_stepper_increase_skips_existing_rep_numbers(
    test_user, async_client, db_session, project_element_rows
):
    """Post-race state: reps exist ahead of the field. An increase must derive its
    seed range from the actual reps (not element.repeat_count) so it never
    re-inserts an existing repetition number."""
    project, element, rows = project_element_rows

    # Simulate the post-race invariant break: reps 1-2 exist, field is still 1.
    extra_rep = ElementRepetition(element_id=element.id, repetition_number=2)
    db_session.add(extra_rep)
    await db_session.flush()
    db_session.add_all(
        RowState(element_repetition_id=extra_rep.id, row_id=row.id) for row in rows
    )
    await db_session.commit()

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/repeat-count",
        data={"repeat_count": 3},
        follow_redirects=False,
    )

    assert response.status_code == 303
    await db_session.refresh(element)
    assert element.repeat_count == 3
    assert await _rep_count(db_session, element.id) == 3
    assert await _state_count(db_session, element.id) == 3 * len(rows)


async def test_stepper_validation_error_rerenders_without_changes(
    test_user, async_client, db_session, project_element_rows
):
    project, element, rows = project_element_rows

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/repeat-count",
        data={"repeat_count": 0},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Repeat count must be between 1 and 99." in response.text
    await db_session.refresh(element)
    assert element.repeat_count == 1
    assert await _rep_count(db_session, element.id) == 1
    assert await _state_count(db_session, element.id) == len(rows)


async def test_stepper_no_rows_element_changes_field_only(
    test_user, async_client, db_session
):
    """No pattern saved: the stepper updates repeat_count without creating reps."""
    project = Project(user_id=test_user.id, name="Empty project")
    db_session.add(project)
    await db_session.commit()

    element = Element(project_id=project.id, name="Empty element", repeat_count=1)
    db_session.add(element)
    await db_session.commit()

    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/repeat-count",
        data={"repeat_count": 5},
        follow_redirects=False,
    )

    assert response.status_code == 303
    await db_session.refresh(element)
    assert element.repeat_count == 5
    assert await _rep_count(db_session, element.id) == 0

    await db_session.execute(delete(Element).where(Element.id == element.id))
    await db_session.execute(delete(Project).where(Project.id == project.id))
    await db_session.commit()


async def test_stepper_other_user_sees_404(
    test_user, second_user, db_session, project_element_rows
):
    _second_user, second_client = second_user
    project, element, rows = project_element_rows

    response = await second_client.post(
        f"/projects/{project.id}/elements/{element.id}/repeat-count",
        data={"repeat_count": 3},
        follow_redirects=False,
    )

    assert response.status_code == 404
    await db_session.refresh(element)
    assert element.repeat_count == 1
    assert await _rep_count(db_session, element.id) == 1


async def test_per_rep_toggle_isolation(
    test_user, async_client, db_session, project_element_rows
):
    """Toggling a row in rep 2 leaves rep 1's state for that row untouched."""
    project, element, rows = project_element_rows
    row = rows[0]

    await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/repeat-count",
        data={"repeat_count": 2},
        follow_redirects=False,
    )
    response = await async_client.post(
        f"/projects/{project.id}/elements/{element.id}/reps/2/rows/{row.id}/state",
        follow_redirects=False,
    )

    assert response.status_code == 200
    rep_2_state = await _rep_row_state(db_session, element.id, 2, row.id)
    assert rep_2_state.state == RowStateEnum.in_progress
    rep_1_state = await _rep_row_state(db_session, element.id, 1, row.id)
    assert rep_1_state.state == RowStateEnum.not_started


async def test_rep_resolution_query_param_cookie_and_404(
    test_user, async_client, db_session, project_element_rows
):
    """Explicit ?rep wins and is pinned to a cookie; a bare GET reads the cookie;
    out-of-range or non-integer ?rep is a bad URL and 404s."""
    project, element, rows = project_element_rows
    row = rows[0]
    element_url = f"/projects/{project.id}/elements/{element.id}"

    await async_client.post(
        f"{element_url}/repeat-count", data={"repeat_count": 2}, follow_redirects=False
    )
    # Differing mark: rep 2's row 1 goes in_progress, rep 1's stays not_started.
    await async_client.post(
        f"{element_url}/reps/2/rows/{row.id}/state", follow_redirects=False
    )

    # Bare GET with no cookie renders rep 1.
    response = await async_client.get(element_url)
    assert response.status_code == 200
    assert f"{element_url}/reps/1/rows/" in response.text
    assert "◐" not in response.text

    # Explicit ?rep=2 renders rep 2 and pins the cookie.
    response = await async_client.get(f"{element_url}?rep=2")
    assert response.status_code == 200
    assert f"{element_url}/reps/2/rows/" in response.text
    assert "◐" in response.text
    assert f"last_rep_{element.id}=2" in response.headers["set-cookie"]

    # A subsequent bare GET (client retains the cookie) still renders rep 2.
    response = await async_client.get(element_url)
    assert response.status_code == 200
    assert f"{element_url}/reps/2/rows/" in response.text
    assert "◐" in response.text

    # Bad URLs 404 — explicit params are never clamped.
    response = await async_client.get(f"{element_url}?rep=99")
    assert response.status_code == 404
    response = await async_client.get(f"{element_url}?rep=abc")
    assert response.status_code == 404


async def test_stale_rep_cookie_is_clamped_not_404(
    test_user, async_client, db_session, project_element_rows
):
    """Cookie points at rep 2, count drops to 1 — bare GET clamps to rep 1."""
    project, element, rows = project_element_rows
    element_url = f"/projects/{project.id}/elements/{element.id}"

    await async_client.post(
        f"{element_url}/repeat-count", data={"repeat_count": 2}, follow_redirects=False
    )
    response = await async_client.get(f"{element_url}?rep=2")
    assert response.status_code == 200

    await async_client.post(
        f"{element_url}/repeat-count", data={"repeat_count": 1}, follow_redirects=False
    )

    response = await async_client.get(element_url)
    assert response.status_code == 200
    assert f"{element_url}/reps/1/rows/" in response.text


async def test_auto_jump_is_per_rep(
    test_user, async_client, db_session, project_element_rows
):
    """Rep 1 all done has no current row; rep 2 with row 1 done jumps to row 2."""
    project, element, rows = project_element_rows
    element_url = f"/projects/{project.id}/elements/{element.id}"

    await async_client.post(
        f"{element_url}/repeat-count", data={"repeat_count": 2}, follow_redirects=False
    )
    # Rep 1: all rows done. Rep 2: only row 1 done.
    for row in rows:
        await async_client.post(
            f"{element_url}/reps/1/rows/{row.id}/state", follow_redirects=False
        )
        await async_client.post(
            f"{element_url}/reps/1/rows/{row.id}/state", follow_redirects=False
        )
    await async_client.post(
        f"{element_url}/reps/2/rows/{rows[0].id}/state", follow_redirects=False
    )
    await async_client.post(
        f"{element_url}/reps/2/rows/{rows[0].id}/state", follow_redirects=False
    )

    response = await async_client.get(f"{element_url}?rep=1")
    assert response.status_code == 200
    # No row is current (the trailing quote keeps the CSS rule from matching).
    assert 'row-item--current"' not in response.text

    response = await async_client.get(f"{element_url}?rep=2")
    assert response.status_code == 200
    second_row_marker = (
        f'<li id="row-{rows[1].id}" '
        'class="row-item row-item--not_started row-item--current">'
    )
    assert second_row_marker in response.text


async def test_stitch_set_persists_and_renders_in_fragment(
    test_user, async_client, db_session, project_element_rows
):
    """Set 14 on an in-progress row: DB updated and the swapped fragment re-renders
    the input with the value."""
    project, element, rows = project_element_rows
    row = rows[0]
    row_url = f"/projects/{project.id}/elements/{element.id}/reps/1/rows/{row.id}"

    # not_started -> in_progress so the stitch input renders.
    await async_client.post(f"{row_url}/state", follow_redirects=False)

    response = await async_client.post(
        f"{row_url}/stitch",
        data={"stitch_position": "14"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert 'value="14"' in response.text
    row_state = await _rep_row_state(db_session, element.id, 1, row.id)
    assert row_state.stitch_position == 14


async def test_stitch_blank_clears_position(
    test_user, async_client, db_session, project_element_rows
):
    project, element, rows = project_element_rows
    row = rows[0]
    row_url = f"/projects/{project.id}/elements/{element.id}/reps/1/rows/{row.id}"

    await async_client.post(f"{row_url}/state", follow_redirects=False)
    await async_client.post(
        f"{row_url}/stitch", data={"stitch_position": "14"}, follow_redirects=False
    )
    row_state = await _rep_row_state(db_session, element.id, 1, row.id)
    assert row_state.stitch_position == 14

    response = await async_client.post(
        f"{row_url}/stitch", data={"stitch_position": ""}, follow_redirects=False
    )

    assert response.status_code == 200
    row_state = await _rep_row_state(db_session, element.id, 1, row.id)
    assert row_state.stitch_position is None


@pytest.mark.parametrize("bad_value", ["abc", "0", "10000", "¹"])
async def test_stitch_invalid_input_renders_error_and_keeps_db_unchanged(
    test_user, async_client, db_session, project_element_rows, bad_value
):
    """Non-numeric / out-of-range input: 200 error fragment, no DB write."""
    project, element, rows = project_element_rows
    row = rows[0]
    row_url = f"/projects/{project.id}/elements/{element.id}/reps/1/rows/{row.id}"

    await async_client.post(f"{row_url}/state", follow_redirects=False)
    await async_client.post(
        f"{row_url}/stitch", data={"stitch_position": "14"}, follow_redirects=False
    )

    response = await async_client.post(
        f"{row_url}/stitch",
        data={"stitch_position": bad_value},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "row-item--error" in response.text
    # The field re-renders with the stored value, not the rejected garbage.
    assert 'value="14"' in response.text
    row_state = await _rep_row_state(db_session, element.id, 1, row.id)
    assert row_state.stitch_position == 14


async def test_stitch_survives_state_cycle(
    test_user, async_client, db_session, project_element_rows
):
    """The value persists across done -> not_started -> in_progress and the input
    re-renders with it on the full page."""
    project, element, rows = project_element_rows
    row = rows[0]
    row_url = f"/projects/{project.id}/elements/{element.id}/reps/1/rows/{row.id}"

    await async_client.post(f"{row_url}/state", follow_redirects=False)
    await async_client.post(
        f"{row_url}/stitch", data={"stitch_position": "14"}, follow_redirects=False
    )

    # in_progress -> done -> not_started -> in_progress
    for _ in range(3):
        await async_client.post(f"{row_url}/state", follow_redirects=False)

    row_state = await _rep_row_state(db_session, element.id, 1, row.id)
    assert row_state.state == RowStateEnum.in_progress
    assert row_state.stitch_position == 14

    response = await async_client.get(
        f"/projects/{project.id}/elements/{element.id}", follow_redirects=False
    )
    assert response.status_code == 200
    assert 'value="14"' in response.text


async def test_stitch_input_renders_only_for_in_progress_rows(
    test_user, async_client, db_session, project_element_rows
):
    """Full-page GET: the stitch input appears only on in-progress rows."""
    project, element, rows = project_element_rows
    row = rows[0]
    row_url = f"/projects/{project.id}/elements/{element.id}/reps/1/rows/{row.id}"

    await async_client.post(f"{row_url}/state", follow_redirects=False)

    response = await async_client.get(
        f"/projects/{project.id}/elements/{element.id}", follow_redirects=False
    )
    assert response.status_code == 200
    # Only row 1 is in-progress; the CSS selectors in the <style> block don't
    # contain `class="row-stitch"`, so this counts rendered labels only.
    assert response.text.count('class="row-stitch"') == 1
    # The input must carry a name so HTMX serializes its value on change — a
    # nameless input posts blank, silently clearing the stored position.
    assert 'name="stitch_position"' in response.text


async def test_stitch_other_user_sees_404(
    test_user, second_user, db_session, project_element_rows
):
    _second_user, second_client = second_user
    project, element, rows = project_element_rows
    row = rows[0]

    response = await second_client.post(
        f"/projects/{project.id}/elements/{element.id}/reps/1/rows/{row.id}/stitch",
        data={"stitch_position": "14"},
        follow_redirects=False,
    )

    assert response.status_code == 404

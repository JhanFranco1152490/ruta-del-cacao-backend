from apps.common.audit import record_update_events


def run(changed):
    recorded = []
    record_update_events(
        lambda **event: recorded.append(event),
        changed,
        updated="updated",
        status_changed="status_changed",
    )
    return recorded


def test_content_changes_leave_one_updated_event():
    assert run(["name", "details"]) == [
        {"action": "updated", "changed_fields": ["name", "details"]}
    ]


def test_a_status_change_leaves_its_own_event():
    assert run(["is_active"]) == [{"action": "status_changed", "changed_fields": ["is_active"]}]


def test_changing_both_leaves_two_events_and_the_status_is_not_in_the_content_one():
    assert run(["is_active", "name"]) == [
        {"action": "updated", "changed_fields": ["name"]},
        {"action": "status_changed", "changed_fields": ["is_active"]},
    ]


def test_no_changes_leave_no_events():
    assert run([]) == []

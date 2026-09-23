from agentposture.normalize import classify_tool_action, normalize_attributes, privilege_level


def test_aliases_map_to_vocabulary():
    a = normalize_attributes({"autonomy": "Human in the loop", "exposure": "internet",
                              "data": {"sensitivity": "secret", "types": "PII, Financial"},
                              "lifecycle": "prod", "owner": "Jane@Example.com"})
    assert a["autonomy"] == "act_with_approval"
    assert a["exposure"] == "public"
    assert a["data_sensitivity"] == "restricted"
    assert a["data_types"] == ["financial", "pii"]
    assert a["lifecycle"] == "production"
    assert a["owner"] == "jane@example.com"


def test_unknown_values_are_marked_not_dropped():
    assert normalize_attributes({"autonomy": "sometimes"})["autonomy"] == "unknown:sometimes"


def test_tool_actions_are_classified_from_names():
    assert classify_tool_action("issue_refund") == "irreversible"
    assert classify_tool_action("create_ticket") == "write"
    assert classify_tool_action("search_kb") == "read"
    assert classify_tool_action("delete_things", "read") == "read"  # declaration wins


def test_privilege_level_and_irreversible_are_derived():
    a = normalize_attributes({"tools": ["lookup", {"name": "wire_transfer"}]})
    assert a["irreversible_actions"] is True
    assert a["privilege_level"] == "write"
    assert privilege_level(["s3:*"], []) == "admin"
    assert privilege_level(["Microsoft Graph:Directory.ReadWrite.All"], []) == "admin"
    assert privilege_level(["orders:read"], []) == "read"


def test_tool_approval_feeds_controls():
    a = normalize_attributes({"tools": [{"name": "refund", "requires_approval": True}],
                              "controls": {"kill_switch": True}})
    assert a["controls"] == {"kill_switch": True, "human_approval": ["refund"]}

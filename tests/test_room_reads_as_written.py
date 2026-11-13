"""What a room prints from its orders: structure kept as written, the
criteria first, a palette name resolved, and no blank rows."""
from engine import cli, render


def _room(prefill, **kw):
    st = {"id": "r1", "assembly": "give-a-verdict", "open": True,
          "current": {"id": "verdict", "segment": "verdict"}, "measures": [],
          "row_returns": {}}
    form = {"imperative": "Answer your criteria.", "fields": []}
    return render.status(st, form, "REVIEW.verdict.toml", prefill=prefill, **kw)


def test_a_multi_line_order_keeps_its_lines_and_indentation():
    tree = "landed:\n  a(x) -> y\n    owns z\n  b() -- THIS GATE"
    room = _room({"call-tree": tree})
    assert "    call-tree\n      landed:\n        a(x) -> y\n          owns z\n        b() -- THIS GATE" in room


def test_a_one_line_order_still_wraps_beside_its_label():
    room = _room({"scope": "one line " * 30})
    first = next(line for line in room.splitlines() if line.strip().startswith("scope"))
    assert first.startswith("    scope  one line")
    wrapped = [line for line in room.splitlines() if "one line" in line]
    assert len(wrapped) > 1 and all(len(line) <= render.WIDTH for line in wrapped)


def test_a_blank_order_prints_no_row():
    room = _room({"budget": "", "model": None, "scope": "src/"})
    assert "budget" not in room and "model" not in room
    assert "scope" in room


def test_the_criteria_opens_the_room_ahead_of_the_orders():
    room = _room({"purpose": "p", "criteria": "break: try to make the purpose false"})
    assert room.index("your criteria") < room.index("your orders")
    assert "break: try to make the purpose false" in room
    orders = room[room.index("your orders"):]
    assert "criteria" not in orders.split("Answer your criteria.")[0]


def test_a_list_order_prints_one_item_a_line():
    lines = render.blocks([{"finding": "the fork does not diverge", "call": "blocking"},
                           {"finding": "second", "call": "accepted"}])
    assert lines[0].splitlines() == ["- finding: the fork does not diverge",
                                     "  call: blocking"]
    assert lines[1].startswith("- finding: second")


def test_a_palette_name_prints_with_the_command_it_runs_as(tmp_path):
    (tmp_path / "constellation.toml").write_text('[commands]\ntest = "python3 -m pytest -q"\n')
    prefill = {"proof": "palette:test tests/x.py", "gate-proof": "waived: none"}
    runs_as = cli._runs_as(prefill, tmp_path)
    assert runs_as == {"proof": "python3 -m pytest -q tests/x.py"}
    room = _room(prefill, runs_as=runs_as)
    assert "proof runs as  python3 -m pytest -q tests/x.py" in room


def test_a_palette_name_the_palette_lacks_prints_no_runs_as_row(tmp_path):
    (tmp_path / "constellation.toml").write_text('[commands]\ntest = "pytest"\n')
    assert cli._runs_as({"proof": "palette:nope"}, tmp_path) == {}

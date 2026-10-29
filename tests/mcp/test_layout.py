"""Wiring placement stays readable for branches, cycles, and existing layouts."""
import jsonpatch
import pytest
from fastapi import HTTPException

from wirecloud.mcp.layout import component_nodes, placement_patches
from wirecloud.mcp.schemas import WiringPlacement
from wirecloud.platform.wiring.schemas import Wiring, WiringBehaviour


def wiring(edges, components=None):
    ids = {key for edge in edges for key in edge}
    return Wiring.model_validate({"operators": {key: {"id": key, "name": "test/operator/1.0.0", "preferences": {}}
        for key in ids}, "connections": [{"source": {"type": "operator", "id": source, "endpoint": "output"},
            "target": {"type": "operator", "id": target, "endpoint": "input"}} for source, target in edges],
        "visualdescription": {"components": {"operator": components or {}}}})


def placed(status, heights=None, moves=(), preserve=True):
    valid = {("operator", key) for key in status.operators}
    nodes = component_nodes(status, valid, moves)
    patches = placement_patches(status, nodes, heights or {}, moves, preserve)
    result = Wiring.model_validate(jsonpatch.apply_patch(status.model_dump(), patches))
    return result, {key: component.position for key, component in result.visualdescription.components.operator.items()}


def test_branching_graph_flows_left_to_right_with_room_for_tall_components():
    status = wiring([("0", "1"), ("0", "2"), ("1", "3"), ("2", "3")])
    heights = {("operator", "1"): 1100}
    result, positions = placed(status, heights)
    assert positions["0"].x < positions["1"].x == positions["2"].x < positions["3"].x
    assert positions["2"].y >= positions["1"].y + 1100 + 40
    assert result.connections == status.connections
    assert placed(result, heights)[0] == result


def test_feedback_and_disconnected_graphs_are_deterministic_and_do_not_overlap():
    status = wiring([("0", "1"), ("1", "2"), ("2", "0"), ("3", "3"), ("4", "5")])
    first, positions = placed(status)
    reordered = status.model_copy(deep=True)
    reordered.connections.reverse()
    reordered.operators = dict(reversed(list(reordered.operators.items())))
    assert placed(reordered)[1] == positions
    assert len({(position.x, position.y) for position in positions.values()}) == len(positions)
    assert placed(first)[0] == first


def test_existing_positions_and_visual_metadata_survive_automatic_and_manual_moves():
    status = wiring([("0", "1"), ("0", "2")], {"0": {"position": {"x": 440, "y": 350},
        "collapsed": True, "endpoints": {"source": ["output"], "target": ["input"]}}})
    behaviour = WiringBehaviour.model_validate({"title": "Custom view", "description": "Preserve me",
        "components": {"operator": {"0": {"position": {"x": 700, "y": 900}}}}, "connections": []})
    status.visualdescription.behaviours.append(behaviour)
    automatic, positions = placed(status)
    assert positions["0"] == status.visualdescription.components.operator["0"].position
    moved, positions = placed(automatic, moves=[WiringPlacement(type="operator", id="1", x=900, y=800)])
    assert positions["1"].x == 900 and positions["1"].y == 800
    assert moved.visualdescription.components.operator["0"] == status.visualdescription.components.operator["0"]
    assert moved.operators == status.operators
    assert moved.connections == status.connections
    reflowed_status, reflowed = placed(moved, preserve=False)
    assert reflowed["0"].x < reflowed["1"].x == reflowed["2"].x
    assert reflowed_status.visualdescription.behaviours == [behaviour]


def test_missing_positions_avoid_existing_components_at_arbitrary_coordinates():
    status = wiring([("0", "1"), ("0", "2")], {"1": {"position": {"x": 410, "y": 125}}})
    _, positions = placed(status)
    assert positions["1"].x == 410 and positions["1"].y == 125
    assert positions["2"].y >= 125 + 240 + 40


def test_manual_moves_reject_missing_or_duplicate_components():
    status = wiring([("0", "1")])
    for moves, expected in [([WiringPlacement(type="operator", id="99", x=20, y=10)], 404),
        ([WiringPlacement(type="operator", id="0", x=20, y=10)] * 2, 422)]:
        with pytest.raises(HTTPException) as error:
            placed(status, moves=moves)
        assert error.value.status_code == expected

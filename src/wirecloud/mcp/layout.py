# -*- coding: utf-8 -*-
# Copyright (c) 2026 Future Internet Consulting and Development Solutions S.L.

# This file is part of Wirecloud.

# Wirecloud is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Wirecloud is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with Wirecloud.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import annotations

from heapq import heapify, heappop, heappush
from typing import Any, Collection, Mapping, Sequence

from fastapi import HTTPException

from wirecloud.mcp.schemas import WiringPlacement
from wirecloud.platform.wiring.schemas import Wiring, WiringConnection


def component_nodes(
    status: Wiring, valid_nodes: set[tuple[str, str]], moves: Sequence[WiringPlacement]
) -> set[tuple[str, str]]:
    """Include operators, displayed widgets, connected widgets, and explicit moves."""
    nodes = {("operator", key) for key in status.operators}
    nodes.update(
        (kind, key) for kind in ("widget", "operator") for key in getattr(status.visualdescription.components, kind)
    )
    nodes.update(
        (endpoint.type.value, endpoint.id)
        for connection in status.connections
        for endpoint in (connection.source, connection.target)
    )
    seen = set()
    for move in moves:
        node = (move.type, move.id)
        if node not in valid_nodes:
            raise HTTPException(404, "Wiring component not found")
        if node in seen:
            raise HTTPException(422, "Supply each component position only once")
        seen.add(node)
        nodes.add(node)
    return nodes & valid_nodes


def graph_layers(
    nodes: Collection[tuple[str, str]], connections: Sequence[WiringConnection]
) -> dict[tuple[str, str], int]:
    """Lay out acyclic edges left to right; break feedback cycles deterministically."""
    edges = {node: set() for node in nodes}
    incoming = dict.fromkeys(nodes, 0)
    for connection in connections:
        source = (connection.source.type.value, connection.source.id)
        target = (connection.target.type.value, connection.target.id)
        if source != target and source in nodes and target in nodes and target not in edges[source]:
            edges[source].add(target)
            incoming[target] += 1
    layers = dict.fromkeys(nodes, 0)
    pending = {node for node in nodes}
    ready = [node for node in nodes if incoming[node] == 0]
    heapify(ready)
    while pending:
        if not ready:
            heappush(ready, min(pending))
        source = heappop(ready)
        pending.remove(source)
        for target in sorted(edges[source] & pending):
            layers[target] = max(layers[target], layers[source] + 1)
            incoming[target] -= 1
            if incoming[target] == 0:
                heappush(ready, target)
    return layers


def placement_patches(
    status: Wiring,
    nodes: set[tuple[str, str]],
    heights: Mapping[tuple[str, str], int],
    moves: Sequence[WiringPlacement] = (),
    preserve_existing: bool = True,
) -> list[dict[str, Any]]:
    """Patch only positions, preserving collapsed state, endpoint order and other views."""
    components = status.visualdescription.components
    existing = {node: getattr(components, node[0]).get(node[1]) for node in nodes}
    manual = {(move.type, move.id): {"x": move.x, "y": move.y} for move in moves}
    placed = {
        node: component.position.model_dump()
        for node, component in existing.items()
        if preserve_existing and component is not None and component.position is not None
    }
    placed.update(manual)
    layers = graph_layers(nodes, status.connections)

    def height(node: tuple[str, str]) -> int:
        component = existing[node]
        return 90 if component is not None and component.collapsed else heights.get(node, 240)

    def placement_order(node: tuple[str, str]) -> tuple[int, tuple[str, str]]:
        return layers[node], node

    for node in sorted(nodes - placed.keys(), key=placement_order):
        # Reserve an initial column for widget sources when adding isolated operators.
        column = layers[node] + (1 if node[0] == "operator" and not status.connections else 0)
        x, y = 20 + column * 420, 10
        while True:
            blockers = [
                other
                for other, position in placed.items()
                if abs(position["x"] - x) < 380
                and y < position["y"] + height(other) + 40
                and position["y"] < y + height(node) + 40
            ]
            if not blockers:
                break
            y = max(placed[other]["y"] + height(other) + 40 for other in blockers)
        placed[node] = {"x": x, "y": y}

    patches = []
    for node in sorted(nodes):
        component = existing[node]
        position = placed[node]
        if component is not None and component.position is not None and component.position.model_dump() == position:
            continue
        kind, identifier = node
        escaped = identifier.replace("~", "~0").replace("/", "~1")
        path = f"/visualdescription/components/{kind}/{escaped}"
        patches.append(
            {
                "op": "add",
                "path": path + "/position" if component is not None else path,
                "value": position if component is not None else {"position": position},
            }
        )
    return patches

"""The map layout: ordered layers of nodes, and the wires drawn between nodes."""

from __future__ import annotations


def default_layout(lead: str, names: list[str]) -> dict:
    others = [n for n in names if n != lead]
    return {
        "layers": [{"id": "lead", "name": "Lead", "nodes": [lead]}, {"id": "team", "name": "Team", "nodes": others}],
        "edges": [{"from": lead, "to": n} for n in others],
    }


def build_layout(raw: dict | None, agents: list[dict], lead: str, source: str) -> dict:
    """Normalizes a layout sent by a team or saved by the user; every agent ends up on the map."""
    by_name = {a["name"]: a for a in agents}
    if not isinstance(raw, dict) or not isinstance(raw.get("layers"), list):
        raw, source = default_layout(lead, list(by_name)), "default"
    layers, placed = [], set()
    for i, layer in enumerate(raw["layers"]):
        if not isinstance(layer, dict):
            continue
        ids = [str(n) for n in layer.get("nodes", layer.get("agents", [])) if str(n) not in placed]
        placed.update(ids)
        layers.append({"id": str(layer.get("id") or f"layer-{i + 1}"), "name": str(layer.get("name") or f"Layer {i + 1}"), "nodes": ids})
    missing = [name for name in by_name if name not in placed]
    if missing:
        layers.append({"id": "unplaced", "name": "Other" if layers else "Team", "nodes": missing})
    raw_nodes = raw.get("nodes") if isinstance(raw.get("nodes"), dict) else {}
    nodes = {}
    for layer in layers:
        for node_id in layer["nodes"]:
            info = raw_nodes.get(node_id) if isinstance(raw_nodes.get(node_id), dict) else {}
            agent_name = info.get("agent", node_id if node_id in by_name else None)
            agent = by_name.get(agent_name, {})
            nodes[node_id] = {
                "agent": agent_name if agent_name in by_name else None,
                "title": info.get("title") or agent.get("title") or node_id,
                "subtitle": info.get("subtitle") or agent.get("assignment") or "",
            }
    edges = []
    for edge in raw.get("edges", []) if isinstance(raw.get("edges"), list) else []:
        if isinstance(edge, dict) and str(edge.get("from")) in nodes and str(edge.get("to")) in nodes:
            edges.append({"from": str(edge["from"]), "to": str(edge["to"])})
    return {"source": source, "layers": layers, "nodes": nodes, "edges": edges}

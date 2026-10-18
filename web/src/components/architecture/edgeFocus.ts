/**
 * Hover focus for the architecture canvases.
 *
 * Dense graphs (a lineage with dozens of links, a decomposition with several
 * components) are unreadable when every connector is drawn at full strength:
 * lines overlap, labels collide and it is impossible to tell which node a line
 * belongs to. Hovering a node or a connector therefore dims everything that is
 * not part of that connection.
 */

export type FocusableEdge = { id: string; source: string; target: string };

export type EdgeFocus = {
  /** Node ids to keep at full strength. */
  nodes: Set<string>;
  /** Edge ids to keep at full strength. */
  edges: Set<string>;
};

/**
 * The nodes and edges to emphasise while the pointer rests on a node or an edge,
 * or ``null`` when nothing is hovered (everything stays at full strength).
 */
export function edgeFocusSets(
  hoveredNodeId: string | null,
  hoveredEdgeId: string | null,
  edges: FocusableEdge[],
): EdgeFocus | null {
  if (!hoveredNodeId && !hoveredEdgeId) return null;
  const nodes = new Set<string>();
  const edgeIds = new Set<string>();
  if (hoveredEdgeId) {
    const hovered = edges.find((edge) => edge.id === hoveredEdgeId);
    if (hovered) {
      nodes.add(hovered.source);
      nodes.add(hovered.target);
      edgeIds.add(hovered.id);
    }
  }
  if (hoveredNodeId) {
    nodes.add(hoveredNodeId);
    for (const edge of edges) {
      if (edge.source === hoveredNodeId || edge.target === hoveredNodeId) {
        edgeIds.add(edge.id);
        nodes.add(edge.source);
        nodes.add(edge.target);
      }
    }
  }
  if (edgeIds.size === 0 && nodes.size === 0) return null;
  return { nodes, edges: edgeIds };
}

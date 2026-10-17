/**
 * Injects obstacle rectangles into edge data for obstacle-aware routing.
 *
 * Every architecture canvas is a React Flow instance whose custom edge types
 * route orthogonally around node boxes (see ``architectureRouting``). Rather
 * than repeat the geometry in each view, the shared canvas shell of every
 * discipline calls :func:`withEdgeObstacles` once, so connectors in the
 * enterprise, integration, solution and information views all agree.
 */

import {
  nodeRectMap,
  obstaclesForEdge,
  type RectLikeNode,
} from "./architectureRouting";

type EdgeLike = {
  source: string;
  target: string;
  data?: unknown;
};

/**
 * Returns a copy of ``edges`` whose ``data`` carries the routing geometry for
 * obstacle-aware paths: ``obstacles`` (the other node boxes) plus the
 * ``sourceRect``/``targetRect`` endpoint boxes. The rectangle map is computed
 * once per call so a view with many edges does not rescan the node list.
 */
export function withEdgeObstacles<
  NodeType extends RectLikeNode,
  EdgeType extends EdgeLike,
>(nodes: NodeType[], edges: EdgeType[]): EdgeType[] {
  if (edges.length === 0) return edges;
  const rects = nodeRectMap(nodes);
  return edges.map(
    (edge) =>
      ({
        ...edge,
        data: {
          ...(edge.data as Record<string, unknown> | undefined),
          obstacles: obstaclesForEdge(rects, edge.source, edge.target),
          sourceRect: rects.get(edge.source),
          targetRect: rects.get(edge.target),
        },
      }) as EdgeType,
  );
}

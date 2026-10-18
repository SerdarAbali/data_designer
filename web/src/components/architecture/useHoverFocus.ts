import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { edgeFocusSets, type EdgeFocus, type FocusableEdge } from "./edgeFocus";

export type HoverTarget = { node: string | null; edge: string | null };

const NO_TARGET: HoverTarget = { node: null, edge: null };

export type HoverFocus = {
  /** What to keep at full strength, or `null` when nothing is hovered. */
  focus: EdgeFocus | null;
  /** The element the focus has settled on (used to emphasise its own label). */
  target: HoverTarget;
  onNodeEnter: (node: { id: string }) => void;
  onEdgeEnter: (edge: { id: string }) => void;
  onLeave: () => void;
};

/**
 * Hover focus with intent.
 *
 * A raw enter/leave pair fires many times while the pointer sweeps across a
 * bundle of connectors or brushes a label, and because every event dims or
 * undims the whole canvas that reads as a flicker. The focus therefore only
 * engages once the pointer settles on an element and only clears once it settles
 * away from every element; moving straight onto another element cancels the
 * pending change instead of blanking the canvas in between.
 */
export function useHoverFocus(edgeList: FocusableEdge[], delay = 110): HoverFocus {
  const [target, setTarget] = useState<HoverTarget>(NO_TARGET);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const cancel = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const schedule = useCallback(
    (next: HoverTarget) => {
      cancel();
      timer.current = setTimeout(() => {
        timer.current = null;
        setTarget((prev) =>
          prev.node === next.node && prev.edge === next.edge ? prev : next,
        );
      }, delay);
    },
    [cancel, delay],
  );

  useEffect(() => cancel, [cancel]);

  const focus = useMemo(
    () => edgeFocusSets(target.node, target.edge, edgeList),
    [target, edgeList],
  );

  return {
    focus,
    target,
    onNodeEnter: useCallback(
      (node: { id: string }) => schedule({ node: node.id, edge: null }),
      [schedule],
    ),
    onEdgeEnter: useCallback(
      (edge: { id: string }) => schedule({ node: null, edge: edge.id }),
      [schedule],
    ),
    onLeave: useCallback(() => schedule(NO_TARGET), [schedule]),
  };
}

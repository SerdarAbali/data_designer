import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import type { TraceObjectRef } from "./workbenchTypes";

/**
 * A cross-workbench "reveal this object" request. Trace navigation uses it to
 * ask the destination workbench to select and reveal an object after the
 * discipline switch has happened. `nonce` distinguishes repeated requests for
 * the same object so a workbench can tell a fresh request from a stale one.
 */
export type WorkbenchFocus = {
  objectId: string;
  kind: string | null;
  discipline: string | null;
  nonce: number;
};

type NavigationValue = {
  focus: WorkbenchFocus | null;
  requestFocus: (node: TraceObjectRef) => void;
  clearFocus: (nonce: number) => void;
};

const WorkbenchNavigationContext = createContext<NavigationValue | null>(null);

const NOOP_NAVIGATION: NavigationValue = {
  focus: null,
  requestFocus: () => {},
  clearFocus: () => {},
};

export function WorkbenchNavigationProvider({ children }: { children: ReactNode }) {
  const [focus, setFocus] = useState<WorkbenchFocus | null>(null);
  const nonce = useRef(0);

  const requestFocus = useCallback((node: TraceObjectRef) => {
    nonce.current += 1;
    setFocus({
      objectId: node.id,
      kind: node.kind,
      discipline: node.discipline,
      nonce: nonce.current,
    });
  }, []);

  const clearFocus = useCallback((value: number) => {
    setFocus((current) => (current && current.nonce === value ? null : current));
  }, []);

  const contextValue = useMemo(
    () => ({ focus, requestFocus, clearFocus }),
    [focus, requestFocus, clearFocus],
  );

  return (
    <WorkbenchNavigationContext.Provider value={contextValue}>
      {children}
    </WorkbenchNavigationContext.Provider>
  );
}

export function useWorkbenchNavigation(): NavigationValue {
  return useContext(WorkbenchNavigationContext) ?? NOOP_NAVIGATION;
}

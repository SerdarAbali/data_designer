import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ArchitectureObject, ArchitectureState } from "../architectureTypes";
import { isEditableState, type CanonicalSystem } from "../architectureCanvasModel";
import { api, list } from "../apiClient";
import { ContextSaveQueue, type NavigationGuard } from "../contextSaveQueue";
import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";

export type GraphDocument = {
  nodes: { id: string; type: string }[];
  edges: { targetNodeId: string; targetPortId: string }[];
};

export type Integration = {
  id: string;
  name: string;
  source_system_id: string;
  target_system_id: string;
  target_object_id: string;
  graph: GraphDocument;
  sample_rows: unknown[];
  revision: number;
};

function activeStateStorageKey(workspaceId: string) {
  return `dd_active_state_id:${workspaceId}`;
}

function readStoredStateId(workspaceId: string): string {
  try {
    return sessionStorage.getItem(activeStateStorageKey(workspaceId)) ?? "";
  } catch {
    return "";
  }
}

type Options = {
  workspaceId: string;
  registerNavigationGuard?: (guard: NavigationGuard) => void;
};

/**
 * Shared workbench data layer: loads the canonical model (systems, architecture
 * objects, contracts, states), owns state selection, the serialized save queue,
 * and the navigation guard that lets a workbench block navigation until pending
 * writes settle. Extracted from `ArchitectureCanvas` so every discipline can
 * reuse the same behaviour.
 */
export function useArchitectureModel({ workspaceId, registerNavigationGuard }: Options) {
  const [systems, setSystems] = useState<CanonicalSystem[]>([]);
  const [architectureObjects, setArchitectureObjects] = useState<ArchitectureObject[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [states, setStates] = useState<ArchitectureState[]>([]);
  const [activeStateId, setActiveStateId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");

  const statesRef = useRef(states);
  statesRef.current = states;
  const saveQueue = useRef(new ContextSaveQueue());
  const loadSequence = useRef(0);
  const mounted = useRef(true);
  const dirtyStates = useRef(new Set<string>());

  const waitForSaves = useCallback(async () => {
    try {
      await saveQueue.current.flush();
      return true;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Resolve the failed save before switching.");
      return false;
    }
  }, []);

  useEffect(() => {
    registerNavigationGuard?.(waitForSaves);
    mounted.current = true;
    return () => {
      mounted.current = false;
      ++loadSequence.current;
      registerNavigationGuard?.(async () => true);
    };
  }, [registerNavigationGuard, waitForSaves]);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    const requestId = ++loadSequence.current;
    setLoading(true);
    setError("");
    try {
      const [nextSystems, nextIntegrations, nextStates, nextArchitectureObjects] = await Promise.all([
        list<CanonicalSystem>("/api/catalog/systems"),
        list<Integration>("/api/integrations"),
        api<ArchitectureState[]>(`/api/workspaces/${workspaceId}/states`),
        api<ArchitectureObject[]>(`/api/workspaces/${workspaceId}/architecture-objects`),
      ]);
      if (requestId !== loadSequence.current) return;
      setSystems(nextSystems);
      setArchitectureObjects(nextArchitectureObjects);
      setIntegrations(nextIntegrations);
      setStates(nextStates);
      setActiveStateId((previous) => {
        const preferred = previous || readStoredStateId(workspaceId);
        if (preferred && nextStates.some((state) => state.id === preferred)) return preferred;
        return (nextStates.find((state) => state.state_type === "current") ?? nextStates[0])?.id ?? "";
      });
    } catch (caught) {
      if (requestId === loadSequence.current) {
        setError(caught instanceof Error ? caught.message : "Could not load the architecture canvas.");
      }
    } finally {
      if (requestId === loadSequence.current) setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    setStates([]);
    setActiveStateId("");
    setSaveStatus("idle");
    setSystems([]);
    setArchitectureObjects([]);
    setIntegrations([]);
    void load();
    return () => {
      ++loadSequence.current;
    };
  }, [load]);

  useEffect(() => {
    if (!workspaceId || !activeStateId) return;
    try {
      sessionStorage.setItem(activeStateStorageKey(workspaceId), activeStateId);
    } catch {
      /* storage unavailable */
    }
  }, [workspaceId, activeStateId]);

  const commit = useCallback(
    (next: ArchitectureState) => {
      if (!workspaceId) return;
      statesRef.current = statesRef.current.map((state) => (state.id === next.id ? next : state));
      setStates((previous) => previous.map((state) => (state.id === next.id ? next : state)));
      setSaveStatus("saving");
      // Saves are serialized so the last edit always wins on the server.
      dirtyStates.current.add(next.id);
      void saveQueue.current
        .enqueue(next.id, async () => {
          const latest = statesRef.current.find((state) => state.id === next.id) ?? next;
          const saved = await api<ArchitectureState>(
            `/api/workspaces/${workspaceId}/states/${next.id}`,
            {
              method: "PUT",
              body: JSON.stringify({ nodes: latest.nodes, relationships: latest.relationships }),
            },
          );
          dirtyStates.current.delete(next.id);
          if (!mounted.current) return;
          setStates((previous) =>
            previous.map((state) =>
              state.id === saved.id ? { ...state, updated_at: saved.updated_at } : state,
            ),
          );
        })
        .then(async () => {
          await saveQueue.current.flush();
          if (mounted.current) {
            setSaveStatus("saved");
            setError("");
          }
        })
        .catch((caught: unknown) => {
          if (mounted.current) {
            setSaveStatus("error");
            setError(
              caught instanceof Error ? caught.message : "Could not save the architecture state.",
            );
          }
        });
    },
    [workspaceId],
  );

  const mutateActive = useCallback(
    (mutate: (state: ArchitectureState) => ArchitectureState) => {
      const state = statesRef.current.find((item) => item.id === activeStateId);
      if (!state) return;
      commit(mutate(state));
    },
    [activeStateId, commit],
  );

  const adoptState = useCallback((next: ArchitectureState) => {
    statesRef.current = statesRef.current.map((state) => (state.id === next.id ? next : state));
    setStates((previous) => previous.map((state) => (state.id === next.id ? next : state)));
    setSaveStatus("saved");
  }, []);

  const activeState = states.find((state) => state.id === activeStateId) ?? null;
  const currentState = states.find((state) => state.state_type === "current") ?? null;
  const editable = isEditableState(activeState);

  const systemsById = useMemo(
    () => new Map(systems.map((system) => [system.id, system])),
    [systems],
  );
  const architectureObjectsById = useMemo(
    () => new Map(architectureObjects.map((object) => [object.id, object])),
    [architectureObjects],
  );
  const integrationsById = useMemo(
    () => new Map(integrations.map((integration) => [integration.id, integration])),
    [integrations],
  );

  return {
    workspaceId,
    systems,
    setSystems,
    architectureObjects,
    setArchitectureObjects,
    integrations,
    setIntegrations,
    states,
    statesRef,
    setStates,
    activeStateId,
    setActiveStateId,
    loading,
    setLoading,
    error,
    setError,
    saveStatus,
    setSaveStatus,
    saveQueue,
    dirtyStates,
    activeState,
    currentState,
    editable,
    systemsById,
    architectureObjectsById,
    integrationsById,
    load,
    waitForSaves,
    commit,
    adoptState,
    mutateActive,
  };
}

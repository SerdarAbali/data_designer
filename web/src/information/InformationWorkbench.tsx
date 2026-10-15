import { useCallback, useEffect, useMemo, useState } from "react";

import type { ArchitectureState } from "../architectureTypes";
import { moveOccurrence } from "../architectureCanvasModel";
import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import ObjectTracePanel from "../components/architecture/ObjectTracePanel";
import type { TraceObjectRef } from "../workbench/workbenchTypes";
import { useWorkbenchNavigation } from "../workbench/WorkbenchNavigation";
import AttributeEditorPanel from "./AttributeEditorPanel";
import EntityEditorPanel, { type AttributeDraft } from "./EntityEditorPanel";
import InformationERCanvas from "./InformationERCanvas";
import RelationshipEditorPanel from "./RelationshipEditorPanel";
import {
  createInformationAttribute,
  createInformationEntity,
  createInformationRelationship,
  deleteInformationAttribute,
  deleteInformationRelationship,
  fetchInformationModel,
  setInformationRealization,
  updateInformationAttribute,
  updateInformationEntity,
  updateInformationRelationship,
  type InformationCardinality,
  type InformationModel,
} from "./informationModel";

type Props = {
  workspaceId: string;
  activeState: ArchitectureState | null;
  editable: boolean;
  saveStatus: SaveStatus;
  search?: string;
  onAdoptState: (state: ArchitectureState) => void;
  mutateActive: (mutate: (state: ArchitectureState) => ArchitectureState) => void;
  onOpenCatalog: () => void;
  onNavigateTrace?: (node: TraceObjectRef) => void;
};

export default function InformationWorkbench({
  workspaceId,
  activeState,
  editable,
  saveStatus,
  search = "",
  onAdoptState,
  mutateActive,
  onOpenCatalog,
  onNavigateTrace,
}: Props) {
  const [model, setModel] = useState<InformationModel | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const [selectedObjectId, setSelectedObjectId] = useState<string | null>(null);
  const [selectedAttributeId, setSelectedAttributeId] = useState<string | null>(null);
  const [selectedRelationshipId, setSelectedRelationshipId] = useState<string | null>(null);
  const [pendingCardinality, setPendingCardinality] = useState<InformationCardinality>("one_to_many");

  const stateId = activeState?.id ?? "";
  const { focus, clearFocus } = useWorkbenchNavigation();

  const reload = useCallback(async () => {
    if (!workspaceId || !stateId) {
      setModel(null);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const next = await fetchInformationModel(workspaceId, stateId);
      setModel(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load the information model.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, stateId]);

  useEffect(() => {
    setSelectedObjectId(null);
    setSelectedAttributeId(null);
    setSelectedRelationshipId(null);
    void reload();
  }, [reload]);

  const run = useCallback(async (operation: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await operation();
      await reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The change could not be saved.");
    } finally {
      setBusy(false);
    }
  }, [reload]);

  const visibleModel = useMemo(() => {
    if (!model) return null;
    const term = search.trim().toLowerCase();
    if (!term) return model;
    return {
      ...model,
      entities: model.entities.filter((entity) => entity.name.toLowerCase().includes(term)),
    };
  }, [model, search]);

  const selectedEntity = model?.entities.find((entity) => entity.object_id === selectedObjectId) ?? null;
  const selectedAttribute = selectedEntity?.attributes.find(
    (attribute) => attribute.object_id === selectedAttributeId,
  ) ?? null;
  const selectedRelationship = model?.relationships.find(
    (relationship) => relationship.id === selectedRelationshipId,
  ) ?? null;
  const relationshipSource = selectedRelationship
    ? model?.entities.find((entity) => entity.object_id === selectedRelationship.source_object_id)
    : null;
  const relationshipTarget = selectedRelationship
    ? model?.entities.find((entity) => entity.object_id === selectedRelationship.target_object_id)
    : null;

  // Trace navigation: select an entity (or the entity owning an attribute).
  useEffect(() => {
    if (!focus || focus.discipline !== "information" || !model) return;
    const entity =
      focus.kind === "information_attribute"
        ? model.entities.find((item) =>
            item.attributes.some((attribute) => attribute.object_id === focus.objectId),
          ) ?? null
        : model.entities.find((item) => item.object_id === focus.objectId) ?? null;
    if (entity) {
      setSelectedObjectId(entity.object_id);
      setSelectedAttributeId(focus.kind === "information_attribute" ? focus.objectId : null);
      setSelectedRelationshipId(null);
      setInspectorCollapsed(false);
    }
    clearFocus(focus.nonce);
  }, [focus, model, clearFocus]);

  function nextEntityPosition() {
    const entities = model?.entities ?? [];
    if (entities.length === 0) return { x: 80, y: 80 };
    const maxX = Math.max(...entities.map((entity) => entity.position.x));
    const minY = Math.min(...entities.map((entity) => entity.position.y));
    return { x: maxX + 280, y: minY };
  }

  async function handleCreateEntity() {
    if (!stateId) return;
    await run(async () => {
      const created = await createInformationEntity(workspaceId, {
        state_id: stateId,
        name: "New entity",
        position: nextEntityPosition(),
      });
      onAdoptState(created.state);
      setSelectedObjectId(created.entity.object_id);
      setSelectedAttributeId(null);
      setSelectedRelationshipId(null);
      setInspectorCollapsed(false);
    });
  }

  return (
    <div className={`information-workbench${!inspectorCollapsed && (selectedEntity || selectedRelationship) ? " has-panel" : ""}`}>
      <div className="information-toolbar">
        <button type="button" className="studio-add-menu" disabled={!editable || busy || !stateId} onClick={() => void handleCreateEntity()}>
          + New entity
        </button>
        <span className="information-toolbar-hint">
          {editable ? "Drag between entity handles to create a relationship." : "Current state is read-only. Duplicate it to model changes."}
        </span>
        <button type="button" className="secondary-button" onClick={onOpenCatalog}>Open catalog</button>
      </div>

      {error && (
        <div className="studio-canvas-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError("")} aria-label="Dismiss error">×</button>
        </div>
      )}

      {loading && !model ? (
        <div className="landscape-empty" role="status">Loading information model…</div>
      ) : (
        <div className="information-canvas-host">
          {visibleModel && (
            <InformationERCanvas
              model={visibleModel}
              editable={editable}
              selectedEntityId={
                selectedEntity?.occurrence_id ?? null
              }
              selectedAttributeId={selectedAttributeId}
              selectedRelationshipId={selectedRelationshipId}
              pendingCardinality={pendingCardinality}
              onSelectEntity={(occurrenceId) => {
                const entity = model?.entities.find((item) => item.occurrence_id === occurrenceId);
                setSelectedObjectId(entity?.object_id ?? null);
                setSelectedAttributeId(null);
                setSelectedRelationshipId(null);
                setInspectorCollapsed(false);
              }}
              onSelectAttribute={(attributeId) => {
                setSelectedAttributeId(attributeId);
                setSelectedRelationshipId(null);
                setInspectorCollapsed(false);
              }}
              onSelectRelationship={(relationshipId) => {
                setSelectedRelationshipId(relationshipId);
                setSelectedAttributeId(null);
                setSelectedObjectId(null);
                setInspectorCollapsed(false);
              }}
              onPaneClick={() => {
                setSelectedObjectId(null);
                setSelectedAttributeId(null);
                setSelectedRelationshipId(null);
              }}
              onConnect={(sourceObjectId, targetObjectId) => {
                if (!stateId) return;
                void run(async () => {
                  await createInformationRelationship(workspaceId, {
                    state_id: stateId,
                    source_object_id: sourceObjectId,
                    target_object_id: targetObjectId,
                    cardinality: pendingCardinality,
                  });
                });
              }}
              onMoveEntity={(occurrenceId, position) => {
                setModel((current) => current ? {
                  ...current,
                  entities: current.entities.map((entity) =>
                    entity.occurrence_id === occurrenceId ? { ...entity, position } : entity),
                } : current);
                mutateActive((state) => moveOccurrence(state, occurrenceId, position));
              }}
              onPendingCardinalityChange={setPendingCardinality}
            />
          )}

          {model && model.entities.length === 0 && (
            <div className="information-empty-overlay">
              <h3>No entities in this state yet</h3>
              <p>{editable ? "Create your first entity to start the information model." : "Duplicate the current state into a candidate to add entities."}</p>
              {editable && <button type="button" onClick={() => void handleCreateEntity()}>+ New entity</button>}
            </div>
          )}

          {inspectorCollapsed && (selectedEntity || selectedRelationship) && (
            <button type="button" className="studio-reopen-inspector" onClick={() => setInspectorCollapsed(false)}>Open inspector</button>
          )}

          {!inspectorCollapsed && selectedEntity && selectedAttribute && (
            <AttributeEditorPanel
              key={selectedAttribute.object_id}
              entityName={selectedEntity.name}
              attribute={selectedAttribute}
              editable={editable}
              stateId={stateId}
              stateName={activeState?.name ?? ""}
              saveStatus={saveStatus}
              busy={busy}
              onChange={(attributeId, patch) => void run(() =>
                updateInformationAttribute(workspaceId, attributeId, { ...patch, state_id: stateId }))}
              onDelete={(attributeId) => {
                if (!window.confirm("Delete this attribute?")) return;
                void run(async () => {
                  await deleteInformationAttribute(workspaceId, attributeId, stateId);
                  setSelectedAttributeId(null);
                });
              }}
              onRealize={(attributeId, fieldId) => void run(() =>
                setInformationRealization(workspaceId, attributeId, { state_id: stateId, catalog_field_id: fieldId }))}
              onClose={() => { setSelectedEntityIdNull(); }}
              onBack={() => setSelectedAttributeId(null)}
              onCollapse={() => setInspectorCollapsed(true)}
            />
          )}

          {!inspectorCollapsed && selectedEntity && !selectedAttribute && (
            <EntityEditorPanel
              key={selectedEntity.object_id}
              entity={selectedEntity}
              editable={editable}
              stateName={activeState?.name ?? ""}
              saveStatus={saveStatus}
              busy={busy}
              onSave={(entityId, patch) => void run(() => updateInformationEntity(workspaceId, entityId, patch))}
              onSelectAttribute={(attributeId) => { setSelectedAttributeId(attributeId); setInspectorCollapsed(false); }}
              onAddAttribute={(draft: AttributeDraft) => void run(() =>
                createInformationAttribute(workspaceId, selectedEntity.object_id, { ...draft, state_id: stateId }))}
              onClose={() => setSelectedObjectId(null)}
              onCollapse={() => setInspectorCollapsed(true)}
            />
          )}

          {!inspectorCollapsed && selectedRelationship && (
            <RelationshipEditorPanel
              key={selectedRelationship.id}
              relationship={selectedRelationship}
              sourceLabel={relationshipSource?.name ?? "Entity"}
              targetLabel={relationshipTarget?.name ?? "Entity"}
              editable={editable}
              stateName={activeState?.name ?? ""}
              saveStatus={saveStatus}
              busy={busy}
              onChange={(relationshipId, patch) => void run(() =>
                updateInformationRelationship(workspaceId, relationshipId, stateId, patch))}
              onDelete={(relationshipId) => {
                if (!window.confirm("Delete this relationship?")) return;
                void run(async () => {
                  await deleteInformationRelationship(workspaceId, relationshipId, stateId);
                  setSelectedRelationshipId(null);
                });
              }}
              onClose={() => setSelectedRelationshipId(null)}
              onCollapse={() => setInspectorCollapsed(true)}
            />
          )}

          {!inspectorCollapsed && (selectedAttribute || selectedEntity) && (
            <ObjectTracePanel
              workspaceId={workspaceId}
              stateId={stateId || null}
              objectId={selectedAttribute?.object_id ?? selectedEntity?.object_id ?? null}
              onNavigate={onNavigateTrace}
            />
          )}
        </div>
      )}
    </div>
  );

  function setSelectedEntityIdNull() {
    setSelectedObjectId(null);
    setSelectedAttributeId(null);
  }
}

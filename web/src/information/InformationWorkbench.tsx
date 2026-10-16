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
  fetchInformationConceptual,
  fetchInformationImpact,
  fetchInformationLineage,
  fetchInformationModel,
  fetchInformationOwnership,
  fetchInformationPhysical,
  setInformationRealization,
  updateInformationAttribute,
  updateInformationEntity,
  updateInformationRelationship,
  arrangeEntities,
  type InformationCardinality,
  type InformationConceptual,
  type InformationImpact,
  type InformationImpactChange,
  type InformationLineage,
  type InformationLineageNode,
  type InformationModel,
  type InformationOwnership,
  type InformationPhysical,
} from "./informationModel";
import { INFORMATION_VIEWS, type InformationViewId } from "./informationViews";
import ConceptualModelView from "./visual/ConceptualModelView";
import InformationImpactView from "./visual/InformationImpactView";
import InformationLineageView from "./visual/InformationLineageView";
import OwnershipAuthorityView from "./visual/OwnershipAuthorityView";
import PhysicalRealizationView from "./visual/PhysicalRealizationView";

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

  // Logical Model stays the default; the other views are additive projections.
  const [view, setView] = useState<InformationViewId>("logical");
  const [attributeFilter, setAttributeFilter] = useState("");
  const [unmappedOnly, setUnmappedOnly] = useState(false);
  const [projectionLoading, setProjectionLoading] = useState(false);
  const [conceptual, setConceptual] = useState<InformationConceptual | null>(null);
  const [physical, setPhysical] = useState<InformationPhysical | null>(null);
  const [ownership, setOwnership] = useState<InformationOwnership | null>(null);
  const [lineage, setLineage] = useState<InformationLineage | null>(null);
  const [impact, setImpact] = useState<InformationImpact | null>(null);
  const [selectedLineageNodeId, setSelectedLineageNodeId] = useState<string | null>(null);

  const stateId = activeState?.id ?? "";
  const { focus, clearFocus } = useWorkbenchNavigation();

  const reloadModel = useCallback(async () => {
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

  const reloadProjection = useCallback(async () => {
    if (!workspaceId || !stateId || view === "logical") return;
    setProjectionLoading(true);
    setError("");
    try {
      if (view === "conceptual") setConceptual(await fetchInformationConceptual(workspaceId, stateId));
      else if (view === "physical") setPhysical(await fetchInformationPhysical(workspaceId, stateId));
      else if (view === "ownership") setOwnership(await fetchInformationOwnership(workspaceId, stateId));
      else if (view === "lineage") setLineage(await fetchInformationLineage(workspaceId, stateId));
      else if (view === "impact") setImpact(await fetchInformationImpact(workspaceId, stateId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load this information view.");
    } finally {
      setProjectionLoading(false);
    }
  }, [workspaceId, stateId, view]);

  useEffect(() => {
    setSelectedObjectId(null);
    setSelectedAttributeId(null);
    setSelectedRelationshipId(null);
    void reloadModel();
  }, [reloadModel]);

  useEffect(() => {
    setSelectedLineageNodeId(null);
    void reloadProjection();
  }, [reloadProjection]);

  const run = useCallback(async (operation: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await operation();
      await reloadModel();
      await reloadProjection();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The change could not be saved.");
    } finally {
      setBusy(false);
    }
  }, [reloadModel, reloadProjection]);

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

  const openContract = useCallback(
    (contractId: string) => {
      onNavigateTrace?.({
        id: contractId,
        kind: "integration",
        name: "Contract",
        description: null,
        discipline: "integration",
        state_membership: "none",
        external: false,
      });
    },
    [onNavigateTrace],
  );

  function nextEntityPosition() {
    const entities = model?.entities ?? [];
    if (entities.length === 0) return { x: 80, y: 80 };
    const maxX = Math.max(...entities.map((entity) => entity.position.x));
    const minY = Math.min(...entities.map((entity) => entity.position.y));
    return { x: maxX + 280, y: minY };
  }

  function handleArrange(direction: "ltr" | "ttb") {
    if (!model || !editable) return;
    const positions = arrangeEntities(model.entities, model.relationships, direction);
    if (positions.size === 0) return;
    setModel((current) => current ? {
      ...current,
      entities: current.entities.map((entity) => {
        const position = positions.get(entity.occurrence_id);
        return position ? { ...entity, position } : entity;
      }),
    } : current);
    mutateActive((state) => {
      let next = state;
      for (const [occurrenceId, position] of positions) {
        next = moveOccurrence(next, occurrenceId, position);
      }
      return next;
    });
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

  function selectEntityByObjectId(objectId: string) {
    setSelectedObjectId(objectId);
    setSelectedAttributeId(null);
    setSelectedRelationshipId(null);
    setInspectorCollapsed(false);
  }

  function selectAttributeByObjectId(attributeObjectId: string) {
    const owner = model?.entities.find((entity) =>
      entity.attributes.some((attribute) => attribute.object_id === attributeObjectId),
    );
    if (!owner) return;
    setSelectedObjectId(owner.object_id);
    setSelectedAttributeId(attributeObjectId);
    setSelectedRelationshipId(null);
    setInspectorCollapsed(false);
  }

  function selectLineageNode(node: InformationLineageNode | null) {
    setSelectedLineageNodeId(node?.id ?? null);
    if (!node) return;
    if (node.kind === "information_attribute") {
      selectAttributeByObjectId(node.id.replace(/^attribute:/, ""));
    } else if (node.kind === "information_entity") {
      selectEntityByObjectId(node.id.replace(/^entity:/, ""));
    }
  }

  function selectImpactChange(change: InformationImpactChange) {
    if (!change.entity_object_id) return;
    if (change.object_type === "attribute") {
      selectAttributeByObjectId(change.object_id);
    } else {
      selectEntityByObjectId(change.entity_object_id);
    }
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

      <div className="information-body">
        <nav className="information-views" aria-label="Information views">
          {INFORMATION_VIEWS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={view === item.id ? "active" : ""}
              aria-current={view === item.id ? "page" : undefined}
              title={item.description}
              onClick={() => setView(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>

        <div className="information-content">
          {loading && !model ? (
            <div className="landscape-empty" role="status">Loading information model…</div>
          ) : (
            <div className="information-canvas-host">
              {view === "logical" && visibleModel && (
                <InformationERCanvas
                  model={visibleModel}
                  editable={editable}
                  selectedEntityId={
                    selectedEntity?.occurrence_id ?? null
                  }
                  selectedAttributeId={selectedAttributeId}
                  selectedRelationshipId={selectedRelationshipId}
                  pendingCardinality={pendingCardinality}
                  attributeFilter={attributeFilter}
                  onAttributeFilterChange={setAttributeFilter}
                  unmappedOnly={unmappedOnly}
                  onUnmappedOnlyChange={setUnmappedOnly}
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
                  onConnect={(sourceObjectId, targetObjectId, sourceHandle, targetHandle) => {
                    if (!stateId) return;
                    void run(async () => {
                      await createInformationRelationship(workspaceId, {
                        state_id: stateId,
                        source_object_id: sourceObjectId,
                        target_object_id: targetObjectId,
                        cardinality: pendingCardinality,
                        source_handle: sourceHandle,
                        target_handle: targetHandle,
                      });
                    });
                  }}
                  onReconnectRelationship={({ relationshipId, sourceObjectId, targetObjectId, sourceHandle, targetHandle }) => {
                    if (!stateId) return;
                    void run(() => updateInformationRelationship(workspaceId, relationshipId, stateId, {
                      source_object_id: sourceObjectId,
                      target_object_id: targetObjectId,
                      source_handle: sourceHandle,
                      target_handle: targetHandle,
                    }));
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
                  onArrange={handleArrange}
                />
              )}

              {view === "conceptual" && conceptual && (
                <ConceptualModelView
                  conceptual={conceptual}
                  stateId={stateId}
                  selectedObjectId={selectedObjectId}
                  onSelectConcept={selectEntityByObjectId}
                />
              )}

              {view === "physical" && physical && (
                <PhysicalRealizationView
                  physical={physical}
                  onSelectAttribute={(_entityId, attributeId) => selectAttributeByObjectId(attributeId)}
                  onOpenCatalog={onOpenCatalog}
                  onOpenContract={openContract}
                />
              )}

              {view === "ownership" && ownership && (
                <OwnershipAuthorityView
                  ownership={ownership}
                  selectedObjectId={selectedObjectId}
                  onSelectEntity={selectEntityByObjectId}
                />
              )}

              {view === "lineage" && lineage && (
                <InformationLineageView
                  lineage={lineage}
                  selectedNodeId={selectedLineageNodeId}
                  onSelectNode={selectLineageNode}
                  onOpenCatalog={onOpenCatalog}
                  onOpenContract={openContract}
                />
              )}

              {view === "impact" && impact && (
                <InformationImpactView
                  impact={impact}
                  selectedObjectId={selectedObjectId}
                  onSelectChange={selectImpactChange}
                />
              )}

              {view !== "logical" && projectionLoading && (
                <div className="landscape-empty" role="status">Loading view…</div>
              )}

              {view === "logical" && model && model.entities.length === 0 && (
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
                  relationships={
                    <section className="information-relationships-section">
                      {(!model?.relationships.some((item) =>
                        item.source_object_id === selectedEntity.object_id
                        || item.target_object_id === selectedEntity.object_id)) ? (
                        <p className="muted">This entity has no relationships yet.</p>
                      ) : (
                        <ul className="information-attribute-editor-list">
                          {model?.relationships
                            .filter((item) =>
                              item.source_object_id === selectedEntity.object_id
                              || item.target_object_id === selectedEntity.object_id)
                            .map((item) => {
                              const other = item.source_object_id === selectedEntity.object_id
                                ? item.target_object_id
                                : item.source_object_id;
                              const otherName = model?.entities.find((entity) => entity.object_id === other)?.name
                                ?? "Entity";
                              const outgoing = item.source_object_id === selectedEntity.object_id;
                              return (
                                <li key={item.id}>
                                  <button type="button" onClick={() => setSelectedRelationshipId(item.id)}>
                                    <span>{outgoing ? "→" : "←"} {otherName}</span>
                                    <small>{item.name || item.cardinality.replace(/_/g, " ")}</small>
                                  </button>
                                </li>
                              );
                            })}
                        </ul>
                      )}
                    </section>
                  }
                  trace={(
                    <ObjectTracePanel
                      workspaceId={workspaceId}
                      stateId={stateId || null}
                      objectId={selectedEntity.object_id}
                      onNavigate={onNavigateTrace}
                    />
                  )}
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
            </div>
          )}
        </div>
      </div>
    </div>
  );

  function setSelectedEntityIdNull() {
    setSelectedObjectId(null);
    setSelectedAttributeId(null);
  }
}

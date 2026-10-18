import { useEffect, useState, type ReactNode } from "react";

import { architectureFactLabel } from "../architectureFacts";
import EvidencePanel from "../components/architecture/EvidencePanel";
import UnifiedInspector from "../components/inspector/UnifiedInspector";
import { IMPLEMENTATION_STATUS_LABELS, type ImplementationStatus } from "../integration/integrationDesignModel";
import {
  contractRoleSummary,
  nodeWarnings,
  relationshipLabel,
  warningLabel,
} from "./solutionLandscapeModel";
import {
  deleteSolutionRelationship,
  SOLUTION_CONTRACT_ROLE_LABELS,
  SOLUTION_RELATIONSHIP_LABELS,
  SOLUTION_RELATIONSHIP_TYPES,
  updateSolutionRelationship,
  type SolutionLandscape,
  type SolutionLandscapeNode,
  type SolutionRelationshipType,
} from "./solutionModel";

type Props = {
  landscape: SolutionLandscape;
  workspaceId: string;
  stateId: string;
  stateName: string;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  busy: boolean;
  onSelectNode: (solutionObjectId: string) => void;
  onSelectEdge: (relationshipId: string) => void;
  onOpenSolution: (solutionObjectId: string) => void;
  onOpenContract: (contractId: string) => void;
  onChanged: () => void;
  onClose: () => void;
  onCollapse: () => void;
  trace?: ReactNode;
};

function factLabel(value: string | null): string {
  return architectureFactLabel(value);
}

function implementationLabel(value: string | null): string {
  if (!value) return "Unavailable";
  return IMPLEMENTATION_STATUS_LABELS[value as ImplementationStatus] ?? value;
}

/**
 * The Solution Landscape inspector. A node shows ownership, membership,
 * Contract associations by role and both relationship directions; an edge shows
 * the relationship detail with edit and remove controls when writable.
 */
export default function SolutionLandscapeInspector({
  landscape,
  workspaceId,
  stateId,
  stateName,
  selectedNodeId,
  selectedEdgeId,
  busy,
  onSelectNode,
  onSelectEdge,
  onOpenSolution,
  onOpenContract,
  onChanged,
  onClose,
  onCollapse,
  trace,
}: Props) {
  const node: SolutionLandscapeNode | null =
    landscape.solutions.find((item) => item.solution_object_id === selectedNodeId) ?? null;
  const edge =
    landscape.relationships.find((item) => item.id === selectedEdgeId) ?? null;

  const [role, setRole] = useState<SolutionRelationshipType>("depends_on");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setRole(edge?.relationship_type ?? "depends_on");
    setDescription(edge?.description ?? "");
    setError("");
  }, [edge?.id, edge?.relationship_type, edge?.description]);

  if (edge) {
    const source = landscape.solutions.find(
      (item) => item.solution_object_id === edge.source_object_id,
    );
    const target = landscape.solutions.find(
      (item) => item.solution_object_id === edge.target_object_id,
    );
    const writable = landscape.editable && edge.state_applicability === "state";

    async function save() {
      setSaving(true);
      setError("");
      try {
        await updateSolutionRelationship(workspaceId, edge!.id, stateId, {
          relationship_type: role,
          description: description.trim() ? description.trim() : null,
        });
        onChanged();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Could not save the relationship.");
      } finally {
        setSaving(false);
      }
    }

    async function remove() {
      if (!window.confirm("Remove this relationship? Both Solutions are kept.")) return;
      setError("");
      try {
        await deleteSolutionRelationship(workspaceId, edge!.id, stateId);
        onChanged();
        onSelectEdge("");
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "Could not remove the relationship.");
      }
    }

    const properties = (
      <>
        <section className="inspector-section">
          <h4 className="inspector-section-title">Relationship</h4>
          <p className="solution-landscape-relationship-flow">
            <span>{source?.name ?? edge.source_object_id}</span>
            <span aria-hidden="true">→</span>
            <span>{target?.name ?? edge.target_object_id}</span>
          </p>
          <dl className="solution-contract-facts">
            <div>
              <dt>Type</dt>
              <dd>{relationshipLabel(edge.relationship_type)}</dd>
            </div>
            <div>
              <dt>Applies to</dt>
              <dd>
                {edge.state_applicability === "canonical"
                  ? "All states (canonical)"
                  : edge.state_name
                    ? `${edge.state_name} state`
                    : "State-scoped"}
              </dd>
            </div>
            <div>
              <dt>Evidence</dt>
              <dd>{edge.evidence_count}</dd>
            </div>
            <div>
              <dt>Description</dt>
              <dd>{edge.description ?? "—"}</dd>
            </div>
          </dl>
        </section>
        {!writable && (
          <p className="architecture-topbar-hint">
            {landscape.editable
              ? "A canonical relationship belongs to every state and cannot be changed here."
              : "This architecture state is read-only, so the relationship cannot be changed."}
          </p>
        )}
        {writable && (
          <section className="inspector-section">
            <h4 className="inspector-section-title">Edit</h4>
            <label className="inspector-field-label">
              Relationship type
              <select
                aria-label="Relationship type"
                value={role}
                disabled={busy || saving}
                onChange={(event) => setRole(event.target.value as SolutionRelationshipType)}
              >
                {SOLUTION_RELATIONSHIP_TYPES.map((value) => (
                  <option key={value} value={value}>
                    {SOLUTION_RELATIONSHIP_LABELS[value]}
                  </option>
                ))}
              </select>
            </label>
            <label className="inspector-field-label">
              Description
              <textarea
                aria-label="Relationship description"
                value={description}
                maxLength={500}
                rows={2}
                disabled={busy || saving}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <div className="solution-panel-actions">
              <button type="button" disabled={busy || saving} onClick={() => void save()}>
                {saving ? "Saving…" : "Save relationship"}
              </button>
              <button
                type="button"
                className="secondary-button solution-contract-danger"
                disabled={busy || saving}
                onClick={() => void remove()}
              >
                Remove relationship
              </button>
            </div>
          </section>
        )}
      </>
    );

    return (
      <UnifiedInspector
        ariaLabel="Solution relationship"
        eyebrow="SOLUTION RELATIONSHIP"
        title={relationshipLabel(edge.relationship_type)}
        identifier={edge.id}
        stateName={stateName}
        status={landscape.editable ? "Editable" : "Read-only"}
        collapseLabel="Collapse relationship inspector"
        closeLabel="Close relationship inspector"
        onCollapse={onCollapse}
        onClose={onClose}
        panels={[
          { id: "properties", label: "Properties", content: properties },
          {
            id: "evidence",
            label: "Evidence",
            count: edge.evidence_count,
            content: (
              <EvidencePanel
                workspaceId={workspaceId}
                stateId={stateId}
                targetKind="architecture_relationship"
                targetId={edge.id}
                readOnly={!landscape.editable}
              />
            ),
          },
        ]}
      />
    );
  }

  if (!node) {
    return (
      <UnifiedInspector
        ariaLabel="Solution landscape"
        eyebrow="SOLUTION LANDSCAPE"
        title="Portfolio"
        stateName={stateName}
        status={landscape.editable ? "Editable" : "Read-only"}
        collapseLabel="Collapse landscape inspector"
        closeLabel="Close landscape inspector"
        onCollapse={onCollapse}
        onClose={onClose}
        panels={[
          {
            id: "summary",
            label: "Summary",
            content: (
              <section className="inspector-section">
                <h4 className="inspector-section-title">Landscape</h4>
                <dl className="solution-contract-facts">
                  <div>
                    <dt>Solutions</dt>
                    <dd>{landscape.solutions.length}</dd>
                  </div>
                  <div>
                    <dt>Relationships</dt>
                    <dd>{landscape.relationships.length}</dd>
                  </div>
                </dl>
                <p className="architecture-topbar-hint">
                  Select a solution to inspect its ownership, membership and Contract
                  associations. Select a relationship to inspect its direction and description.
                </p>
              </section>
            ),
          },
        ]}
      />
    );
  }

  const incoming = landscape.relationships.filter(
    (item) => item.target_object_id === node.solution_object_id,
  );
  const outgoing = landscape.relationships.filter(
    (item) => item.source_object_id === node.solution_object_id,
  );
  const warnings = nodeWarnings(landscape, node.solution_object_id);

  const properties = (
    <>
      <section className="inspector-section">
        <h4 className="inspector-section-title">Properties</h4>
        <dl className="solution-contract-facts">
          <div>
            <dt>Owner</dt>
            <dd>{node.owner && node.owner.length > 0 ? node.owner : "Unspecified"}</dd>
          </div>
          <div>
            <dt>Lifecycle</dt>
            <dd>{factLabel(node.lifecycle_stage)}</dd>
          </div>
          <div>
            <dt>Operational status</dt>
            <dd>{factLabel(node.operational_status)}</dd>
          </div>
          <div>
            <dt>Components</dt>
            <dd>{node.component_count}</dd>
          </div>
          <div>
            <dt>Member systems</dt>
            <dd>{node.member_count}</dd>
          </div>
          <div>
            <dt>External systems</dt>
            <dd>{node.external_system_count}</dd>
          </div>
          <div>
            <dt>Evidence</dt>
            <dd>{node.evidence_count}</dd>
          </div>
        </dl>
        {node.description && <p className="inspector-field-help">{node.description}</p>}
        {warnings.length > 0 && (
          <ul className="solution-landscape-warnings">
            {warnings.map((warning) => (
              <li key={`${warning.code}:${warning.association_id ?? ""}`}>
                {warningLabel(warning.code)} — {warning.message}
              </li>
            ))}
          </ul>
        )}
        <div className="solution-panel-actions">
          <button type="button" onClick={() => onOpenSolution(node.solution_object_id)}>
            Open in Context
          </button>
        </div>
      </section>
    </>
  );

  const membership = (
    <section className="inspector-section">
      <div className="information-section-heading">
        <strong>Member systems</strong>
        <span className="item-count">{node.members.length}</span>
      </div>
      {node.members.length === 0 ? (
        <p className="architecture-topbar-hint">No member systems.</p>
      ) : (
        <ul className="solution-member-list">
          {node.members.map((member) => (
            <li key={member.system_id}>
              <span>{member.name}</span>
              <small>{member.kind}</small>
            </li>
          ))}
        </ul>
      )}
      <div className="solution-external">
        <strong>External participating systems</strong>
        {node.external_systems.length === 0 ? (
          <p className="architecture-topbar-hint">No external systems on the canvas.</p>
        ) : (
          <ul>
            {node.external_systems.map((system) => (
              <li key={system.system_id}>{system.name}</li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );

  const contracts = (
    <section className="inspector-section">
      <div className="information-section-heading">
        <strong>Contracts</strong>
        <span className="item-count">{node.contract_counts.total}</span>
      </div>
      <p className="architecture-topbar-hint">{contractRoleSummary(node)}</p>
      {node.contracts.length === 0 ? (
        <p className="architecture-topbar-hint">
          No Contracts are associated with this solution.
        </p>
      ) : (
        <ul className="solution-contract-list">
          {node.contracts.map((association) => (
            <li key={association.association_id} className="solution-contract-item">
              <div className="solution-contract-head">
                <strong>{association.contract_name ?? association.contract_id}</strong>
                <span className={`solution-contract-role role-${association.role}`}>
                  {SOLUTION_CONTRACT_ROLE_LABELS[association.role]}
                </span>
              </div>
              {!association.available && (
                <p className="solution-landscape-warnings">
                  Unavailable — the Contract is archived.
                </p>
              )}
              {association.available && (
                <dl className="solution-contract-facts">
                  <div>
                    <dt>Lifecycle</dt>
                    <dd>{factLabel(association.lifecycle_stage.value)}</dd>
                  </div>
                  <div>
                    <dt>Operational</dt>
                    <dd>{factLabel(association.operational_status.value)}</dd>
                  </div>
                  <div>
                    <dt>Implementation</dt>
                    <dd>{implementationLabel(association.implementation_status)}</dd>
                  </div>
                  <div>
                    <dt>Evidence</dt>
                    <dd>{association.evidence_count}</dd>
                  </div>
                </dl>
              )}
              {association.description && (
                <p className="solution-contract-description">{association.description}</p>
              )}
              {association.available && (
                <div className="solution-contract-actions">
                  <button type="button" onClick={() => onOpenContract(association.contract_id)}>
                    Open in Integration Architecture
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );

  const relationships = (
    <section className="inspector-section">
      <div className="information-section-heading">
        <strong>Solution relationships</strong>
        <span className="item-count">{incoming.length + outgoing.length}</span>
      </div>
      {incoming.length + outgoing.length === 0 ? (
        <p className="architecture-topbar-hint">No relationships yet.</p>
      ) : (
        <ul className="solution-landscape-relationship-list">
          {incoming.map((item) => (
            <li key={`in-${item.id}`}>
              <button type="button" onClick={() => onSelectEdge(item.id)}>
                <span className="solution-landscape-direction">Incoming</span>
                {landscape.solutions.find(
                  (candidate) => candidate.solution_object_id === item.source_object_id,
                )?.name ?? item.source_object_id}
                <em> {relationshipLabel(item.relationship_type)}</em>
              </button>
            </li>
          ))}
          {outgoing.map((item) => (
            <li key={`out-${item.id}`}>
              <button type="button" onClick={() => onSelectEdge(item.id)}>
                <span className="solution-landscape-direction">Outgoing</span>
                {landscape.solutions.find(
                  (candidate) => candidate.solution_object_id === item.target_object_id,
                )?.name ?? item.target_object_id}
                <em> {relationshipLabel(item.relationship_type)}</em>
              </button>
            </li>
          ))}
        </ul>
      )}
      <button type="button" className="secondary-button" onClick={() => onSelectNode("")}>
        Select another solution
      </button>
    </section>
  );

  return (
    <UnifiedInspector
      ariaLabel="Solution landscape solution"
      eyebrow="SOLUTION"
      title={node.name}
      identifier={node.solution_object_id}
      stateName={stateName}
      status={landscape.editable ? "Editable" : "Read-only"}
      collapseLabel="Collapse solution inspector"
      closeLabel="Close solution inspector"
      onCollapse={onCollapse}
      onClose={onClose}
      panels={[
        { id: "properties", label: "Properties", content: properties },
        { id: "membership", label: "Membership", count: node.members.length, content: membership },
        {
          id: "contracts",
          label: "Contracts",
          count: node.contract_counts.total,
          content: contracts,
        },
        {
          id: "relationships",
          label: "Relationships",
          count: incoming.length + outgoing.length,
          content: relationships,
        },
        {
          id: "evidence",
          label: "Evidence",
          count: node.evidence_count,
          content: (
            <EvidencePanel
              workspaceId={workspaceId}
              stateId={stateId}
              targetKind="architecture_object"
              targetId={node.solution_object_id}
              readOnly={!landscape.editable}
            />
          ),
        },
        {
          id: "traceability",
          label: "Traceability",
          content: trace ?? <p className="muted">Traceability is unavailable.</p>,
        },
      ]}
    />
  );
}

import { useState, type FormEvent, type ReactNode } from "react";

import type { SaveStatus } from "../components/architecture/ArchitectureTopBar";
import UnifiedInspector from "../components/inspector/UnifiedInspector";
import {
  ENTERPRISE_LABELS,
  ENTERPRISE_LINK_RULES,
  ENTERPRISE_LINK_TYPES,
  ENTERPRISE_PRINCIPLE_TYPES,
  ENTERPRISE_PROCESS_TYPES,
  ENTERPRISE_ROLE_TYPES,
  endpointName,
  endpointsFor,
  type EnterpriseLinkType,
  type EnterpriseModel,
  type EnterpriseObject,
} from "./enterpriseModel";

type Props = {
  object: EnterpriseObject;
  model: EnterpriseModel;
  editable: boolean;
  stateName: string;
  saveStatus: SaveStatus;
  busy: boolean;
  onSave: (objectId: string, patch: Record<string, unknown>) => void;
  onDelete: (objectId: string) => void;
  onCreateLink: (
    relationshipType: EnterpriseLinkType,
    sourceObjectId: string,
    targetObjectId: string,
  ) => void;
  onDeleteLink: (linkId: string) => void;
  onSelectObject: (objectId: string) => void;
  onClose: () => void;
  onCollapse: () => void;
  trace?: ReactNode;
};

export default function EnterpriseObjectPanel({
  object,
  model,
  editable,
  stateName,
  saveStatus,
  busy,
  onSave,
  onDelete,
  onCreateLink,
  onDeleteLink,
  onSelectObject,
  onClose,
  onCollapse,
  trace,
}: Props) {
  const [name, setName] = useState(object.name);
  const [description, setDescription] = useState(object.description ?? "");
  const [owner, setOwner] = useState(object.owner ?? "");
  const [outcomeMetric, setOutcomeMetric] = useState(object.outcome_metric ?? "");
  const [horizon, setHorizon] = useState(object.horizon ?? "");
  const [processType, setProcessType] = useState(object.process_type ?? "");
  const [principleType, setPrincipleType] = useState(object.principle_type ?? "");
  const [rationale, setRationale] = useState(object.rationale ?? "");
  const [roleType, setRoleType] = useState(object.role_type ?? "");

  const [linkType, setLinkType] = useState<EnterpriseLinkType>("drives");
  const [linkDirection, setLinkDirection] = useState<"outgoing" | "incoming">("outgoing");
  const [linkPartner, setLinkPartner] = useState("");

  const dirty =
    name !== object.name ||
    description !== (object.description ?? "") ||
    owner !== (object.owner ?? "") ||
    outcomeMetric !== (object.outcome_metric ?? "") ||
    horizon !== (object.horizon ?? "") ||
    processType !== (object.process_type ?? "") ||
    principleType !== (object.principle_type ?? "") ||
    rationale !== (object.rationale ?? "") ||
    roleType !== (object.role_type ?? "");

  const connections = model.links.filter(
    (link) =>
      link.source_object_id === object.object_id || link.target_object_id === object.object_id,
  );

  const rule = ENTERPRISE_LINK_RULES[linkType];
  const endpoints = endpointsFor(
    model,
    linkDirection === "outgoing" ? rule.targets : rule.sources,
  ).filter((endpoint) => endpoint.id !== object.object_id);

  const applicableLinkTypes = ENTERPRISE_LINK_TYPES.filter((type) => {
    const candidate = ENTERPRISE_LINK_RULES[type];
    return (
      candidate.sources.includes(object.kind) ||
      candidate.targets.includes(object.kind)
    );
  });

  function submitLink(event: FormEvent) {
    event.preventDefault();
    if (!linkPartner) return;
    if (linkDirection === "outgoing") {
      if (!ENTERPRISE_LINK_RULES[linkType].sources.includes(object.kind)) return;
      onCreateLink(linkType, object.object_id, linkPartner);
    } else {
      if (!ENTERPRISE_LINK_RULES[linkType].targets.includes(object.kind)) return;
      onCreateLink(linkType, linkPartner, object.object_id);
    }
    setLinkPartner("");
  }

  function save() {
    const patch: Record<string, unknown> = { name, description };
    if (object.kind === "goal") {
      patch.owner = owner;
      patch.outcome_metric = outcomeMetric;
      patch.horizon = horizon;
    }
    if (object.kind === "process") {
      patch.owner = owner;
      patch.process_type = processType || null;
    }
    if (object.kind === "principle") {
      patch.principle_type = principleType || null;
      patch.rationale = rationale;
    }
    if (object.kind === "role") {
      patch.role_type = roleType || null;
    }
    onSave(object.object_id, patch);
  }

  const properties = (
    <>
      <label>
        Name
        <input value={name} disabled={!editable} onChange={(event) => setName(event.target.value)} />
      </label>
      <label>
        Description
        <textarea
          value={description}
          disabled={!editable}
          onChange={(event) => setDescription(event.target.value)}
        />
      </label>

      {object.kind === "goal" && (
        <>
          <label>
            Owner
            <input value={owner} disabled={!editable} onChange={(event) => setOwner(event.target.value)} />
          </label>
          <label>
            Outcome metric
            <input
              value={outcomeMetric}
              disabled={!editable}
              onChange={(event) => setOutcomeMetric(event.target.value)}
            />
          </label>
          <label>
            Horizon
            <input value={horizon} disabled={!editable} onChange={(event) => setHorizon(event.target.value)} />
          </label>
        </>
      )}

      {object.kind === "process" && (
        <>
          <label>
            Process type
            <select
              value={processType}
              disabled={!editable}
              onChange={(event) => setProcessType(event.target.value)}
            >
              <option value="">Unspecified</option>
              {ENTERPRISE_PROCESS_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type === "value_stream" ? "value stream" : type}
                </option>
              ))}
            </select>
          </label>
          <label>
            Owner
            <input value={owner} disabled={!editable} onChange={(event) => setOwner(event.target.value)} />
          </label>
        </>
      )}

      {object.kind === "principle" && (
        <>
          <label>
            Principle type
            <select
              value={principleType}
              disabled={!editable}
              onChange={(event) => setPrincipleType(event.target.value)}
            >
              <option value="">Unspecified</option>
              {ENTERPRISE_PRINCIPLE_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </label>
          <label>
            Rationale
            <textarea
              value={rationale}
              disabled={!editable}
              onChange={(event) => setRationale(event.target.value)}
            />
          </label>
        </>
      )}

      {object.kind === "role" && (
        <label>
          Role type
          <select
            value={roleType}
            disabled={!editable}
            onChange={(event) => setRoleType(event.target.value)}
          >
            <option value="">Unspecified</option>
            {ENTERPRISE_ROLE_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
      )}

      {editable && (
        <div className="solution-panel-actions">
          <button type="button" disabled={!dirty || busy || !name.trim()} onClick={save}>
            {busy ? "Saving…" : "Save object"}
          </button>
          <button
            type="button"
            className="secondary-button architecture-danger"
            onClick={() => onDelete(object.object_id)}
          >
            Delete
          </button>
        </div>
      )}
    </>
  );

  const relationshipsPanel = (
    <section className="enterprise-links-section">
      <div className="information-section-heading">
        <strong>Relationships</strong>
        <span className="item-count">{connections.length}</span>
      </div>
      {connections.length === 0 ? (
        <p className="architecture-topbar-hint">No typed dependencies yet.</p>
      ) : (
        <ul className="enterprise-link-list">
          {connections.map((link) => {
            const outgoing = link.source_object_id === object.object_id;
            const partnerId = outgoing ? link.target_object_id : link.source_object_id;
            return (
              <li key={link.id}>
                <button
                  type="button"
                  className="enterprise-link-endpoint"
                  onClick={() => onSelectObject(partnerId)}
                >
                  {endpointName(model, partnerId)}
                </button>
                <span className="enterprise-link-verb">
                  {outgoing ? "→" : "←"} {ENTERPRISE_LABELS[link.relationship_type] ?? link.relationship_type}
                </span>
                {editable && (
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => onDeleteLink(link.id)}
                  >
                    Remove
                  </button>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {editable && applicableLinkTypes.length > 0 && (
        <form className="enterprise-link-form" onSubmit={submitLink}>
          <p className="studio-menu-caption">New relationship</p>
          <label>
            Type
            <select
              value={linkType}
              onChange={(event) => {
                setLinkType(event.target.value as EnterpriseLinkType);
                setLinkPartner("");
              }}
            >
              {applicableLinkTypes.map((type) => (
                <option key={type} value={type}>
                  {ENTERPRISE_LABELS[type] ?? type}
                </option>
              ))}
            </select>
          </label>
          <label>
            Direction
            <select
              value={
                ENTERPRISE_LINK_RULES[linkType].sources.includes(object.kind) ? linkDirection : "incoming"
              }
              onChange={(event) => {
                setLinkDirection(event.target.value as "outgoing" | "incoming");
                setLinkPartner("");
              }}
            >
              {ENTERPRISE_LINK_RULES[linkType].sources.includes(object.kind) && (
                <option value="outgoing">This object is the source</option>
              )}
              {ENTERPRISE_LINK_RULES[linkType].targets.includes(object.kind) && (
                <option value="incoming">This object is the target</option>
              )}
            </select>
          </label>
          <label>
            Other object
            <select value={linkPartner} onChange={(event) => setLinkPartner(event.target.value)}>
              <option value="">Select…</option>
              {endpoints.map((endpoint) => (
                <option key={endpoint.id} value={endpoint.id}>
                  {endpoint.name} · {ENTERPRISE_LABELS[endpoint.kind] ?? endpoint.kind}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={busy || !linkPartner}>
            Add relationship
          </button>
        </form>
      )}
    </section>
  );

  return (
    <UnifiedInspector
      ariaLabel="Enterprise object details"
      eyebrow={ENTERPRISE_LABELS[object.kind]?.toUpperCase() ?? "ENTERPRISE"}
      title={object.name}
      identifier={object.object_id}
      stateName={stateName}
      status={editable ? "Editable" : "Read-only"}
      saveStatus={saveStatus}
      collapseLabel="Collapse object inspector"
      closeLabel="Close object details"
      onCollapse={onCollapse}
      onClose={onClose}
      panels={[
        { id: "properties", label: "Properties", content: properties },
        { id: "relationships", label: "Relationships", count: connections.length, content: relationshipsPanel },
        { id: "traceability", label: "Traceability", content: trace ?? <p className="muted">Traceability is unavailable.</p> },
      ]}
    />
  );
}

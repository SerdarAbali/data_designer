import React from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";

export type LandscapeField = {
  id: string;
  objectId: string;
  objectLabel: string;
  name: string;
  dataType: string;
  sourceConnected: boolean;
  targetConnected: boolean;
};

export type SystemLandscapeNodeData = {
  systemId: string;
  label: string;
  kind: string;
  color: string;
  icon: string;
  objectCount: number;
  integrationCount: number;
  incomingContractCount: number;
  outgoingContractCount: number;
  validationIssueContractCount: number;
  fields: LandscapeField[];
  expanded: boolean;
  showFields?: boolean;
  compact?: boolean;
  selected?: boolean;
  dimmed?: boolean;
  onToggleExpanded: (systemId: string) => void;
  onSelectSystem?: (systemId: string) => void;
  onAddIntegration: (systemId: string) => void;
  onOpenCatalog: () => void;
};

export type SystemLandscapeNode = import("@xyflow/react").Node<
  SystemLandscapeNodeData,
  "system"
>;

export default function SystemLandscapeNodeCard({
  data,
}: NodeProps<SystemLandscapeNode>) {
  return (
    <article
      className={`landscape-system-card${data.expanded ? " expanded" : ""}${data.compact ? " compact" : ""}${data.showFields !== false ? " legacy-hybrid" : ""}${data.selected ? " focused" : ""}${data.dimmed ? " dimmed" : ""}`}
      aria-label={`${data.label}, ${data.kind || "System"}`}
      role="group"
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          data.onSelectSystem?.(data.systemId);
        }
      }}
    >
      <Handle
        type="target"
        position={Position.Left}
        id="system-in"
        className="landscape-system-handle"
      />
      <Handle
        type="source"
        position={Position.Right}
        id="system-out"
        className="landscape-system-handle"
      />
      <div className="landscape-system-content">
        <header className="landscape-system-heading">
          <span className="landscape-system-marker" style={{ backgroundColor: data.color }}>
            {data.icon || data.label.slice(0, 1).toUpperCase()}
          </span>
          <div className="landscape-system-copy">
            <strong>{data.label}</strong>
          </div>
          {data.showFields !== false && (
            <button
              type="button"
              className="landscape-expand-button nodrag nopan"
              aria-label={`${data.expanded ? "Collapse" : "Expand"} ${data.label} fields`}
              aria-expanded={data.expanded}
              onClick={(event) => {
                event.stopPropagation();
                data.onToggleExpanded(data.systemId);
              }}
            >
              <span aria-hidden="true">{data.expanded ? "⌃" : "⌄"}</span>
            </button>
          )}
        </header>
        <div className="landscape-system-subheading">
          <small>{data.kind || "System"}</small>
          {!data.compact && (
            <span>
              {data.objectCount} {data.objectCount === 1 ? "object" : "objects"}
              {" · "}
              {data.integrationCount} {data.integrationCount === 1 ? "contract" : "contracts"}
            </span>
          )}
        </div>
        {data.compact && (
          <div className="landscape-system-metrics" aria-label="System contract counts">
            <span>{data.objectCount} {data.objectCount === 1 ? "object" : "objects"}</span>
            <span>
              {data.incomingContractCount} incoming {data.incomingContractCount === 1 ? "contract" : "contracts"}
            </span>
            <span>
              {data.outgoingContractCount} outgoing {data.outgoingContractCount === 1 ? "contract" : "contracts"}
            </span>
            <span className={data.validationIssueContractCount ? "has-issues" : ""}>
              {data.validationIssueContractCount} {data.validationIssueContractCount === 1 ? "issue" : "issues"}
            </span>
          </div>
        )}
        {data.showFields !== false && data.expanded && (
          <div className="landscape-field-list">
            {!data.fields.length ? (
              <span className="landscape-no-fields">No mapped fields</span>
            ) : data.fields.map((field) => (
              <div className="landscape-field-row" key={`${field.objectId}:${field.id}`}>
                {field.targetConnected && (
                  <Handle
                    type="target"
                    position={Position.Left}
                    id={`in:${field.objectId}:${field.id}`}
                    className="landscape-field-target-handle active"
                  />
                )}
                <span className="landscape-field-name" title={`${field.objectLabel} · ${field.name}`}>
                  {field.name}
                </span>
                <span className="landscape-field-type">{field.dataType}</span>
                {field.sourceConnected && (
                  <Handle
                    type="source"
                    position={Position.Right}
                    id={`out:${field.objectId}:${field.id}`}
                    className="landscape-field-source-handle active"
                  />
                )}
              </div>
            ))}
          </div>
        )}
        {data.showFields !== false && (
          <footer className="landscape-node-actions nodrag nopan">
            <button type="button" onClick={() => data.onAddIntegration(data.systemId)}>+ Add Contract</button>
            <button type="button" onClick={data.onOpenCatalog}>View Catalog</button>
          </footer>
        )}
      </div>
    </article>
  );
}

import React from "react";
import { Handle, Position, type Node } from "@xyflow/react";
import type { CatalogField } from "./types";

export type SystemNodeData = {
  label: string;
  systemId?: string;
  objectId?: string;
  fields?: CatalogField[];
  isSource?: boolean;
  isTarget?: boolean;
};

type SystemNodeProps = {
  id: string;
  data: SystemNodeData;
  selected?: boolean;
  isConnectable?: boolean;
  sourcePosition?: Position;
  targetPosition?: Position;
};

export default function SystemNodeCard({
  id,
  data,
  selected,
}: SystemNodeProps) {
  const isSource = data.isSource;
  const isTarget = data.isTarget;

  return (
    <div
      className={`system-node-card${selected ? " selected" : ""}`}
      style={{
        background: "white",
        border: selected ? "2px solid #2563eb" : "1px solid #d1d5db",
        borderRadius: "8px",
        padding: "12px",
        minWidth: "200px",
        maxWidth: "280px",
        boxShadow: selected ? "0 0 0 3px rgba(37, 99, 235, 0.1)" : "0 1px 2px rgba(0,0,0,0.05)",
      }}
    >
      {/* Left side: Inbound return handles (Right to Left) */}
      {isTarget && (
        <>
          <Handle
            type="target"
            position={Position.Left}
            id="return-input"
            className="flow-handle"
            style={{
              background: "#10b981",
              top: "25%",
            }}
            title="Inbound Response Connection"
          />
          <Handle
            type="target"
            position={Position.Left}
            id="return-input-secondary"
            className="flow-handle"
            style={{
              background: "#10b981",
              top: "75%",
            }}
            title="Additional Inbound Response"
          />
        </>
      )}

      {/* Right side: Outbound output handles (Left to Right) */}
      {isSource && (
        <>
          <Handle
            type="source"
            position={Position.Right}
            id="output"
            className="flow-handle"
            style={{
              background: "#2563eb",
              top: "25%",
            }}
            title="Outbound Data Connection"
          />
          <Handle
            type="source"
            position={Position.Right}
            id="output-secondary"
            className="flow-handle"
            style={{
              background: "#2563eb",
              top: "75%",
            }}
            title="Additional Outbound Connection"
          />
        </>
      )}

      {/* Bottom side: Response output handles (for Right node returning data) */}
      {isTarget && (
        <>
          <Handle
            type="source"
            position={Position.Bottom}
            id="response-output"
            className="flow-handle"
            style={{
              background: "#10b981",
              left: "25%",
            }}
            title="Response Data Output"
          />
          <Handle
            type="source"
            position={Position.Bottom}
            id="response-output-secondary"
            className="flow-handle"
            style={{
              background: "#10b981",
              left: "75%",
            }}
            title="Additional Response Output"
          />
        </>
      )}

      {/* Top side: Request input handles (for Right node receiving requests) */}
      {isSource && (
        <>
          <Handle
            type="target"
            position={Position.Top}
            id="request-input"
            className="flow-handle"
            style={{
              background: "#2563eb",
              left: "25%",
            }}
            title="Request Input"
          />
          <Handle
            type="target"
            position={Position.Top}
            id="request-input-secondary"
            className="flow-handle"
            style={{
              background: "#2563eb",
              left: "75%",
            }}
            title="Additional Request Input"
          />
        </>
      )}

      {/* Card content */}
      <div className="system-node-header">
        <h3 style={{ margin: "0 0 8px 0", fontSize: "14px", fontWeight: "600" }}>
          {data.label}
        </h3>
      </div>

      {data.fields && data.fields.length > 0 && (
        <div className="system-node-fields">
          <ul
            style={{
              margin: "0",
              padding: "0",
              listStyle: "none",
              fontSize: "12px",
              maxHeight: "200px",
              overflowY: "auto",
            }}
          >
            {data.fields.slice(0, 5).map((field: CatalogField) => (
              <li
                key={field.id}
                style={{
                  padding: "4px 0",
                  borderBottom: "1px solid #f3f4f6",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <span style={{ fontWeight: "500" }}>{field.label || field.name}</span>
                <span
                  style={{
                    fontSize: "10px",
                    color: "#6b7280",
                    background: "#f3f4f6",
                    padding: "1px 6px",
                    borderRadius: "3px",
                  }}
                >
                  {field.data_type}
                </span>
              </li>
            ))}
          </ul>
          {data.fields.length > 5 && (
            <small style={{ display: "block", marginTop: "4px", color: "#9ca3af" }}>
              +{data.fields.length - 5} more fields
            </small>
          )}
        </div>
      )}

      {!data.fields && (
        <p
          style={{
            margin: "0",
            fontSize: "12px",
            color: "#9ca3af",
            fontStyle: "italic",
          }}
        >
          No fields configured
        </p>
      )}
    </div>
  );
}

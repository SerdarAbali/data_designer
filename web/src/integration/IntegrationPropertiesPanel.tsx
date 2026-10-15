import { useEffect, useState } from "react";

import {
  AUTH_TYPES,
  BACKOFF_STRATEGIES,
  IMPLEMENTATION_STATUSES,
  INTEGRATION_PATTERNS,
  ORCHESTRATION_ROLES,
  PATTERN_LABELS,
  STATUS_LABELS,
  specFromContract,
  type AuthType,
  type BackoffStrategy,
  type ImplementationStatus,
  type IntegrationContractSummary,
  type IntegrationInterfaceSummary,
  type IntegrationOperatingSpec,
  type IntegrationPattern,
  type OrchestrationRole,
} from "./integrationDesignModel";
import ObjectTracePanel from "../components/architecture/ObjectTracePanel";
import type { TraceObjectRef } from "../workbench/workbenchTypes";
import { integrationLog } from "./integrationLog";

export type IntegrationPropertiesDraft = {
  pattern: IntegrationPattern | null;
  implementation_status: ImplementationStatus;
  producer_interface_id: string | null;
  consumer_interface_id: string | null;
  specification: IntegrationOperatingSpec;
};

type Props = {
  contract: IntegrationContractSummary;
  interfaces: IntegrationInterfaceSummary[];
  editable: boolean;
  busy: boolean;
  error: string;
  workspaceId?: string;
  stateId?: string | null;
  onNavigateTrace?: (node: TraceObjectRef) => void;
  onSave: (draft: IntegrationPropertiesDraft) => void;
  onClose: () => void;
};

export default function IntegrationPropertiesPanel({
  contract,
  interfaces,
  editable,
  busy,
  error,
  workspaceId,
  stateId = null,
  onNavigateTrace,
  onSave,
  onClose,
}: Props) {
  const [pattern, setPattern] = useState<IntegrationPattern | "">(contract.pattern ?? "");
  const [status, setStatus] = useState<ImplementationStatus>(
    (contract.implementation_status as ImplementationStatus) ?? "draft",
  );
  const [producerId, setProducerId] = useState(contract.producer_interface?.object_id ?? "");
  const [consumerId, setConsumerId] = useState(contract.consumer_interface?.object_id ?? "");
  const [spec, setSpec] = useState<IntegrationOperatingSpec>(() => specFromContract(contract));

  useEffect(() => {
    setPattern(contract.pattern ?? "");
    setStatus((contract.implementation_status as ImplementationStatus) ?? "draft");
    setProducerId(contract.producer_interface?.object_id ?? "");
    setConsumerId(contract.consumer_interface?.object_id ?? "");
    setSpec(specFromContract(contract));
  }, [contract]);

  function updateSpec(patch: Partial<IntegrationOperatingSpec>) {
    setSpec((current) => ({ ...current, ...patch }));
  }

  function submit() {
    integrationLog.info("properties submit", {
      integrationId: contract.id,
      pattern,
      status,
      producerId,
      consumerId,
    });
    onSave({
      pattern: pattern || null,
      implementation_status: status,
      producer_interface_id: producerId || null,
      consumer_interface_id: consumerId || null,
      specification: {
        ...spec,
        idempotency_key_field_id: spec.idempotent ? spec.idempotency_key_field_id : null,
      },
    });
  }

  return (
    <aside className="integration-props" aria-label="Integration properties">
      <header className="integration-props-head">
        <div>
          <p className="eyebrow">INTEGRATION PROPERTIES</p>
          <h3>{contract.name}</h3>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close properties">
          ×
        </button>
      </header>

      {error && (
        <div className="studio-canvas-error" role="alert">
          {error}
        </div>
      )}

      <div className="integration-props-body">
        <label>
          <span>Pattern</span>
          <select
            value={pattern}
            disabled={!editable}
            onChange={(event) => setPattern(event.target.value as IntegrationPattern | "")}
          >
            <option value="">Unspecified</option>
            {INTEGRATION_PATTERNS.map((value) => (
              <option key={value} value={value}>
                {PATTERN_LABELS[value]}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Implementation status</span>
          <select
            value={status}
            disabled={!editable}
            onChange={(event) => setStatus(event.target.value as ImplementationStatus)}
          >
            {IMPLEMENTATION_STATUSES.map((value) => (
              <option key={value} value={value}>
                {STATUS_LABELS[value]}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Producer interface</span>
          <select
            value={producerId}
            disabled={!editable}
            onChange={(event) => setProducerId(event.target.value)}
          >
            <option value="">None</option>
            {interfaces.map((item) => (
              <option key={item.object_id} value={item.object_id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Consumer interface</span>
          <select
            value={consumerId}
            disabled={!editable}
            onChange={(event) => setConsumerId(event.target.value)}
          >
            <option value="">None</option>
            {interfaces.map((item) => (
              <option key={item.object_id} value={item.object_id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>

        <fieldset className="integration-props-group">
          <legend>Retry</legend>
          <label>
            <span>Max attempts</span>
            <input
              type="number"
              min={0}
              max={10}
              value={spec.retry.max_attempts}
              disabled={!editable}
              onChange={(event) =>
                updateSpec({
                  retry: { ...spec.retry, max_attempts: Number(event.target.value) },
                })
              }
            />
          </label>
          <label>
            <span>Backoff</span>
            <select
              value={spec.retry.backoff}
              disabled={!editable}
              onChange={(event) =>
                updateSpec({
                  retry: { ...spec.retry, backoff: event.target.value as BackoffStrategy },
                })
              }
            >
              {BACKOFF_STRATEGIES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        <label>
          <span>Timeout (ms)</span>
          <input
            type="number"
            min={0}
            max={600000}
            value={spec.timeout_ms ?? ""}
            disabled={!editable}
            onChange={(event) =>
              updateSpec({ timeout_ms: event.target.value === "" ? null : Number(event.target.value) })
            }
          />
        </label>

        <label className="integration-props-check">
          <input
            type="checkbox"
            checked={spec.idempotent}
            disabled={!editable}
            onChange={(event) => updateSpec({ idempotent: event.target.checked })}
          />
          <span>Idempotent delivery</span>
        </label>

        <label>
          <span>Idempotency key field</span>
          <input
            type="text"
            value={spec.idempotency_key_field_id ?? ""}
            disabled={!editable || !spec.idempotent}
            placeholder="Field UUID"
            onChange={(event) =>
              updateSpec({ idempotency_key_field_id: event.target.value || null })
            }
          />
        </label>

        <fieldset className="integration-props-group">
          <legend>Security</legend>
          <label>
            <span>Authentication</span>
            <select
              value={spec.security.auth_type}
              disabled={!editable}
              onChange={(event) =>
                updateSpec({ security: { ...spec.security, auth_type: event.target.value as AuthType } })
              }
            >
              {AUTH_TYPES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Security notes</span>
            <textarea
              rows={2}
              maxLength={2000}
              value={spec.security.notes}
              disabled={!editable}
              onChange={(event) =>
                updateSpec({ security: { ...spec.security, notes: event.target.value } })
              }
            />
          </label>
        </fieldset>

        <label>
          <span>Routing</span>
          <textarea
            rows={2}
            maxLength={2000}
            value={spec.routing}
            disabled={!editable}
            onChange={(event) => updateSpec({ routing: event.target.value })}
          />
        </label>

        <label>
          <span>Orchestration role</span>
          <select
            value={spec.orchestration_role}
            disabled={!editable}
            onChange={(event) =>
              updateSpec({ orchestration_role: event.target.value as OrchestrationRole })
            }
          >
            {ORCHESTRATION_ROLES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>

        <label>
          <span>Error handling</span>
          <textarea
            rows={2}
            maxLength={2000}
            value={spec.error_handling}
            disabled={!editable}
            onChange={(event) => updateSpec({ error_handling: event.target.value })}
          />
        </label>
      </div>

      {workspaceId && (
        <ObjectTracePanel
          workspaceId={workspaceId}
          stateId={stateId}
          objectId={contract.id}
          onNavigate={onNavigateTrace}
        />
      )}

      <footer className="integration-props-footer">
        <button
          type="button"
          className="primary-button"
          disabled={!editable || busy}
          onClick={submit}
        >
          {busy ? "Saving…" : "Save properties"}
        </button>
        <span className="integration-props-revision">Revision {contract.revision}</span>
      </footer>
    </aside>
  );
}

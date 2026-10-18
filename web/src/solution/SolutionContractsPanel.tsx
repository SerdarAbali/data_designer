import { useCallback, useEffect, useState } from "react";

import { architectureFactLabel } from "../architectureFacts";
import { IMPLEMENTATION_STATUS_LABELS, IMPLEMENTATION_STATUSES } from "../integration/integrationDesignModel";
import {
  createSolutionContract,
  deleteSolutionContract,
  listAssociableContracts,
  listSolutionContracts,
  SOLUTION_CONTRACT_ROLE_LABELS,
  SOLUTION_CONTRACT_ROLES,
  updateSolutionContract,
  type AssociableContract,
  type SolutionContractRole,
  type SolutionIntegration,
} from "./solutionModel";

type Props = {
  workspaceId: string;
  solutionId: string;
  stateId: string;
  /** Current is read-only, so associations can only be viewed there. */
  editable: boolean;
  busy: boolean;
  onOpenContract: (contractId: string) => void;
};

function implementationLabel(value: string): string {
  return IMPLEMENTATION_STATUS_LABELS[value as (typeof IMPLEMENTATION_STATUSES)[number]] ?? value;
}

function factLabel(value: string | null): string {
  return architectureFactLabel(value);
}

/**
 * The Contracts tab of the Solution inspector.
 *
 * Contract ownership is never inferred from system membership, so this panel is
 * the only place a Boundary is linked to a Contract, and the role is stated in
 * words rather than by colour or badge.
 */
export default function SolutionContractsPanel({
  workspaceId,
  solutionId,
  stateId,
  editable,
  busy,
  onOpenContract,
}: Props) {
  const [associations, setAssociations] = useState<SolutionIntegration[]>([]);
  const [contracts, setContracts] = useState<AssociableContract[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [formOpen, setFormOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [contractId, setContractId] = useState("");
  const [role, setRole] = useState<SolutionContractRole>("owned");
  const [description, setDescription] = useState("");
  const [formError, setFormError] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!workspaceId || !solutionId || !stateId) {
      setAssociations([]);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [nextAssociations, nextContracts] = await Promise.all([
        listSolutionContracts(workspaceId, solutionId, stateId),
        listAssociableContracts(workspaceId),
      ]);
      setAssociations(nextAssociations);
      setContracts(nextContracts);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load solution contracts.");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, solutionId, stateId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setFormOpen(false);
    setEditingId(null);
    setFormError("");
  }, [solutionId, stateId]);

  const associatedIds = new Set(associations.map((item) => item.integration_id));
  const available = contracts.filter((item) => !associatedIds.has(item.id));

  function startCreate() {
    setEditingId(null);
    setContractId(available[0]?.id ?? "");
    setRole("owned");
    setDescription("");
    setFormError("");
    setFormOpen(true);
  }

  function startEdit(association: SolutionIntegration) {
    setEditingId(association.id);
    setContractId(association.integration_id);
    setRole(association.role);
    setDescription(association.description ?? "");
    setFormError("");
    setFormOpen(true);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editingId && !contractId) {
      setFormError("Select a Contract to associate.");
      return;
    }
    setSaving(true);
    setFormError("");
    try {
      if (editingId) {
        await updateSolutionContract(workspaceId, solutionId, editingId, {
          role,
          description: description.trim() ? description.trim() : null,
        });
      } else {
        await createSolutionContract(workspaceId, solutionId, {
          state_id: stateId,
          integration_id: contractId,
          role,
          description: description.trim() ? description.trim() : null,
        });
      }
      setFormOpen(false);
      setEditingId(null);
      await load();
    } catch (caught) {
      setFormError(caught instanceof Error ? caught.message : "Could not save this association.");
    } finally {
      setSaving(false);
    }
  }

  async function remove(association: SolutionIntegration) {
    if (
      !window.confirm(
        `Remove the association with “${association.contract.name}”? The Contract and the solution are not deleted.`,
      )
    ) {
      return;
    }
    setError("");
    try {
      await deleteSolutionContract(workspaceId, solutionId, association.id);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not remove this association.");
    }
  }

  return (
    <section className="solution-contracts" aria-label="Solution contracts">
      {loading && (
        <p className="architecture-topbar-hint" role="status">
          Loading solution contracts…
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {!loading && associations.length === 0 && (
        <p className="architecture-topbar-hint">
          No Contracts are associated with this solution yet. Ownership is explicit: a Contract is
          never linked automatically from its source or target system membership.
        </p>
      )}

      {associations.length > 0 && (
        <ul className="solution-contract-list">
          {associations.map((association) => (
            <li key={association.id} className="solution-contract-item">
              <div className="solution-contract-head">
                <strong>{association.contract.name}</strong>
                <span className={`solution-contract-role role-${association.role}`}>
                  {SOLUTION_CONTRACT_ROLE_LABELS[association.role]}
                </span>
              </div>
              <p className="solution-contract-flow">
                <span>{association.contract.source.system_name}</span>
                {association.contract.mediator && (
                  <>
                    <span aria-hidden="true">→</span>
                    <span className="solution-contract-mediator">
                      {association.contract.mediator.system_name}
                      {association.contract.explicit_mediator ? " (explicit)" : " (inferred)"}
                    </span>
                  </>
                )}
                <span aria-hidden="true">→</span>
                <span>{association.contract.target.system_name}</span>
              </p>
              <dl className="solution-contract-facts">
                <div>
                  <dt>Lifecycle</dt>
                  <dd>{factLabel(association.contract.lifecycle_stage.value)}</dd>
                </div>
                <div>
                  <dt>Operational</dt>
                  <dd>{factLabel(association.contract.operational_status.value)}</dd>
                </div>
                <div>
                  <dt>Environment</dt>
                  <dd>{factLabel(association.contract.environment_scope.value)}</dd>
                </div>
                <div>
                  <dt>Implementation</dt>
                  <dd>{implementationLabel(association.contract.implementation_status)}</dd>
                </div>
                <div>
                  <dt>Evidence</dt>
                  <dd>{association.contract.evidence_count}</dd>
                </div>
                <div>
                  <dt>Applies to</dt>
                  <dd>
                    {association.state_applicability === "canonical"
                      ? "All states (canonical)"
                      : association.state_name
                        ? `${association.state_name} state`
                        : "State-scoped"}
                  </dd>
                </div>
              </dl>
              {association.description && (
                <p className="solution-contract-description">{association.description}</p>
              )}
              <div className="solution-contract-actions">
                <button type="button" onClick={() => onOpenContract(association.integration_id)}>
                  Open in Integration Architecture
                </button>
                {editable && (
                  <>
                    <button type="button" className="secondary-button" onClick={() => startEdit(association)}>
                      Edit
                    </button>
                    <button
                      type="button"
                      className="secondary-button solution-contract-danger"
                      onClick={() => void remove(association)}
                    >
                      Remove
                    </button>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {editable && !formOpen && (
        <div className="solution-contract-add">
          <button type="button" disabled={busy || available.length === 0} onClick={startCreate}>
            + Associate a contract
          </button>
          {available.length === 0 && contracts.length > 0 && (
            <p className="architecture-topbar-hint">
              Every Contract is already associated in this state.
            </p>
          )}
        </div>
      )}

      {editable && formOpen && (
        <form className="solution-contract-form" onSubmit={(event) => void submit(event)}>
          <label>
            Contract
            <select
              value={contractId}
              disabled={Boolean(editingId) || saving}
              onChange={(event) => setContractId(event.target.value)}
            >
              <option value="">Select a contract…</option>
              {contracts.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Role
            <select value={role} onChange={(event) => setRole(event.target.value as SolutionContractRole)} disabled={saving}>
              {SOLUTION_CONTRACT_ROLES.map((value) => (
                <option key={value} value={value}>
                  {SOLUTION_CONTRACT_ROLE_LABELS[value]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Description
            <textarea
              value={description}
              maxLength={500}
              rows={2}
              placeholder="Why this solution is associated with the contract"
              onChange={(event) => setDescription(event.target.value)}
              disabled={saving}
            />
          </label>
          {formError && (
            <p className="error" role="alert">
              {formError}
            </p>
          )}
          <div className="solution-panel-actions">
            <button
              type="button"
              disabled={saving}
              onClick={() => {
                setFormOpen(false);
                setEditingId(null);
                setFormError("");
              }}
            >
              Cancel
            </button>
            <button type="submit" disabled={saving || (!editingId && !contractId)}>
              {saving ? "Saving…" : editingId ? "Save association" : "Associate contract"}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

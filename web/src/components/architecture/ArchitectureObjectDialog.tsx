import React from "react";
import type {
  ArchitectureDiscipline,
  ArchitectureObjectKind,
} from "../../architectureTypes";
import type { CanonicalSystem } from "../../architectureCanvasModel";

export type ArchitectureObjectDraft = {
  kind: ArchitectureObjectKind;
  name: string;
  description: string;
  owner?: string;
  relatedSystemId?: string;
  authoritativeSystemId?: string;
};

type Props = {
  kind: ArchitectureObjectKind;
  discipline: ArchitectureDiscipline;
  systems: CanonicalSystem[];
  onCancel: () => void;
  onCreate: (draft: ArchitectureObjectDraft) => Promise<void>;
};

const LABELS: Record<ArchitectureObjectKind, string> = {
  business_requirement: "Business Requirement",
  business_capability: "Business Capability",
  information_object: "Information Object",
  solution_boundary: "Solution Boundary",
  component: "Component",
  interface: "Interface",
};

export default function ArchitectureObjectDialog({
  kind,
  discipline,
  systems,
  onCancel,
  onCreate,
}: Props) {
  const [name, setName] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [owner, setOwner] = React.useState("");
  const [systemId, setSystemId] = React.useState(systems[0]?.id ?? "");
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");
  const isInformationObject = kind === "information_object";
  const label = LABELS[kind];

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    if (!systemId) {
      setError("Choose an existing system.");
      return;
    }
    if (isInformationObject && !owner.trim()) {
      setError("Enter an owner.");
      return;
    }

    setBusy(true);
    try {
      await onCreate({
        kind,
        name: name.trim(),
        description: description.trim(),
        ...(isInformationObject
          ? { owner: owner.trim(), authoritativeSystemId: systemId }
          : { relatedSystemId: systemId }),
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : `Could not add ${label.toLowerCase()}.`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="architecture-dialog-backdrop" role="presentation" onClick={onCancel}>
      <form
        className="architecture-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="architecture-object-dialog-title"
        onClick={(event) => event.stopPropagation()}
        onSubmit={(event) => void submit(event)}
      >
        <p className="eyebrow">{discipline.toUpperCase()} ARCHITECTURE</p>
        <h3 id="architecture-object-dialog-title">Add {label}</h3>
        <label>
          Name
          <input
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={160}
            required
          />
        </label>
        <label>
          Description
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={500}
            rows={3}
          />
        </label>
        {isInformationObject && (
          <label>
            Owner
            <input
              value={owner}
              onChange={(event) => setOwner(event.target.value)}
              maxLength={160}
              required
            />
          </label>
        )}
        <label>
          {isInformationObject ? "Authoritative system" : "Related system"}
          {systems.length === 0 ? (
            <span>No active systems are available. Add one to the catalog first.</span>
          ) : (
            <select value={systemId} onChange={(event) => setSystemId(event.target.value)} required>
              {systems.map((system) => (
                <option key={system.id} value={system.id}>{system.name}</option>
              ))}
            </select>
          )}
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="architecture-dialog-actions">
          <button type="button" className="secondary-button" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
          <button type="submit" disabled={busy || systems.length === 0}>
            {busy ? "Adding…" : `Add ${label}`}
          </button>
        </div>
      </form>
    </div>
  );
}

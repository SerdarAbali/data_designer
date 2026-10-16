import { useMemo } from "react";

import type { InformationPhysical, InformationPhysicalMapping } from "../informationModel";

export const REALIZATION_STATUS_LABELS: Record<string, string> = {
  realized: "Realized",
  partial: "Partially realized",
  unmapped: "Unmapped",
  invalid: "Invalid physical reference",
};

type Props = {
  physical: InformationPhysical;
  onSelectAttribute: (entityObjectId: string, attributeObjectId: string) => void;
  onOpenCatalog: () => void;
  onOpenContract: (contractId: string) => void;
};

export default function PhysicalRealizationView({
  physical,
  onSelectAttribute,
  onOpenCatalog,
  onOpenContract,
}: Props) {
  const groups = useMemo(() => {
    const byEntity = new Map<string, { name: string; mappings: InformationPhysicalMapping[] }>();
    for (const mapping of physical.mappings) {
      const group = byEntity.get(mapping.entity_object_id) ?? {
        name: mapping.entity_name,
        mappings: [],
      };
      group.mappings.push(mapping);
      byEntity.set(mapping.entity_object_id, group);
    }
    return [...byEntity.entries()];
  }, [physical.mappings]);

  return (
    <section className="information-physical" aria-label="Physical realization">
      <header className="information-physical-summary">
        {(["realized", "partial", "unmapped", "invalid"] as const).map((status) => (
          <span key={status} className={`information-physical-chip status-${status}`}>
            {REALIZATION_STATUS_LABELS[status]}: {physical.summary[status] ?? 0}
          </span>
        ))}
      </header>
      {groups.length === 0 && (
        <p className="information-projection-empty">
          No attributes to realize yet. Add attributes in the Logical Model view.
        </p>
      )}
      {groups.map(([entityId, group]) => (
        <article key={entityId} className="information-physical-entity">
          <h3>{group.name}</h3>
          <ul className="information-physical-list">
            {group.mappings.map((mapping) => {
              const statusLabel = REALIZATION_STATUS_LABELS[mapping.status] ?? mapping.status;
              const logicalName = `${mapping.entity_name}.${mapping.attribute_name}`;
              const mapped = Boolean(mapping.catalog_field_id);
              const systemName = mapping.system_name ?? "";
              const objectName = mapping.catalog_object_name ?? "";
              const fieldName = mapping.catalog_field_name ?? "";
              const physicalName = mapped ? `${systemName} / ${objectName} / ${fieldName}` : null;
              return (
                <li
                  key={mapping.attribute_object_id}
                  className={`information-physical-row status-${mapping.status}`}
                  data-status={mapping.status}
                >
                  <button
                    type="button"
                    className="information-physical-logical"
                    onClick={() =>
                      onSelectAttribute(mapping.entity_object_id, mapping.attribute_object_id)
                    }
                    title={`${logicalName} — open the attribute inspector to map or remap`}
                  >
                    <strong className="information-physical-name" title={logicalName}>
                      {logicalName}
                    </strong>
                    <small className="information-physical-meta">
                      {mapping.data_type}
                      {mapping.required ? " · required" : " · optional"}
                    </small>
                  </button>

                  <span className="information-physical-relation">
                    <span className="information-physical-arrow" aria-hidden="true">
                      →
                    </span>
                    <span className={`information-physical-status status-${mapping.status}`}>
                      {statusLabel}
                    </span>
                  </span>

                  {mapped ? (
                    <button
                      type="button"
                      className="information-physical-mapping"
                      onClick={onOpenCatalog}
                      title={`${physicalName} — open in the catalog`}
                    >
                      <strong className="information-physical-name" title={physicalName ?? undefined}>
                        <span className="information-physical-system" title={systemName}>
                          {systemName}
                        </span>
                        <span className="information-physical-separator" aria-hidden="true">
                          {" / "}
                        </span>
                        <span className="information-physical-object" title={objectName}>
                          {objectName}
                        </span>
                        <span className="information-physical-separator" aria-hidden="true">
                          {" / "}
                        </span>
                        <span className="information-physical-field" title={fieldName}>
                          {fieldName}
                        </span>
                      </strong>
                    </button>
                  ) : (
                    <span className="information-physical-unmapped">Not mapped to a catalog field</span>
                  )}

                  {mapping.contracts.length > 0 && (
                    <span className="information-physical-contracts">
                      <span className="information-physical-contracts-label">Contracts</span>
                      {mapping.contracts.map((contract) => (
                        <button
                          key={contract.id}
                          type="button"
                          className="information-physical-contract"
                          onClick={() => onOpenContract(contract.id)}
                          title={`${contract.name} · direction: ${contract.direction}`}
                        >
                          {contract.name}
                        </button>
                      ))}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </article>
      ))}
    </section>
  );
}

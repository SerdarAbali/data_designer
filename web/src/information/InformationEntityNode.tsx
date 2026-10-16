import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import {
  attributeSummary,
  handleId,
  keyBadge,
  type InformationEntity,
  type InformationFlowSide,
} from "./informationModel";

const SIDES: { side: InformationFlowSide; position: Position }[] = [
  { side: "top", position: Position.Top },
  { side: "right", position: Position.Right },
  { side: "bottom", position: Position.Bottom },
  { side: "left", position: Position.Left },
];

/**
 * Automatic left/right connectors anchor inside the header band, above the
 * attribute list, so a relationship leaves the card from a stable point that
 * clears every attribute row instead of the middle of the attribute list.
 */
const SIDE_ANCHOR_TOP = 22;

/** Handles sit just outside the border so connector lines start outside it. */
const HANDLE_INSET = 6;

function handleStyle(position: Position) {
  switch (position) {
    case Position.Left:
      return { top: SIDE_ANCHOR_TOP, left: -HANDLE_INSET };
    case Position.Right:
      return { top: SIDE_ANCHOR_TOP, right: -HANDLE_INSET };
    case Position.Top:
      return { top: -HANDLE_INSET };
    case Position.Bottom:
      return { bottom: -HANDLE_INSET };
    default:
      return undefined;
  }
}


export type InformationEntityNodeData = {
  entity: InformationEntity;
  editable: boolean;
  selectedAttributeId: string | null;
  onSelectAttribute: (attributeId: string) => void;
  /** Optional inline attribute filter applied inside the node. */
  attributeFilter?: string;
  /** Optional filter showing only attributes without a physical realization. */
  unmappedOnly?: boolean;
};

export type InformationEntityFlowNode = Node<InformationEntityNodeData, "informationEntity">;

export default function InformationEntityNode({ data, selected }: NodeProps<InformationEntityFlowNode>) {
  const { entity, editable, selectedAttributeId, onSelectAttribute } = data;
  const term = (data.attributeFilter ?? "").trim().toLowerCase();
  const attributes = entity.attributes.filter(
    (attribute) =>
      (!term || attribute.name.toLowerCase().includes(term)) &&
      (!data.unmappedOnly || !attribute.realization),
  );
  const filtered = attributes.length !== entity.attributes.length;
  return (
    <article
      className={`information-entity-node${selected ? " selected" : ""}`}
      aria-label={`Entity ${entity.name}`}
      data-object-id={entity.object_id}
      data-occurrence-id={entity.occurrence_id}
    >
      {SIDES.map(({ side, position }) => (
        <Handle
          key={`t-${side}`}
          id={handleId("target", side)}
          type="target"
          position={position}
          isConnectable={editable}
          style={handleStyle(position)}
        />
      ))}
      {SIDES.map(({ side, position }) => (
        <Handle
          key={`s-${side}`}
          id={handleId("source", side)}
          type="source"
          position={position}
          isConnectable={editable}
          style={handleStyle(position)}
        />
      ))}
      <header>
        <span className="information-entity-icon" aria-hidden="true">
          {entity.name.slice(0, 1).toUpperCase()}
        </span>
        <strong title={entity.name}>{entity.name}</strong>
        <span className="information-entity-count" title="Attributes">
          {filtered ? `${attributes.length}/${entity.attributes.length}` : entity.attributes.length}
        </span>
      </header>
      {entity.attributes.length === 0 ? (
        <p className="information-entity-empty">No attributes yet</p>
      ) : attributes.length === 0 ? (
        <p className="information-entity-empty">No attributes match the filter</p>
      ) : (
        <ul className="information-attribute-list">
          {attributes.map((attribute) => (
            <li
              key={attribute.object_id}
              className={`${attribute.object_id === selectedAttributeId ? "selected" : ""}${
                attribute.realization ? "" : " unmapped"
              }`}
            >
              <button
                type="button"
                className="nodrag nopan"
                onClick={(event) => {
                  event.stopPropagation();
                  onSelectAttribute(attribute.object_id);
                }}
              >
                <span className="information-attribute-name" title={attribute.name}>
                  {attribute.name}
                </span>
                <span className="information-attribute-type" title={attributeSummary(attribute)}>
                  {keyBadge(attribute) && <em className="information-key-badge">{keyBadge(attribute)}</em>}
                  {attribute.data_type}
                  {attribute.required ? " *" : ""}
                  {!attribute.realization && (
                    <em className="information-attribute-unmapped" title="No physical realization">
                      unmapped
                    </em>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

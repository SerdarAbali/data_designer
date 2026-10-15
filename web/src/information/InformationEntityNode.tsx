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


export type InformationEntityNodeData = {
  entity: InformationEntity;
  editable: boolean;
  selectedAttributeId: string | null;
  onSelectAttribute: (attributeId: string) => void;
};

export type InformationEntityFlowNode = Node<InformationEntityNodeData, "informationEntity">;

export default function InformationEntityNode({ data, selected }: NodeProps<InformationEntityFlowNode>) {
  const { entity, editable, selectedAttributeId, onSelectAttribute } = data;
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
        />
      ))}
      {SIDES.map(({ side, position }) => (
        <Handle
          key={`s-${side}`}
          id={handleId("source", side)}
          type="source"
          position={position}
          isConnectable={editable}
        />
      ))}
      <header>
        <span className="information-entity-icon" aria-hidden="true">
          {entity.name.slice(0, 1).toUpperCase()}
        </span>
        <strong title={entity.name}>{entity.name}</strong>
        <span className="information-entity-count" title="Attributes">
          {entity.attributes.length}
        </span>
      </header>
      {entity.attributes.length === 0 ? (
        <p className="information-entity-empty">No attributes yet</p>
      ) : (
        <ul className="information-attribute-list">
          {entity.attributes.map((attribute) => (
            <li
              key={attribute.object_id}
              className={attribute.object_id === selectedAttributeId ? "selected" : ""}
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
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

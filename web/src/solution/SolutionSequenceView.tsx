import type { SolutionComponent } from "./solutionModel";

type Props = {
  solutionName: string;
  components: SolutionComponent[];
};

export default function SolutionSequenceView({ solutionName, components }: Props) {
  const lifelines = components.filter((component) => component.interfaces.length > 0);

  if (lifelines.length === 0) {
    return (
      <div className="solution-sequence-empty" role="status">
        Add interfaces to components to see the interaction view.
      </div>
    );
  }

  return (
    <div className="solution-sequence" aria-label={`Interaction view for ${solutionName}`}>
      <div
        className="solution-sequence-headers"
        style={{ gridTemplateColumns: `repeat(${lifelines.length}, minmax(140px, 1fr))` }}
      >
        {lifelines.map((component) => (
          <div key={component.object_id} className="solution-sequence-lifeline-head">
            <span className="solution-sequence-actor">{component.name}</span>
            {component.technology && (
              <span className="solution-sequence-actor-tech">{component.technology}</span>
            )}
          </div>
        ))}
      </div>
      <div className="solution-sequence-body">
        {lifelines.flatMap((component, columnIndex) =>
          component.interfaces.map((ui) => (
            <div
              key={ui.object_id}
              className="solution-sequence-message"
              style={{ paddingLeft: `${columnIndex * 12}px` }}
            >
              <span className={`solution-sequence-arrow direction-${ui.direction}`} aria-hidden="true">
                {ui.direction === "provided" ? "\u2192" : "\u2190"}
              </span>
              <span className="solution-sequence-label">
                <strong>{ui.name}</strong>
                <em>{ui.direction}</em>
                {ui.operations.length > 0 && (
                  <span className="solution-sequence-ops">
                    {ui.operations.map((operation) => operation.name).join(", ")}
                  </span>
                )}
              </span>
            </div>
          )),
        )}
      </div>
    </div>
  );
}

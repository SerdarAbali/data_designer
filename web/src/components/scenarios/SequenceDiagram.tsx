import React from "react";
import type { EnterpriseArchitectureIndex } from "../../enterpriseArchitectureIndex";
import type { ScenarioDocument, ScenarioPhase, StepOutcome } from "../../scenarioModel";
import { layoutSequence, SEQUENCE_METRICS, type LayoutMessage } from "../../scenarioSequenceLayout";

const PHASE_COLORS: Record<ScenarioPhase, string> = {
  request: "var(--discipline-integration)",
  "success-response": "var(--color-healthy)",
  "async-response": "var(--color-healthy)",
  "error-response": "var(--color-danger)",
};

const OUTCOME_LABELS: Record<StepOutcome, string> = {
  ok: "Evaluated: OK",
  mismatch: "Evaluated: mismatch",
  failed: "Evaluated: failed",
  skipped: "Evaluated: skipped",
  missing_reference: "Missing reference",
  not_evaluated: "Not evaluated",
};

type Props = {
  document: ScenarioDocument;
  index: EnterpriseArchitectureIndex | null;
  outcomes?: ReadonlyMap<string, StepOutcome>;
  selectedStepId?: string | null;
  ariaLabel?: string;
  onOpenContractPhase?: (contractId: string, phase: ScenarioPhase) => void;
  onSelectStep?: (stepId: string) => void;
};

function messageColor(message: LayoutMessage): string {
  if (message.missing) return "var(--color-muted)";
  if (message.phase) return PHASE_COLORS[message.phase];
  return "var(--color-ink)";
}

function arrowPath(message: LayoutMessage): string {
  if (message.self) {
    const w = SEQUENCE_METRICS.selfLoopWidth;
    return `M ${message.fromX} ${message.y} h ${w} v 26 h ${-w}`;
  }
  return `M ${message.fromX} ${message.y} H ${message.toX}`;
}

function truncate(value: string, length: number): string {
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

/** Read-only UML sequence diagram generated from the scenario document. */
export default function SequenceDiagram({
  document,
  index,
  outcomes,
  selectedStepId,
  ariaLabel = "Scenario sequence diagram",
  onOpenContractPhase,
  onSelectStep,
}: Props) {
  const layout = React.useMemo(() => layoutSequence(document, index, outcomes), [document, index, outcomes]);
  const markerId = React.useId().replace(/:/g, "");
  const m = SEQUENCE_METRICS;

  if (layout.lifelines.length === 0) {
    return (
      <div className="scenario-diagram-empty">
        Add participants or contract steps to generate the sequence diagram.
      </div>
    );
  }

  return (
    <div className="scenario-diagram-scroll">
      <svg
        className="scenario-diagram"
        width={layout.width}
        height={layout.height}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
        role="group"
        aria-label={ariaLabel}
      >
        <defs>
          {(["request", "success-response", "error-response", "neutral", "missing"] as const).map((key) => (
            <marker
              key={key}
              id={`${markerId}-${key}`}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="8"
              markerHeight="8"
              orient="auto-start-reverse"
            >
              <path
                d="M 0 0 L 10 5 L 0 10 z"
                fill={key === "neutral" ? "var(--color-ink)" : key === "missing" ? "var(--color-muted)" : PHASE_COLORS[key]}
              />
            </marker>
          ))}
        </defs>

        {layout.lifelines.map((lifeline) => (
          <g key={lifeline.id} className={`scenario-lifeline${lifeline.missing ? " missing" : ""}`}>
            <title>{lifeline.missing ? `${lifeline.label} (missing or archived)` : lifeline.label}</title>
            <line x1={lifeline.x} x2={lifeline.x} y1={layout.lifelineTop} y2={layout.lifelineBottom} />
            {lifeline.kind === "actor" ? (
              <g className="scenario-actor" transform={`translate(${lifeline.x} 2)`}>
                <circle cx={0} cy={7} r={5.5} />
                <path d="M 0 12.5 v 13 M -9 17 h 18 M 0 25.5 l -7 9 M 0 25.5 l 7 9" />
                <text x={0} y={48} textAnchor="middle">{truncate(lifeline.label, 24)}</text>
              </g>
            ) : (
              <g className="scenario-system-head">
                <rect x={lifeline.x - m.headerWidth / 2} y={8} width={m.headerWidth} height={m.headerHeight - 14} rx={7} />
                <text x={lifeline.x} y={8 + (m.headerHeight - 14) / 2 + 4} textAnchor="middle">
                  {truncate(lifeline.label, 22)}
                </text>
              </g>
            )}
          </g>
        ))}

        {layout.fragments.map((fragment) => (
          <g key={fragment.id} className={`scenario-fragment scenario-fragment-${fragment.kind}`}>
            <rect x={fragment.x} y={fragment.y} width={fragment.width} height={fragment.height} rx={4} />
            <path className="scenario-fragment-tab" d={`M ${fragment.x} ${fragment.y} h 46 v 14 l -8 8 h -38 z`} />
            <text className="scenario-fragment-kind" x={fragment.x + 7} y={fragment.y + 15}>
              {fragment.kind}
            </text>
            {fragment.operands.map((operand, operandIndex) => (
              <g key={operandIndex}>
                {operandIndex > 0 && (
                  <line
                    className="scenario-fragment-divider"
                    x1={fragment.x}
                    x2={fragment.x + fragment.width}
                    y1={operand.y - 3}
                    y2={operand.y - 3}
                  />
                )}
                {(operand.guard || (fragment.kind === "alt" && operandIndex > 0)) && (
                  <text
                    className="scenario-fragment-guard"
                    x={fragment.x + (operandIndex === 0 ? 54 : 10)}
                    y={operandIndex === 0 ? fragment.y + 15 : operand.y + 13}
                  >
                    [{operand.guard || "else"}]
                  </text>
                )}
              </g>
            ))}
          </g>
        ))}

        {layout.messages.map((message) => {
          const color = messageColor(message);
          const marker = message.missing
            ? "missing"
            : message.phase
              ? message.phase === "async-response" ? "success-response" : message.phase
              : "neutral";
          const clickable = !!message.contractId && !!message.phase && !message.missing && !!onOpenContractPhase;
          const selectable = !!onSelectStep && !message.missing;
          const interactive = clickable || selectable;
          const textX = message.self ? message.fromX + 8 : (message.fromX + message.toX) / 2;
          const anchor = message.self ? "start" : "middle";
          const labelY = message.self ? message.y - 6 : message.y - 8;
          const description = [
            `Step ${message.number}: ${message.label}`,
            message.detail,
            message.missing,
            message.status ? `Mapping status: ${message.status}` : null,
            message.outcome ? OUTCOME_LABELS[message.outcome] : null,
            clickable ? "Opens the contract phase" : selectable ? "Opens the operation" : null,
          ].filter(Boolean).join(". ");
          const open = () => {
            if (clickable) onOpenContractPhase!(message.contractId!, message.phase!);
            else if (selectable) onSelectStep!(message.stepId);
          };
          return (
            <g
              key={message.stepId}
              className={[
                "scenario-message",
                message.missing ? "missing" : "",
                message.outcome ? `outcome-${message.outcome}` : "",
                selectedStepId === message.stepId ? "selected" : "",
                interactive ? "clickable" : "",
              ].filter(Boolean).join(" ")}
              data-step-id={message.stepId}
              role={interactive ? "button" : undefined}
              tabIndex={interactive ? 0 : undefined}
              aria-label={description}
              onClick={interactive ? open : undefined}
              onKeyDown={interactive ? (event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  open();
                }
              } : undefined}
            >
              <title>{description}</title>
              <path d={arrowPath(message)} fill="none" stroke="transparent" strokeWidth={18} />
              <path
                className="scenario-message-line"
                d={arrowPath(message)}
                fill="none"
                stroke={color}
                strokeWidth={1.6}
                strokeDasharray={message.dashed || message.missing ? "6 4" : undefined}
                markerEnd={`url(#${markerId}-${marker})`}
              />
              <text className="scenario-message-label" x={textX} y={labelY} textAnchor={anchor} fill={color}>
                <tspan className="scenario-message-number">{message.number}. </tspan>
                {truncate(message.label, 48)}
              </text>
              {message.detail && (
                <text
                  className="scenario-message-detail"
                  x={textX}
                  y={message.self ? message.y + 42 : message.y + 15}
                  textAnchor={anchor}
                >
                  {truncate(message.detail, 56)}
                </text>
              )}
              {message.outcome && message.outcome !== "not_evaluated" && (
                <circle
                  className={`scenario-outcome-dot outcome-${message.outcome}`}
                  cx={message.self ? message.fromX - 9 : Math.min(message.fromX, message.toX) + 10}
                  cy={message.y - 12}
                  r={4}
                />
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

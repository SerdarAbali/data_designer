export type BreadcrumbStep = {
  id: string;
  label: string;
  kind: "solution" | "component" | "interface" | "operation";
};

type Props = {
  steps: BreadcrumbStep[];
  onNavigate: (step: BreadcrumbStep, index: number) => void;
};

export default function SolutionBreadcrumb({ steps, onNavigate }: Props) {
  return (
    <nav className="solution-breadcrumb" aria-label="Solution drill-down">
      {steps.map((step, index) => (
        <span key={`${step.kind}-${step.id}`} className="solution-breadcrumb-item">
          {index > 0 && <span className="solution-breadcrumb-sep" aria-hidden="true">/</span>}
          <button
            type="button"
            className={`solution-breadcrumb-button${index === steps.length - 1 ? " current" : ""}`}
            aria-current={index === steps.length - 1 ? "page" : undefined}
            onClick={() => onNavigate(step, index)}
          >
            <span className={`solution-breadcrumb-kind kind-${step.kind}`}>{step.kind}</span>
            {step.label}
          </button>
        </span>
      ))}
    </nav>
  );
}

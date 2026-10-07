export type InspectorTab = "general" | "schema" | "metadata";

const tabs: { id: InspectorTab; label: string }[] = [
  { id: "general", label: "General" },
  { id: "schema", label: "Schema" },
  { id: "metadata", label: "Raw metadata JSON" },
];

type Props = {
  value: InspectorTab;
  onChange: (tab: InspectorTab) => void;
  includeSchema?: boolean;
};

export default function InspectorTabs({ value, onChange, includeSchema = true }: Props) {
  return (
    <nav className="inspector-tabs" aria-label="Entity details">
      {tabs.filter((tab) => includeSchema || tab.id !== "schema").map((tab) => (
        <button
          type="button"
          key={tab.id}
          className={value === tab.id ? "active" : ""}
          aria-pressed={value === tab.id}
          onClick={() => onChange(tab.id)}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}

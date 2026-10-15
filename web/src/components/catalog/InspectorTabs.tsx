export type InspectorTab = string;

export type InspectorTabItem = {
  id: string;
  label: string;
};

type Props = {
  tabs: InspectorTabItem[];
  value: string;
  onChange: (tab: string) => void;
  ariaLabel?: string;
};

/** Generic tab strip for catalog inspectors. */
export default function InspectorTabs({ tabs, value, onChange, ariaLabel = "Details" }: Props) {
  return (
    <nav className="inspector-tabs" aria-label={ariaLabel}>
      {tabs.map((tab) => (
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

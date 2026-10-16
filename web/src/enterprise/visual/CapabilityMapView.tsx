import { useState } from "react";

import type {
  CapabilityMap,
  EnterpriseImpact,
  EnterpriseModel,
} from "../enterpriseModel";
import { capabilityClusters } from "./enterpriseCanvasModel";

type Props = {
  model: EnterpriseModel;
  capabilityMap: CapabilityMap;
  impact: EnterpriseImpact | null;
  selectedObjectId: string | null;
  onSelectObject: (objectId: string) => void;
};

type Overlay = "impact" | "applications" | "risks";

const CHANGE_LABELS: Record<string, string> = {
  added: "Added",
  removed: "Removed",
  changed: "Changed",
  reused: "Reused",
};

export default function CapabilityMapView({
  model,
  capabilityMap,
  impact,
  selectedObjectId,
  onSelectObject,
}: Props) {
  const [overlays, setOverlays] = useState<Record<Overlay, boolean>>({
    impact: false,
    applications: false,
    risks: false,
  });
  const clusters = capabilityClusters(model, capabilityMap, impact);
  const riskPrinciples = model.principles.filter((principle) => principle.principle_type === "risk");
  const risksAvailable = riskPrinciples.length > 0 || Boolean(impact?.gaps.length);

  function toggle(overlay: Overlay) {
    setOverlays((current) => ({ ...current, [overlay]: !current[overlay] }));
  }

  return (
    <div className="enterprise-capability-map" aria-label="Capability map">
      <div className="enterprise-overlay-toggles" role="group" aria-label="Capability map overlays">
        <button
          type="button"
          className={overlays.impact ? "active" : ""}
          aria-pressed={overlays.impact}
          onClick={() => toggle("impact")}
        >
          Current / Candidate impact
        </button>
        <button
          type="button"
          className={overlays.applications ? "active" : ""}
          aria-pressed={overlays.applications}
          onClick={() => toggle("applications")}
        >
          Supporting applications
        </button>
        <button
          type="button"
          className={overlays.risks ? "active" : ""}
          aria-pressed={overlays.risks}
          disabled={!risksAvailable}
          onClick={() => toggle("risks")}
        >
          Risks / gaps
        </button>
      </div>

      {clusters.length === 0 ? (
        <p className="architecture-topbar-hint">No capabilities recorded yet.</p>
      ) : (
        <div className="enterprise-capability-clusters">
          {clusters.map((cluster) => (
            <section key={cluster.id} className="enterprise-capability-cluster">
              <div className="information-section-heading">
                <strong>{cluster.label}</strong>
                <span className="item-count">{cluster.capabilities.length}</span>
              </div>
              <ul className="enterprise-capability-list">
                {cluster.capabilities.map((capability) => (
                  <li key={capability.objectId}>
                    <button
                      type="button"
                      className={`enterprise-capability-card${capability.objectId === selectedObjectId ? " selected" : ""}`}
                      onClick={() => onSelectObject(capability.objectId)}
                    >
                      <span className="enterprise-capability-name">{capability.name}</span>
                      {capability.change && overlays.impact && (
                        <em className={`enterprise-badge change-${capability.change}`}>
                          {CHANGE_LABELS[capability.change] ?? capability.change}
                        </em>
                      )}
                      <span className="enterprise-capability-coverage">
                        {capability.flags.lacksOwner && <em className="enterprise-badge enterprise-badge-warn">no owner</em>}
                        {capability.flags.lacksProcesses && <em className="enterprise-badge enterprise-badge-warn">no process</em>}
                        {capability.flags.lacksApplications && <em className="enterprise-badge enterprise-badge-warn">no application</em>}
                        {capability.flags.lacksRequirements && <em className="enterprise-badge enterprise-badge-warn">no requirement</em>}
                        {!capability.flags.lacksOwner && !capability.flags.lacksProcesses &&
                          !capability.flags.lacksApplications && !capability.flags.lacksRequirements && (
                            <em className="enterprise-badge">complete</em>
                          )}
                      </span>
                      {overlays.applications && capability.applicationNames.length > 0 && (
                        <small className="enterprise-capability-meta">
                          Applications: {capability.applicationNames.join(", ")}
                        </small>
                      )}
                      {capability.processNames.length > 0 && (
                        <small className="enterprise-capability-meta">
                          Processes: {capability.processNames.join(", ")}
                        </small>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {overlays.risks && risksAvailable && (
        <section className="enterprise-gaps-block">
          <strong>Risks and gaps</strong>
          <ul>
            {riskPrinciples.map((principle) => (
              <li key={principle.object_id}>Risk: {principle.name}</li>
            ))}
            {(impact?.gaps ?? []).map((gap) => (
              <li key={gap}>{gap}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

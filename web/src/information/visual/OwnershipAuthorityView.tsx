import type { InformationOwnership } from "../informationModel";
import { OWNERSHIP_ISSUE_LABELS } from "../informationViews";

type Props = {
  ownership: InformationOwnership;
  selectedObjectId: string | null;
  onSelectEntity: (objectId: string) => void;
};

export default function OwnershipAuthorityView({
  ownership,
  selectedObjectId,
  onSelectEntity,
}: Props) {
  return (
    <section className="information-ownership" aria-label="Ownership and authority">
      {ownership.entries.length === 0 ? (
        <p className="information-projection-empty">No information entities in this state.</p>
      ) : (
        <table className="information-ownership-matrix">
          <thead>
            <tr>
              <th scope="col">Entity</th>
              <th scope="col">Owner</th>
              <th scope="col">Steward</th>
              <th scope="col">Authoritative system</th>
              <th scope="col">Classification</th>
              <th scope="col">Sensitivity</th>
              <th scope="col">Realizations</th>
              <th scope="col">Gaps</th>
            </tr>
          </thead>
          <tbody>
            {ownership.entries.map((entry) => (
              <tr
                key={entry.object_id}
                className={`${entry.issues.length > 0 ? "has-issues" : ""}${
                  entry.object_id === selectedObjectId ? " selected" : ""
                }`}
                data-issues={entry.issues.join(" ")}
              >
                <th scope="row">
                  <button type="button" onClick={() => onSelectEntity(entry.object_id)}>
                    {entry.name}
                  </button>
                </th>
                <td className={entry.owner ? "" : "is-missing"}>{entry.owner ?? "—"}</td>
                <td className={entry.steward ? "" : "is-missing"}>{entry.steward ?? "—"}</td>
                <td
                  className={
                    entry.authoritative_system_id
                      ? entry.authoritative_in_state
                        ? ""
                        : "is-warning"
                      : "is-missing"
                  }
                >
                  {entry.authoritative_system_name ?? "—"}
                  {entry.authoritative_system_id && !entry.authoritative_in_state && (
                    <em> not in state</em>
                  )}
                </td>
                <td>{entry.classification ?? "—"}</td>
                <td>{entry.sensitivity ?? "—"}</td>
                <td>{entry.realization_count}</td>
                <td>
                  {entry.issues.length === 0 ? (
                    <span className="information-ownership-ok">No gaps</span>
                  ) : (
                    <ul className="information-ownership-issues">
                      {entry.issues.map((issue) => (
                        <li key={issue} data-issue={issue}>
                          {OWNERSHIP_ISSUE_LABELS[issue] ?? issue}
                        </li>
                      ))}
                    </ul>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

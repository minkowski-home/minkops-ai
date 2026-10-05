import type { Catalog, Column } from "./types";

export function CatalogReview({
  catalog,
  provenance,
  filter,
  onChange
}: {
  catalog: Catalog;
  provenance: { id: string; path: string }[];
  filter: string;
  onChange: (value: Catalog) => void;
}) {
  const change = (index: number, update: (sheet: Catalog["sheets"][number]) => void) => {
    const next = structuredClone(catalog);
    update(next.sheets[index]);
    onChange(next);
  };
  return (
    <div className="accounts-catalog">
      {catalog.sheets.map((sheet, index) => {
        if (
          ![
            sheet.sheet,
            sheet.table,
            provenance.find((f) => f.id === sheet.file_id)?.path
          ]
            .join(" ")
            .toLowerCase()
            .includes(filter.toLowerCase())
        )
          return null;
        return (
          <details
            key={`${sheet.file_id}:${sheet.sheet}:${sheet.table ?? ""}`}
            open={sheet.role === "destination"}
          >
            <summary>
              {sheet.sheet}
              {sheet.table ? ` / ${sheet.table}` : ""} · {sheet.columns.length} columns ·{" "}
              {sheet.role}
            </summary>
            <p className="quiet-state">
              {provenance.find((f) => f.id === sheet.file_id)?.path}
            </p>
            {sheet.columns.some(
              (column, index) =>
                column.concept &&
                sheet.columns.some(
                  (other, i) => i !== index && other.concept === column.concept
                )
            ) && (
              <p role="alert">
                A business meaning is assigned to multiple columns. Give each mapped
                meaning one column, or clear the meaning for unrelated fields before
                confirming.
              </p>
            )}
            <div className="accounts-field-grid">
              <label>
                Purpose
                <select
                  value={sheet.role}
                  onChange={(e) =>
                    change(index, (s) => {
                      s.role = e.target.value as typeof s.role;
                    })
                  }
                >
                  <option value="reference">Reference data</option>
                  <option value="destination">Bill-entry destination</option>
                  <option value="ignore">Ignore</option>
                </select>
              </label>
              <label>
                Header row
                <input
                  type="number"
                  min="1"
                  value={sheet.header_row}
                  onChange={(e) =>
                    change(index, (s) => {
                      s.header_row = Number(e.target.value);
                    })
                  }
                />
              </label>
            </div>
            <div className="accounts-table">
              <table>
                <thead>
                  <tr>
                    <th>Column</th>
                    <th>Value type</th>
                    <th>Business meaning</th>
                    <th>Required</th>
                    <th>Record key</th>
                  </tr>
                </thead>
                <tbody>
                  {sheet.columns.map((column, c) => (
                    <tr key={c}>
                      <td>
                        <input
                          aria-label={`Column ${c + 1} in ${sheet.sheet}`}
                          value={column.name}
                          onChange={(e) =>
                            change(index, (s) => {
                              s.columns[c].name = e.target.value;
                            })
                          }
                        />
                      </td>
                      <td>
                        <select
                          aria-label={`Type for ${column.name}`}
                          value={column.type}
                          onChange={(e) =>
                            change(index, (s) => {
                              s.columns[c].type = e.target.value as Column["type"];
                            })
                          }
                        >
                          {["string", "number", "integer", "boolean"].map((v) => (
                            <option key={v}>{v}</option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <input
                          aria-label={`Meaning for ${column.name}`}
                          value={column.concept}
                          onChange={(e) =>
                            change(index, (s) => {
                              s.columns[c].concept = e.target.value;
                            })
                          }
                        />
                      </td>
                      <td>
                        <input
                          aria-label={`Require ${column.name}`}
                          type="checkbox"
                          checked={column.required}
                          onChange={(e) =>
                            change(index, (s) => {
                              s.columns[c].required = e.target.checked;
                            })
                          }
                        />
                      </td>
                      <td>
                        <input
                          aria-label={`Use ${column.name} as record key`}
                          type="checkbox"
                          checked={sheet.key_columns.includes(column.name)}
                          onChange={(e) =>
                            change(index, (s) => {
                              s.key_columns = e.target.checked
                                ? [...s.key_columns, column.name]
                                : s.key_columns.filter((v) => v !== column.name);
                            })
                          }
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        );
      })}
    </div>
  );
}

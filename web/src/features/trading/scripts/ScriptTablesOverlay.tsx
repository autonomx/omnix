import type { IndicatorOutput } from '../indicators/coreIndicators';
import './ScriptTablesOverlay.css';

/**
 * Omnix Script tables (table.new, TVP-11.1) over the chart, each at its position (top_right, middle_center, ...), with
 * its cells' text and colours; tables at the same position stack in the order they come. Tables don't take the pointer,
 * so the chart stays usable under them.
 */
export function ScriptTablesOverlay({ outputs }: { outputs: readonly IndicatorOutput[] }) {
  const slots = new Map<string, IndicatorOutput[]>();
  for (const output of outputs) {
    if (output.kind !== 'table' || !output.table || output.visible === false) continue;
    slots.set(output.table.position, [...(slots.get(output.table.position) ?? []), output]);
  }
  if (slots.size === 0) return null;
  return (
    <div className="trading-script-tables">
      {[...slots].map(([position, tables]) => (
        <div key={position} className={`trading-script-table-slot is-${position.replace('_', '-')}`}>
          {tables.map((output) => <ScriptTable key={output.key} output={output} />)}
        </div>
      ))}
    </div>
  );
}

function ScriptTable({ output }: { output: IndicatorOutput }) {
  const table = output.table!;
  return (
    <table
      className="trading-script-table"
      aria-label={output.title}
      style={{ ...(table.background ? { background: table.background } : {}), ...(table.border ? { borderColor: table.border } : {}) }}
    >
      <tbody>
        {table.rows.map((row, rowIndex) => (
          <tr key={rowIndex}>
            {row.map((cell, columnIndex) => (
              <td key={columnIndex} style={{ ...(cell?.color ? { color: cell.color } : {}), ...(cell?.background ? { background: cell.background } : {}) }}>
                {cell?.text ?? ''}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

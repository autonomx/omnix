// The settings dialog's Visibility and Template sections (TVP-3.8), for every tool.
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { tradingApi } from '../tradingApi';
import type { DrawingProperties, DrawingStyle, TradingDrawing } from './drawingCommands';
import { drawingTemplatePayload, drawingTemplateRecordId, parseDrawingTemplate, resetToolDefaults, type DrawingTemplate } from './drawingTemplates';
import { VISIBILITY_UNITS, onlyOnInterval, type DrawingVisibility, type UnitVisibility } from './drawingVisibility';

/** Per-unit checkboxes with count ranges, as TradingView's Visibility tab, plus "only this interval". */
export function DrawingVisibilitySection({ visibility, interval, onChange }: {
  visibility: DrawingVisibility | undefined;
  interval: string;
  onChange: (visibility: DrawingVisibility) => void;
}) {
  const current = visibility ?? {};
  const update = (unit: keyof DrawingVisibility, patch: Partial<UnitVisibility>) => {
    onChange({ ...current, [unit]: { visible: current[unit]?.visible ?? true, ...current[unit], ...patch } });
  };
  return (
    <fieldset className="trading-drawing-visibility">
      <legend>Visibility</legend>
      {VISIBILITY_UNITS.map(({ unit, label, min, max }) => {
        const setting = current[unit];
        const visible = setting?.visible !== false;
        return (
          <div key={unit} className="trading-drawing-visibility-row">
            <label>
              <input type="checkbox" aria-label={`Show on ${label.toLowerCase()}`} checked={visible} onChange={(event) => update(unit, { visible: event.target.checked })} />
              <span>{label}</span>
            </label>
            {min !== undefined && max !== undefined ? (
              <span className="trading-drawing-visibility-range">
                <input
                  type="number" aria-label={`${label} from`} min={min} max={max} disabled={!visible}
                  value={setting?.from ?? min}
                  onChange={(event) => update(unit, { from: Math.min(max, Math.max(min, Number(event.target.value) || min)) })}
                />
                <span aria-hidden="true">–</span>
                <input
                  type="number" aria-label={`${label} to`} min={min} max={max} disabled={!visible}
                  value={setting?.to ?? max}
                  onChange={(event) => update(unit, { to: Math.min(max, Math.max(min, Number(event.target.value) || max)) })}
                />
              </span>
            ) : null}
          </div>
        );
      })}
      <div className="trading-drawing-visibility-actions">
        <button type="button" onClick={() => onChange(onlyOnInterval(interval))}>Only this interval</button>
        <button type="button" onClick={() => onChange({})}>All intervals</button>
      </div>
    </fieldset>
  );
}

/** Save the drawing's style and properties as a named template of its tool, apply one, or reset the tool's default. */
export function DrawingTemplateSection({ drawing, onApply }: {
  drawing: TradingDrawing;
  onApply: (style: DrawingStyle, properties: DrawingProperties) => void;
}) {
  const [name, setName] = useState('');
  const [status, setStatus] = useState<'idle' | 'saving' | 'error' | 'saved'>('idle');
  const records = useQuery({
    queryKey: ['trading', 'indicator-presets'],
    queryFn: () => tradingApi.documents('indicator-presets'),
    staleTime: 30_000,
  });
  const templates: DrawingTemplate[] = (records.data ?? []).flatMap((record) => {
    const template = parseDrawingTemplate(record);
    return template && template.toolType === drawing.toolType ? [template] : [];
  });
  const save = async () => {
    const label = name.trim();
    if (!label) return;
    setStatus('saving');
    try {
      await tradingApi.createDocument('indicator-presets', drawingTemplateRecordId(label), drawingTemplatePayload(label, drawing));
      setName('');
      setStatus('saved');
      void records.refetch();
    } catch {
      setStatus('error');
    }
  };
  return (
    <fieldset className="trading-drawing-templates">
      <legend>Template</legend>
      {templates.length > 0 ? (
        <ul>
          {templates.map((template) => (
            <li key={template.recordId}>
              <button type="button" onClick={() => onApply(template.style, template.properties)}>Apply {template.name}</button>
            </li>
          ))}
        </ul>
      ) : null}
      <label className="trading-drawing-properties-row">
        <span>Save as</span>
        <input aria-label="Template name" value={name} onChange={(event) => setName(event.target.value)} placeholder="Template name" />
      </label>
      <button type="button" onClick={() => { void save(); }} disabled={!name.trim() || status === 'saving'}>Save template</button>
      <button type="button" onClick={() => resetToolDefaults(drawing.toolType)} title="New drawings of this tool use the built-in style again">Reset tool default</button>
      {status === 'error' ? <span role="alert">The template wasn't saved.</span> : null}
      {status === 'saved' ? <span role="status">Template saved.</span> : null}
    </fieldset>
  );
}

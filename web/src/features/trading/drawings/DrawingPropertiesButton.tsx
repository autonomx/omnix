// Generic drawing settings (TVP-0.4): a dialog built from the selected
// drawing's tool `propertySchema`, so every tool gets settings without UI code.
import { useState } from 'react';
import type { TradingDrawing } from './drawingCommands';
import { booleanProperty, numberListProperty, numberProperty, recordsProperty, stringProperty } from './tools/properties';
import { drawingPropertiesWithDefaults, drawingToolDefinition } from './tools/registry';
import type { DrawingProperties, DrawingPropertyField, DrawingPropertyRecord, DrawingPropertyValue, DrawingRecordField } from './tools/types';
import './DrawingPropertiesButton.css';

function parseNumberList(text: string): number[] {
  return text.split(',').map((item) => item.trim()).filter((item) => item !== '').map(Number).filter(Number.isFinite);
}

function RecordFieldInput({ field, record, onChange }: {
  field: DrawingRecordField;
  record: DrawingPropertyRecord;
  onChange: (value: string | number | boolean) => void;
}) {
  const value = record[field.key];
  const label = field.label;
  switch (field.type) {
    case 'boolean':
      return <input aria-label={label} type="checkbox" checked={value === true} onChange={(event) => onChange(event.target.checked)} />;
    case 'number':
      return (
        <input
          aria-label={label}
          type="number"
          step={field.step ?? 'any'}
          min={field.min}
          max={field.max}
          value={typeof value === 'number' ? value : ''}
          onChange={(event) => {
            const parsed = Number(event.target.value);
            if (event.target.value !== '' && Number.isFinite(parsed)) onChange(parsed);
          }}
        />
      );
    case 'color':
      return <input aria-label={label} type="color" value={typeof value === 'string' && value ? value : '#66d9e8'} onChange={(event) => onChange(event.target.value)} />;
    case 'text':
      return <input aria-label={label} type="text" value={typeof value === 'string' ? value : ''} onChange={(event) => onChange(event.target.value)} />;
  }
}

function PropertyInput({ field, properties, onChange }: {
  field: DrawingPropertyField;
  properties: DrawingProperties;
  onChange: (value: DrawingPropertyValue) => void;
}) {
  const { key, label } = field;
  switch (field.type) {
    case 'boolean':
      return <input aria-label={label} type="checkbox" checked={booleanProperty(properties, key, false)} onChange={(event) => onChange(event.target.checked)} />;
    case 'number':
      return (
        <input
          aria-label={label}
          type="number"
          step={field.step ?? 'any'}
          min={field.min}
          max={field.max}
          value={numberProperty(properties, key, 0)}
          onChange={(event) => {
            const parsed = Number(event.target.value);
            if (event.target.value !== '' && Number.isFinite(parsed)) onChange(parsed);
          }}
        />
      );
    case 'number-list':
      return (
        <input
          aria-label={label}
          type="text"
          defaultValue={numberListProperty(properties, key, []).join(', ')}
          onBlur={(event) => onChange(parseNumberList(event.target.value))}
        />
      );
    case 'select':
      return (
        <select aria-label={label} value={stringProperty(properties, key, '')} onChange={(event) => onChange(event.target.value)}>
          {field.options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
        </select>
      );
    case 'color':
      return <input aria-label={label} type="color" value={stringProperty(properties, key, '#66d9e8') || '#66d9e8'} onChange={(event) => onChange(event.target.value)} />;
    case 'text':
      return <input aria-label={label} type="text" value={stringProperty(properties, key, '')} onChange={(event) => onChange(event.target.value)} />;
    case 'records': {
      const records = recordsProperty(properties, key, []);
      return (
        <div className="trading-drawing-properties-records" role="group" aria-label={label}>
          {records.map((record, index) => (
            <div key={index} className="trading-drawing-properties-record">
              {field.fields.map((recordField) => (
                <RecordFieldInput
                  key={recordField.key}
                  field={{ ...recordField, label: `${label} ${index + 1} ${recordField.label}` }}
                  record={record}
                  onChange={(value) => onChange(records.map((item, position) => position === index ? { ...item, [recordField.key]: value } : item))}
                />
              ))}
              <button type="button" aria-label={`Remove ${label} ${index + 1}`} onClick={() => onChange(records.filter((_, position) => position !== index))}>×</button>
            </div>
          ))}
          <button type="button" onClick={() => onChange([...records, field.newRecord])}>Add</button>
        </div>
      );
    }
  }
}

/** A "Settings" button and dialog for the selected drawing; nothing when its tool has no properties. */
export function DrawingPropertiesButton({ drawing, onChange }: { drawing: TradingDrawing; onChange: (properties: DrawingProperties) => void }) {
  const [open, setOpen] = useState(false);
  const definition = drawingToolDefinition(drawing.toolType);
  if (!definition || definition.propertySchema.length === 0) return null;
  const properties = drawingPropertiesWithDefaults(drawing.toolType, drawing.properties);
  return (
    <span className="trading-drawing-properties-anchor">
      <button type="button" aria-expanded={open} onClick={() => setOpen((value) => !value)}>Settings</button>
      {open ? (
        <div className="trading-drawing-properties" role="dialog" aria-label={`${definition.label} settings`}>
          {definition.propertySchema.map((field) => {
            const input = <PropertyInput field={field} properties={properties} onChange={(value) => onChange({ ...properties, [field.key]: value })} />;
            return field.type === 'records'
              ? <div key={field.key} className="trading-drawing-properties-row"><span>{field.label}</span>{input}</div>
              : <label key={field.key} className="trading-drawing-properties-row"><span>{field.label}</span>{input}</label>;
          })}
          <button type="button" onClick={() => setOpen(false)}>Close</button>
        </div>
      ) : null}
    </span>
  );
}

import { describe, expect, it } from 'vitest';
import { applyConditionDrafts, conditionDraft, conditionEditorFields, draftCondition, newConditionDraft } from './alertConditionDrafts';

const price = (overrides = {}) => ({ condition_type: 'price_above' as string, threshold: '100', parameters: { lookback_bars: 3 }, conditions: undefined as unknown, ...overrides });

describe('multi-condition alert drafts (TVP-1.6)', () => {
  it('turns drafts into conditions and back', () => {
    const moving = { ...newConditionDraft(), source: 'change' as const, lookback: '5', operator: 'moving_up_percent' as const, amount: '2', bars: '3' };
    const condition = draftCondition(moving);
    expect(condition).toEqual({ source: { kind: 'change_percent', lookback_bars: 5 }, operator: 'moving_up_percent', amount: '2', bars: 3 });
    expect(conditionDraft(condition as never)).toMatchObject({ source: 'change', lookback: '5', operator: 'moving_up_percent', amount: '2', bars: '3' });
    expect(draftCondition({ ...newConditionDraft(), operator: 'entering_channel', upper: '1', lower: '2' })).toMatch(/upper value is above/);
    expect(draftCondition({ ...newConditionDraft(), value: '' })).toMatch(/needs a value/);
    expect(draftCondition({ ...newConditionDraft(), source: 'indicator' })).toMatch(/indicator/);
    // A trendline condition can't be edited in the dialog: the alert keeps it.
    expect(conditionEditorFields({ condition_type: 'conditions', conditions: [{ source: { kind: 'trendline', points: [] }, operator: 'crossing', target: null, amount: null, bars: null }] as never })).toEqual({ conditionDrafts: [], conditionsEditable: false });
  });

  it('makes a legacy alert with extra conditions a conditions alert, its own condition first', () => {
    const input = price();
    expect(applyConditionDrafts(input as never, { condition: 'price_above', conditionDrafts: [{ ...newConditionDraft('50'), source: 'volume', operator: 'greater_than' }] })).toBeNull();
    expect(input).toMatchObject({
      condition_type: 'conditions',
      threshold: '0',
      conditions: [
        { source: { kind: 'price', field: 'close' }, operator: 'crossing_up', target: { kind: 'value', value: '100' } },
        { source: { kind: 'price', field: 'volume' }, operator: 'greater_than', target: { kind: 'value', value: '50' } },
      ],
    });
    const change = price({ condition_type: 'percent_change_below' });
    applyConditionDrafts(change as never, { condition: 'percent_change_below', conditionDrafts: [newConditionDraft('1')] });
    expect((change.conditions as Array<{ source: unknown; operator: string }>)[0]).toMatchObject({ source: { kind: 'change_percent', lookback_bars: 3 }, operator: 'crossing_down' });
    // Without extra conditions a legacy alert is left as it is.
    const untouched = price();
    expect(applyConditionDrafts(untouched as never, { condition: 'price_above', conditionDrafts: [] })).toBeNull();
    expect(untouched.condition_type).toBe('price_above');
  });

  it('refuses more than five conditions, an invalid draft, and extra conditions on a drawing alert', () => {
    const six = Array.from({ length: 5 }, () => newConditionDraft('1'));
    expect(applyConditionDrafts(price() as never, { condition: 'price_above', conditionDrafts: six })).toMatch(/at most 5/);
    expect(applyConditionDrafts(price() as never, { condition: 'price_above', conditionDrafts: [newConditionDraft('')] })).toMatch(/needs a value/);
    expect(applyConditionDrafts(price({ condition_type: 'trendline_crossing' }) as never, { condition: 'trendline_crossing', conditionDrafts: [newConditionDraft('1')] })).toMatch(/one condition/);
  });
});

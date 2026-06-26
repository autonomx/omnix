import { describe, expect, it } from 'vitest';
import { parseScriptSpeakers } from './scriptLines';

describe('parseScriptSpeakers', () => {
  it('detects unique names and line counts', () => {
    expect(parseScriptSpeakers('dave: hello there\nbob: how do you do\nmarry: fine\ndave: topic')).toEqual([
      { name: 'dave', count: 2 },
      { name: 'bob', count: 1 },
      { name: 'marry', count: 1 },
    ]);
  });

  it('ignores empty and untagged lines', () => {
    expect(parseScriptSpeakers('intro\n: missing\nanna: hello\nempty:   ')).toEqual([{ name: 'anna', count: 1 }]);
  });
});

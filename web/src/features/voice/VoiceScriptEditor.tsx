/**
 * Voice Studio's script editor: CodeMirror 6 with the script grammar highlighted
 * (speaker tags and `{pause …}` tokens) and Ctrl+Enter to generate.
 */
import { history, historyKeymap, defaultKeymap } from '@codemirror/commands';
import { EditorState, Prec, RangeSetBuilder } from '@codemirror/state';
import { Decoration, EditorView, ViewPlugin, keymap, lineNumbers, placeholder, type DecorationSet, type ViewUpdate } from '@codemirror/view';
import { useEffect, useEffectEvent, useRef } from 'react';

const speakerMark = Decoration.mark({ class: 'voice-script-speaker' });
const pauseMark = Decoration.mark({ class: 'voice-script-pause' });
const PAUSE = /\{\s*pause\s+\d+(?:\.\d+)?\s*(?:ms|s)\s*\}/gi;

function scriptDecorations(view: EditorView): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>();
  for (const { from, to } of view.visibleRanges) {
    let position = from;
    while (position <= to) {
      const line = view.state.doc.lineAt(position);
      const marks: Array<[number, number, Decoration]> = [];
      const colon = line.text.indexOf(':');
      const name = colon > 0 ? line.text.slice(0, colon).trim() : '';
      if (name && name.length <= 50 && !name.includes('{') && line.text.slice(colon + 1).trim()) {
        const start = line.from + line.text.indexOf(name);
        marks.push([start, start + name.length, speakerMark]);
      }
      for (const match of line.text.matchAll(PAUSE)) {
        const start = line.from + (match.index ?? 0);
        marks.push([start, start + match[0].length, pauseMark]);
      }
      marks.sort((left, right) => left[0] - right[0]);
      for (const [start, end, mark] of marks) builder.add(start, end, mark);
      position = line.to + 1;
    }
  }
  return builder.finish();
}

const scriptHighlighting = ViewPlugin.fromClass(class {
  decorations: DecorationSet;

  constructor(view: EditorView) {
    this.decorations = scriptDecorations(view);
  }

  update(update: ViewUpdate) {
    if (update.docChanged || update.viewportChanged) this.decorations = scriptDecorations(update.view);
  }
}, { decorations: (plugin) => plugin.decorations });

const theme = EditorView.theme({
  '&': { minHeight: '14rem', fontSize: '13px', backgroundColor: 'transparent' },
  '.cm-scroller': { fontFamily: 'ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace', lineHeight: '1.7' },
  '.cm-gutters': { backgroundColor: 'transparent', border: 'none', color: 'color-mix(in srgb, currentColor 45%, transparent)' },
  '.voice-script-speaker': { color: 'var(--c-indigo-600)', fontWeight: '700' },
  '.voice-script-pause': { color: 'var(--c-amber-770)', fontStyle: 'italic' },
});

export function VoiceScriptEditor({ value, onChange, onGenerate, label = 'Script' }: {
  value: string;
  onChange: (value: string) => void;
  onGenerate: () => void;
  label?: string;
}) {
  const host = useRef<HTMLDivElement | null>(null);
  const view = useRef<EditorView | null>(null);
  const latest = useRef({ onChange, onGenerate });
  latest.current = { onChange, onGenerate };

  const createEditor = useEffectEvent((parent: HTMLElement) => new EditorView({
    parent,
    state: EditorState.create({
      doc: value,
      extensions: [
        lineNumbers(),
        history(),
        Prec.high(keymap.of([{ key: 'Mod-Enter', preventDefault: true, run: () => { latest.current.onGenerate(); return true; } }])),
        keymap.of([...defaultKeymap, ...historyKeymap]),
        EditorView.lineWrapping,
        placeholder('Narrator: Write a line…\nDave: Tag a line with a speaker name.\n{pause 600ms}'),
        scriptHighlighting,
        theme,
        EditorView.contentAttributes.of({ 'aria-label': label, 'aria-multiline': 'true' }),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) latest.current.onChange(update.state.doc.toString());
        }),
      ],
    }),
  }));

  useEffect(() => {
    if (!host.current) return undefined;
    const editor = createEditor(host.current);
    view.current = editor;
    return () => {
      editor.destroy();
      view.current = null;
    };
  }, []);

  // A new script from outside (load, clear, a saved script).
  useEffect(() => {
    const editor = view.current;
    if (!editor || editor.state.doc.toString() === value) return;
    editor.dispatch({ changes: { from: 0, to: editor.state.doc.length, insert: value } });
  }, [value]);

  return <div ref={host} className="voice-script-editor" />;
}

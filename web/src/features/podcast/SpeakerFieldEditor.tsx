import { Button, Group, Modal, Textarea } from '@mantine/core';

/** A speaker's free-text fields, in the order the participant table shows them. */
export const speakerTextFields = [
  { field: 'identity', label: 'Identity' },
  { field: 'beliefs', label: 'Beliefs' },
  { field: 'personality', label: 'Personality' },
  { field: 'speakingStyle', label: 'Speaking style' },
  { field: 'goal', label: 'Goal this episode' },
  { field: 'instructions', label: 'Instructions' },
] as const;

export type SpeakerTextField = (typeof speakerTextFields)[number]['field'];

export const expandHint = 'Double-click to edit in a larger box';

/** One speaker field in a large box (double-click a cell in the participant table); edits apply as you type. */
export function SpeakerFieldEditor({ speakerName, field, value, onChange, onClose }: {
  speakerName: string;
  field: SpeakerTextField | null;
  value: string;
  onChange: (value: string) => void;
  onClose: () => void;
}) {
  const label = speakerTextFields.find((entry) => entry.field === field)?.label ?? '';
  return (
    <Modal opened={field !== null} onClose={onClose} title={`${speakerName}: ${label}`} size="xl" centered>
      <Textarea
        data-autofocus
        aria-label={`${speakerName} ${label.toLowerCase()} (expanded)`}
        rows={16}
        resize="vertical"
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
      />
      <Group justify="flex-end" mt="md">
        <Button onClick={onClose}>Done</Button>
      </Group>
    </Modal>
  );
}

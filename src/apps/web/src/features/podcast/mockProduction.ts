import type { ProductionStage } from '../conversation-production/types';

export interface MockProductionStage {
  id: ProductionStage | 'podcast_renderer';
  label: string;
  state: 'done' | 'active' | 'pending' | 'failed';
}

export interface MockTranscriptLine {
  timestamp: string;
  speaker: string;
  text: string;
}

export interface MockQualityGate {
  label: string;
  status: 'Pass' | 'Warning';
}

export interface MockSessionMetric {
  label: string;
  value: string;
}

export interface MockProductionAssetTile {
  label: string;
  status: string;
  action: string;
  color: 'purple' | 'green' | 'cyan' | 'orange' | 'blue';
}

export interface MockDownloadAssetTile {
  label: string;
  metadata: string;
  icon: string;
}

export interface MockRecentPodcastJob {
  name: string;
  status: string;
  duration: string;
}

export const mockProductionStages: MockProductionStage[] = [
  { id: 'research', label: 'Research', state: 'done' },
  { id: 'producer_plan', label: 'Producer Plan', state: 'done' },
  { id: 'canonical_script', label: 'Canonical Script', state: 'done' },
  { id: 'performance_script', label: 'Performance Script', state: 'active' },
  { id: 'voice_takes', label: 'Voice Takes', state: 'pending' },
  { id: 'mix', label: 'Mix', state: 'pending' },
  { id: 'podcast_renderer', label: 'Podcast Renderer', state: 'pending' },
];

export const mockDirectorNote = 'Approved producer plan. Rebalancing Guest B speaking time and validating citation coverage.';

export const mockTranscriptLines: MockTranscriptLine[] = [
  {
    timestamp: '06:12',
    speaker: 'Host',
    text: 'Welcome everyone to today’s discussion on the future of AI in everyday life.',
  },
  {
    timestamp: '06:25',
    speaker: 'Guest A',
    text: 'AI is already woven into the fabric of our daily routines — from assistants and recommendations to copilots that amplify productivity.',
  },
  {
    timestamp: '06:38',
    speaker: 'Guest B',
    text: 'That’s true, but we also need to be cautious. These systems can reinforce biases, reduce human agency, and create risky dependencies.',
  },
  {
    timestamp: '06:55',
    speaker: 'Host',
    text: 'Great points from both sides. Let’s dig into where the biggest opportunities and risks are heading.',
  },
];

export const mockQualityGates: MockQualityGate[] = [
  { label: 'Repetition', status: 'Pass' },
  { label: 'Speaker balance', status: 'Warning' },
  { label: 'Citation coverage', status: 'Pass' },
  { label: 'Duration estimate', status: 'Pass' },
  { label: 'Audience fit', status: 'Pass' },
  { label: 'Contradictions', status: 'Pass' },
];

export const mockSessionMetrics: MockSessionMetric[] = [
  { label: 'Speaker balance', value: '72%' },
  { label: 'Avg turn', value: '23s' },
  { label: 'Interruption rate', value: '12%' },
  { label: 'Pacing score', value: '82%' },
  { label: 'Repetition score', value: '18%' },
  { label: 'Duration drift', value: '+0:54' },
];

export const mockProductionAssetTiles: MockProductionAssetTile[] = [
  { label: 'Research', status: 'Generated', action: 'View', color: 'purple' },
  { label: 'Producer Plan', status: 'Approved', action: 'Open', color: 'green' },
  { label: 'Canonical Script', status: 'Approved', action: 'Edit', color: 'cyan' },
  { label: 'Performance Script', status: 'In Progress', action: 'Edit', color: 'orange' },
  { label: 'Voice Takes', status: 'Generated', action: 'Review', color: 'blue' },
  { label: 'Transcript', status: 'Generated', action: 'Edit', color: 'green' },
  { label: 'Show Notes', status: 'Editable', action: 'Edit', color: 'purple' },
  { label: 'Citations', status: 'Generated', action: 'View', color: 'blue' },
];

export const mockDownloadAssetTiles: MockDownloadAssetTile[] = [
  { label: 'MP3', metadata: 'Audio file', icon: '♫' },
  { label: 'WAV', metadata: 'High quality', icon: '▥' },
  { label: 'Transcript', metadata: 'TXT file', icon: '▤' },
  { label: 'Show Notes', metadata: 'Markdown', icon: '▣' },
  { label: 'Citations', metadata: 'BibTeX', icon: '⌁' },
  { label: 'Chapters', metadata: 'JSON', icon: '§' },
];

export const mockRecentPodcastJobs: MockRecentPodcastJob[] = [
  { name: 'The Future of AI in Everyday Life', status: 'LIVE', duration: '20 min' },
  { name: 'AI and the Future of Work', status: 'Completed', duration: '42 min' },
  { name: 'Creativity in the Age of AI', status: 'Completed', duration: '37 min' },
];

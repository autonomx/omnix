export interface OutputDefaults {
  stability: number;
  similarity: number;
  style: number;
  speed: number;
  pitch: number;
  volume: number;
}

export const DEFAULT_OUTPUT_SETTINGS: OutputDefaults = {
  stability: 0.75,
  similarity: 0.8,
  style: 0.35,
  speed: 1,
  pitch: 0,
  volume: 0,
};

export const IMAGE_SIZE_PRESETS = [
  { id: 'square-768', label: 'Square 768 x 768', width: 768, height: 768 },
  { id: 'portrait-768', label: 'Portrait 768 x 1024', width: 768, height: 1024 },
  { id: 'landscape-768', label: 'Landscape 1024 x 768', width: 1024, height: 768 },
  { id: 'square-1024', label: 'Square HD 1024 x 1024', width: 1024, height: 1024 },
] as const;

export interface ImageRequestDefaults {
  providerId: string;
  width: number;
  height: number;
  unloadAfterGeneration: boolean;
}

export interface ImageRequestFormValues {
  providerId: string;
  prompt: string;
  negativePrompt: string;
  preset: string;
  width: string;
  height: string;
  style: string;
  seed: string;
  steps: string;
  guidanceScale: string;
  unloadAfterGeneration: boolean;
  noCache: boolean;
}

export function imageRequestDefaultValues(defaults: ImageRequestDefaults): ImageRequestFormValues {
  return {
    providerId: defaults.providerId,
    prompt: '',
    negativePrompt: '',
    preset: 'custom',
    width: String(defaults.width),
    height: String(defaults.height),
    style: '',
    seed: '',
    steps: '',
    guidanceScale: '',
    unloadAfterGeneration: defaults.unloadAfterGeneration,
    noCache: false,
  };
}

export function imagePresetById(presetId: string) {
  return IMAGE_SIZE_PRESETS.find((preset) => preset.id === presetId);
}

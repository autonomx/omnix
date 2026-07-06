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
    preset: matchingImagePreset(defaults.width, defaults.height)?.id ?? 'custom',
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

export function buildImageGenerateInput(values: ImageRequestFormValues, defaults: ImageRequestDefaults) {
  return {
    prompt: values.prompt.trim(),
    negative_prompt: values.negativePrompt.trim(),
    provider_id: values.providerId.trim() || null,
    width: parseDimension(values.width, defaults.width),
    height: parseDimension(values.height, defaults.height),
    style: values.style.trim(),
    seed: optionalInteger(values.seed),
    steps: optionalInteger(values.steps),
    guidance_scale: optionalNumber(values.guidanceScale),
    unload_after_generation: values.unloadAfterGeneration,
    no_cache: values.noCache,
  };
}

export function matchingImagePreset(width: number, height: number) {
  return IMAGE_SIZE_PRESETS.find((preset) => preset.width === width && preset.height === height);
}

export function imagePresetById(presetId: string) {
  return IMAGE_SIZE_PRESETS.find((preset) => preset.id === presetId);
}

export function validateImageDimension(value: string): true | string {
  const parsed = Number.parseInt(value, 10);
  if (!Number.isFinite(parsed) || parsed < 128 || parsed > 4096) return 'Use a value from 128 to 4096.';
  if (parsed % 64 !== 0) return 'Use a multiple of 64.';
  return true;
}

function parseDimension(value: string, fallback: number): number {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function optionalInteger(value: string): number | undefined {
  const normalized = value.trim();
  if (!normalized) return undefined;
  const parsed = Number.parseInt(normalized, 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function optionalNumber(value: string): number | undefined {
  const normalized = value.trim();
  if (!normalized) return undefined;
  const parsed = Number.parseFloat(normalized);
  return Number.isFinite(parsed) ? parsed : undefined;
}

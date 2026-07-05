export type CloneFormValues = {
  providerId: string;
  sampleAssetId: string;
  profileName: string;
  referenceText: string;
  language: string;
  quality: string;
};

export type CloneModuleDefaults = {
  providerId: string;
  language: string;
  quality: string;
};

export function cloneFormDefaults(defaults: CloneModuleDefaults): CloneFormValues {
  return {
    providerId: defaults.providerId,
    sampleAssetId: '',
    profileName: '',
    referenceText: '',
    language: defaults.language,
    quality: defaults.quality,
  };
}

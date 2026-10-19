// The parts of Vite's client types the app uses (the full `vite/client` types are not loaded).
interface ImportMetaEnv {
  readonly DEV: boolean;
}

interface ImportMeta {
  glob<T = unknown>(pattern: string, options?: { eager?: boolean; import?: string }): Record<string, T>;
}

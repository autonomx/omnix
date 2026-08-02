export {};

declare global {
  interface String {
    casefold?: () => string;
  }
}

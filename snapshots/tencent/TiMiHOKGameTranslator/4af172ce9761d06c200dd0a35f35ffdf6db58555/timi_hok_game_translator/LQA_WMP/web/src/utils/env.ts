export function isDevMode(): boolean {
  return import.meta.env.DEV;
}

export function isProdMode(): boolean {
  return import.meta.env.PROD;
}

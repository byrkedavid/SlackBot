export const TIME_ZONE = "America/New_York";

export const SITES = [
  "ATL55",
  "ATL66",
  "ATL77",
  "ATL88",
  "ATL99",
  "ATL118",
  "REMOTE",
  "OFF",
] as const;

export const SITE_EMOJI: Record<string, string> = {
  ATL55: "🏢",
  ATL66: "🏢",
  ATL77: "🏢",
  ATL88: "🏢",
  ATL99: "🏢",
  ATL118: "🏢",
  REMOTE: "🏠",
  OFF: "🏖️",
};

export function localDate(date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((p) => [p.type, p.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

export function friendlyDate(date = new Date()): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: TIME_ZONE,
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

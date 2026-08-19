export const SITES = ["ATL55", "ATL66", "ATL77", "ATL88", "ATL99", "ATL118", "REMOTE", "OFF"] as const;

export const SITE_EMOJI: Record<string, string> = {
  ATL55: "🏢", ATL66: "🏢", ATL77: "🏢", ATL88: "🏢",
  ATL99: "🏢", ATL118: "🏢", REMOTE: "🏠", OFF: "🏖️",
};

export function localDate(date = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric", month: "2-digit", day: "2-digit",
  }).format(date);
}

export function friendlyDate(date = new Date()): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "long", month: "long", day: "numeric", year: "numeric",
  }).format(date);
}

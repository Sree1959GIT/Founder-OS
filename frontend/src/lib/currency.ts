/** Founder F12: the member's currency. Settings → Currency; until chosen, the browser's region decides. */

const REGION_CURRENCY: Record<string, string> = {
  IN: "INR", US: "USD", GB: "GBP", AE: "AED", SA: "SAR", SG: "SGD", AU: "AUD", NZ: "NZD", CA: "CAD", JP: "JPY",
  CN: "CNY", HK: "HKD", CH: "CHF", ZA: "ZAR", BR: "BRL", KR: "KRW", NG: "NGN", PH: "PHP",
  DE: "EUR", FR: "EUR", ES: "EUR", IT: "EUR", NL: "EUR", IE: "EUR", PT: "EUR", BE: "EUR", AT: "EUR", FI: "EUR",
  GR: "EUR", LU: "EUR",
};

/** The currencies offered in Settings (the ones the spend report has a symbol for). */
export const CURRENCIES = ["USD", "INR", "EUR", "GBP", "AED", "SAR", "SGD", "AUD", "NZD", "CAD", "JPY", "CNY", "HKD", "CHF", "ZAR", "BRL", "KRW", "NGN", "PHP"];

/** "en-IN" → INR. Unknown regions (or none) → USD. */
export function browserCurrency(languages: readonly string[] = typeof navigator === "undefined" ? [] : navigator.languages ?? [navigator.language]): string {
  for (const tag of languages) {
    const region = tag.split(/[-_]/)[1]?.toUpperCase();
    if (region && REGION_CURRENCY[region]) return REGION_CURRENCY[region];
  }
  return "USD";
}

/** "about ₹1" from US dollars, as the backend writes it (rounded for reading). */
export function moneyText(usd: number, symbol: string, rate: number): string {
  const amount = usd * rate;
  if (amount <= 0) return `${symbol}0`;
  if (amount < 0.01) return `less than ${symbol}0.01`;
  if (amount < 1) return `about ${symbol}${amount.toFixed(2)}`;
  return `about ${symbol}${Math.round(amount).toLocaleString("en")}`;
}

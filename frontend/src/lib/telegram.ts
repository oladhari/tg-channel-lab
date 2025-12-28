export function normalizeTelegramUsername(input: string): string {
  let s = (input || "").trim();
  if (!s) return "";

  s = s.replace(/^https?:\/\//i, "");
  s = s.replace(/^www\./i, "");

  s = s.replace(/^t\.me\//i, "");
  s = s.replace(/^telegram\.me\//i, "");

  s = s.replace(/^@+/, "");
  s = s.split("?")[0].split("#")[0];

  s = s.replace(/[^a-zA-Z0-9_]/g, "");
  return s.toLowerCase();
}

// frontend/src/lib/time.ts

/**
 * Format a UTC datetime string (or Date) as Japan Standard Time (JST, UTC+9).
 * Returns "—" for null/undefined/invalid values.
 */
export function toJST(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const d = value instanceof Date ? value : new Date(value);
  if (isNaN(d.getTime())) return "—";
  // Manually offset to JST (UTC+9) — avoids relying on ICU locale data in Node.js Docker images
  const jst = new Date(d.getTime() + 9 * 60 * 60 * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return (
    `${jst.getUTCFullYear()}/${p(jst.getUTCMonth() + 1)}/${p(jst.getUTCDate())} ` +
    `${p(jst.getUTCHours())}:${p(jst.getUTCMinutes())}:${p(jst.getUTCSeconds())} JST`
  );
}

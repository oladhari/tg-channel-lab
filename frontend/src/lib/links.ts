// frontend/src/lib/links.ts

export function shortMint(m: string) {
  if (!m) return "";
  return `${m.slice(0, 6)}…${m.slice(-6)}`;
}

// If you still want Dex as a secondary link later
export function dexscreenerSolanaUrl(mint: string) {
  return `https://dexscreener.com/solana/${mint}`;
}

// Your new default:
export function gmgnSolanaTokenUrl(mint: string) {
  return `https://gmgn.ai/sol/token/${mint}`;
}

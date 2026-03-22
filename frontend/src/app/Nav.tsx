"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/",          label: "Dashboard" },
  { href: "/live",      label: "Live Monitor" },
  { href: "/calls",     label: "Calls" },
  { href: "/explorer",  label: "Explorer" },
];

export default function Nav() {
  const path = usePathname();

  return (
    <nav style={{
      position: "sticky",
      top: 0,
      zIndex: 100,
      display: "flex",
      alignItems: "center",
      gap: 0,
      padding: "0 24px",
      height: 52,
      background: "#0f172a",
      borderBottom: "1px solid #1e293b",
      boxShadow: "0 1px 8px rgba(0,0,0,.35)",
    }}>
      {/* Logo */}
      <Link href="/" style={{
        fontWeight: 800,
        fontSize: 15,
        letterSpacing: "0.02em",
        color: "#f8fafc",
        marginRight: 32,
        display: "flex",
        alignItems: "center",
        gap: 8,
        textDecoration: "none",
        whiteSpace: "nowrap",
      }}>
        <span style={{ fontSize: 18 }}>📡</span>
        TG Channel Lab
      </Link>

      {/* Nav links */}
      <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
        {LINKS.map(({ href, label }) => {
          const active = href === "/" ? path === "/" : path.startsWith(href);
          return (
            <Link key={href} href={href} style={{
              padding: "6px 14px",
              borderRadius: 8,
              fontSize: 13,
              fontWeight: active ? 600 : 400,
              color: active ? "#f8fafc" : "#94a3b8",
              background: active ? "#1e40af" : "transparent",
              textDecoration: "none",
              transition: "background .15s, color .15s",
              whiteSpace: "nowrap",
            }}>
              {label}
            </Link>
          );
        })}
      </div>

      {/* Right side — quick links */}
      <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
        <a
          href="http://localhost:8000/docs"
          target="_blank"
          rel="noreferrer"
          style={{ fontSize: 12, color: "#64748b", textDecoration: "none", padding: "4px 10px" }}
        >
          API Docs
        </a>
      </div>
    </nav>
  );
}

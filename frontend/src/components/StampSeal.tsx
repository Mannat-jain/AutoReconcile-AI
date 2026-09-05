/**
 * StampSeal — the one deliberately hand-crafted visual moment in the app.
 * Modeled on a rubber ledger stamp: a rough, slightly-off-register double
 * ring with a tilt, meant to feel like something a controller would
 * physically stamp on a reconciled batch of invoices — not another
 * gradient-and-glow SaaS badge.
 */
export default function StampSeal({
  label,
  sublabel,
  tone = "gold",
}: {
  label: string;
  sublabel?: string;
  tone?: "gold" | "good";
}) {
  const color = tone === "good" ? "#4ADE9E" : "#E8B94A";

  return (
    <div
      className="relative w-[132px] h-[132px] shrink-0 select-none"
      style={{ transform: "rotate(-7deg)" }}
      aria-hidden="true"
    >
      <svg viewBox="0 0 140 140" className="w-full h-full" style={{ mixBlendMode: "screen" }}>
        <defs>
          <filter id="inkRough">
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" result="noise" seed="7" />
            <feDisplacementMap in="SourceGraphic" in2="noise" scale="3.2" />
          </filter>
        </defs>
        <g filter="url(#inkRough)" stroke={color} fill="none" strokeWidth="2.2" opacity="0.85">
          <circle cx="70" cy="70" r="60" />
          <circle cx="70" cy="70" r="51" strokeWidth="1.4" />
        </g>
        <g fill={color} opacity="0.85">
          {Array.from({ length: 28 }).map((_, i) => {
            const angle = (i / 28) * Math.PI * 2;
            const r = 55.5;
            return (
              <circle key={i} cx={70 + r * Math.cos(angle)} cy={70 + r * Math.sin(angle)} r="0.9" />
            );
          })}
        </g>
      </svg>
      <div
        className="absolute inset-0 flex flex-col items-center justify-center text-center px-4"
        style={{ color }}
      >
        <span className="font-display font-bold text-[13.5px] leading-[1.05] tracking-tight">
          {label}
        </span>
        {sublabel && <span className="text-[9px] mt-1 opacity-80 font-ledger">{sublabel}</span>}
      </div>
    </div>
  );
}

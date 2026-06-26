const COLORS = [
  "#f76902", "#fbbf24", "#34d399", "#60a5fa",
  "#f472b6", "#a78bfa", "#fb7185", "#4ade80",
];
const PIECES = 15;

/** Decorative confetti burst — pure CSS animation, no dependencies.
 *  Must be inside a `position:relative; overflow:hidden` container. */
export default function Confetti() {
  return (
    <div
      aria-hidden="true"
      style={{ position: "absolute", inset: 0, overflow: "hidden", pointerEvents: "none" }}
    >
      {Array.from({ length: PIECES }).map((_, i) => {
        const left = `${(i / PIECES) * 100 + Math.random() * (100 / PIECES)}%`;
        const color = COLORS[i % COLORS.length];
        const delay = `${(Math.random() * 0.6).toFixed(2)}s`;
        const duration = `${(1.8 + Math.random() * 1.2).toFixed(2)}s`;
        const size = `${6 + Math.floor(Math.random() * 6)}px`;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              top: 0,
              left,
              width: size,
              height: size,
              borderRadius: i % 2 === 0 ? "50%" : "2px",
              background: color,
              animation: `confettiFall ${duration} ${delay} ease-in forwards`,
            }}
          />
        );
      })}
    </div>
  );
}

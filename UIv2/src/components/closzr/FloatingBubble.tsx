import { useEffect, useRef, useState, type ComponentType } from "react";
import { MessageCircle, X } from "lucide-react";

const STORAGE_KEY = "closzr-bubble-pos";
const SIZE = 56;

type Pos = { x: number; y: number };

export function FloatingBubble() {
  const [open, setOpen] = useState(false);
  const [Panel, setPanel] = useState<ComponentType<{ onClose: () => void }> | null>(null);
  const [pos, setPos] = useState<Pos>(() => {
    if (typeof window === "undefined") return { x: 24, y: 24 };
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) return JSON.parse(raw) as Pos;
    } catch {}
    return { x: window.innerWidth - SIZE - 24, y: window.innerHeight - SIZE - 24 };
  });
  const dragRef = useRef<{ dx: number; dy: number; moved: boolean } | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(pos));
    } catch {}
  }, [pos]);

  useEffect(() => {
    if (!open || Panel) return;
    void import("./ClozrPanel").then((module) => setPanel(() => module.ClozrPanel));
  }, [open, Panel]);

  const onPointerDown = (e: React.PointerEvent) => {
    (e.target as Element).setPointerCapture(e.pointerId);
    dragRef.current = { dx: e.clientX - pos.x, dy: e.clientY - pos.y, moved: false };
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragRef.current) return;
    const nx = Math.max(8, Math.min(window.innerWidth - SIZE - 8, e.clientX - dragRef.current.dx));
    const ny = Math.max(8, Math.min(window.innerHeight - SIZE - 8, e.clientY - dragRef.current.dy));
    if (Math.abs(nx - pos.x) > 3 || Math.abs(ny - pos.y) > 3) dragRef.current.moved = true;
    setPos({ x: nx, y: ny });
  };
  const onPointerUp = (e: React.PointerEvent) => {
    const moved = dragRef.current?.moved;
    dragRef.current = null;
    try {
      (e.target as Element).releasePointerCapture(e.pointerId);
    } catch {}
    if (!moved) setOpen((o) => !o);
  };

  // Posición del panel: si la bola está en la mitad derecha, panel abre hacia la izquierda.
  const panelStyle: React.CSSProperties = (() => {
    if (typeof window === "undefined") return { top: pos.y, left: pos.x + SIZE + 12 };
    const W = 400;
    const H = 600;
    const rightSide = pos.x > window.innerWidth / 2;
    const bottomSide = pos.y > window.innerHeight / 2;
    return {
      top: bottomSide ? Math.max(16, pos.y + SIZE - H) : pos.y,
      left: rightSide ? Math.max(16, pos.x - W - 12) : pos.x + SIZE + 12,
      width: W,
      height: H,
    };
  })();

  return (
    <>
      <button
        aria-label="Abrir Closzr"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        style={{
          position: "fixed",
          left: pos.x,
          top: pos.y,
          width: SIZE,
          height: SIZE,
          zIndex: 9999,
          touchAction: "none",
        }}
        className="rounded-full shadow-2xl flex items-center justify-center text-white cursor-grab active:cursor-grabbing transition-transform hover:scale-105"
      >
        <span
          className="absolute inset-0 rounded-full"
          style={{
            background:
              "radial-gradient(circle at 30% 30%, #ef4256, #c8102e 60%, #8a0a1e)",
            boxShadow: "0 10px 30px -10px rgba(200,16,46,0.6)",
          }}
        />
        <span className="relative font-bold text-sm tracking-tight">
          {open ? <X size={20} /> : <MessageCircle size={20} />}
        </span>
      </button>

      {open && (
        <div
          style={{ position: "fixed", zIndex: 9998, ...panelStyle }}
          className="rounded-2xl bg-white shadow-2xl border border-gray-200 overflow-hidden flex flex-col"
        >
          {Panel ? <Panel onClose={() => setOpen(false)} /> : null}
        </div>
      )}
    </>
  );
}

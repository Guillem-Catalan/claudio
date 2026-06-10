import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState, type ComponentType } from "react";

export const Route = createFileRoute("/closzr-embed")({
  component: Embed,
});

function Embed() {
  const [Panel, setPanel] = useState<ComponentType<{ onClose: () => void }> | null>(null);

  useEffect(() => {
    void import("@/components/closzr/ClozrPanel").then((module) =>
      setPanel(() => module.ClozrPanel),
    );
  }, []);

  return (
    <div className="h-screen w-screen bg-[#faf9f6]">
      {Panel ? (
        <Panel onClose={() => window.parent?.postMessage({ type: "closzr-close" }, "*")} />
      ) : null}
    </div>
  );
}

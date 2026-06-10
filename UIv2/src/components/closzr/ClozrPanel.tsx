import { useState } from "react";
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { X, Database } from "lucide-react";
import ReactMarkdown from "react-markdown";

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import { Message, MessageContent } from "@/components/ai-elements/message";
import {
  PromptInput,
  PromptInputTextarea,
  PromptInputSubmit,
} from "@/components/ai-elements/prompt-input";
import {
  Tool,
  ToolHeader,
  ToolContent,
  ToolInput,
  ToolOutput,
} from "@/components/ai-elements/tool";
import { Shimmer } from "@/components/ai-elements/shimmer";

const SUGGESTIONS = [
  "Pipeline review de Pol",
  "Quick check del deal de Cabify",
  "Audit del último demo",
];

export function ClozrPanel({ onClose }: { onClose: () => void }) {
  const [input, setInput] = useState("");
  const { messages, sendMessage, status } = useChat({
    transport: new DefaultChatTransport({ api: "/api/closzr" }),
  });

  const submit = (text: string) => {
    const t = text.trim();
    if (!t) return;
    sendMessage({ text: t });
    setInput("");
  };

  return (
    <div className="flex flex-col h-full bg-[#faf9f6]">
      {/* Header */}
      <header
        className="flex items-center justify-between px-4 py-3 text-white"
        style={{
          background:
            "linear-gradient(135deg, #c8102e 0%, #8a0a1e 100%)",
        }}
      >
        <div>
          <div className="font-semibold text-sm leading-tight">Closzr</div>
          <div className="text-[11px] opacity-80">Sales Intelligence</div>
        </div>
        <button
          onClick={onClose}
          className="rounded-full p-1 hover:bg-white/10"
          aria-label="Cerrar"
        >
          <X size={16} />
        </button>
      </header>

      {/* Conversation */}
      <Conversation className="flex-1">
        <ConversationContent className="px-3 py-4 space-y-3">
          {messages.length === 0 && (
            <div className="text-sm text-gray-600 space-y-3">
              <p>
                Hola, soy <strong>Claudio</strong>. Pregúntame por un deal, un PAE
                o pídeme un pipeline review.
              </p>
              <div className="flex flex-col gap-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => submit(s)}
                    className="text-left text-xs px-3 py-2 rounded-lg border border-gray-200 bg-white hover:border-[#c8102e] hover:text-[#c8102e] transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m) => (
            <Message key={m.id} from={m.role}>
              <MessageContent>
                {m.parts.map((part, i) => {
                  if (part.type === "text") {
                    return (
                      <div
                        key={i}
                        className="prose prose-sm max-w-none prose-headings:my-2 prose-p:my-1 prose-table:text-xs"
                      >
                        <ReactMarkdown>{part.text}</ReactMarkdown>
                      </div>
                    );
                  }
                  if (part.type === "tool-run_sql") {
                    const state = part.state;
                    const status =
                      state === "output-available"
                        ? "output-available"
                        : state === "output-error"
                          ? "output-error"
                          : state === "input-available"
                            ? "input-available"
                            : "input-streaming";
                    return (
                      <Tool key={i} defaultOpen={false}>
                        <ToolHeader type="tool-run_sql" state={status} />
                        <ToolContent>
                          <ToolInput input={part.input} />
                          <ToolOutput
                            output={
                              state === "output-available" ? (
                                <pre className="text-[10px] whitespace-pre-wrap">
                                  {JSON.stringify(part.output, null, 2).slice(0, 4000)}
                                </pre>
                              ) : undefined
                            }
                            errorText={state === "output-error" ? part.errorText : undefined}
                          />
                        </ToolContent>
                      </Tool>
                    );
                  }
                  return null;
                })}
              </MessageContent>
            </Message>
          ))}

          {status === "submitted" && (
            <div className="flex items-center gap-2 text-xs text-gray-500 pl-2">
              <Database size={12} />
              <Shimmer>Pensando…</Shimmer>
            </div>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      {/* Composer */}
      <div className="p-2 border-t border-gray-200 bg-white">
        <PromptInput
          onSubmit={(message) => {
            submit(message.text ?? input);
          }}
        >
          <PromptInputTextarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Pregúntale a Claudio…"
            autoFocus
          />
          <div className="flex justify-end px-2 pb-2">
            <PromptInputSubmit
              status={status}
              disabled={!input.trim() || status === "streaming" || status === "submitted"}
            />
          </div>
        </PromptInput>
      </div>
    </div>
  );
}

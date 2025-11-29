"use client";

import React, { useState } from "react";

interface Quest {
  id?: string | number;
  title?: string;
  description?: string;
  status?: string;
}

interface QuestsPanelProps {
  quests?: { active?: Quest[]; completed?: Quest[] } | null;
}

export function QuestsPanel({ quests }: QuestsPanelProps) {
  const active = quests?.active ?? [];
  const completed = quests?.completed ?? [];
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggleExpanded = (id: string) => {
    setExpanded(prev => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div className="pointer-events-auto relative w-64 rounded-md border border-input/30 bg-background/80 p-4 shadow-md max-h-96 overflow-y-auto">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Quests</h3>
        <div className="text-sm text-muted-foreground">{active.length} active</div>
      </div>

      <div className="mt-3 text-sm">
        <div className="text-xs text-muted-foreground">Active</div>
        {active.length === 0 ? (
          <div className="mt-1 italic text-muted-foreground text-sm">No active quests</div>
        ) : (
          <div className="mt-1 space-y-2">
            {active.map((q, i) => {
              const id = String(q.id ?? `active-${i}`);
              return (
                <div key={id} className="rounded-sm border p-2">
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="font-semibold">{q.title ?? (q as any).name ?? "Untitled"}</div>
                      {q.status && <div className="text-xs text-muted-foreground">Status: {q.status}</div>}
                    </div>
                    <button
                      onClick={() => toggleExpanded(id)}
                      className="ml-2 text-muted-foreground hover:text-foreground flex-shrink-0"
                    >
                      <svg
                        className={`w-4 h-4 transition-transform ${expanded[id] ? 'rotate-180' : ''}`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                  </div>
                  {expanded[id] && (q.description || (q as any).description) && (
                    <div className="text-xs text-muted-foreground mt-1">{q.description ?? (q as any).description}</div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div className="mt-3 text-xs text-muted-foreground">Completed</div>
        {completed.length === 0 ? (
          <div className="mt-1 italic text-muted-foreground text-sm">No completed quests</div>
        ) : (
          <ul className="mt-1 space-y-1">
            {completed.map((q, i) => (
              <li key={q.id ?? i} className="text-sm">
                <div className="flex justify-between">
                  <span className="line-clamp-1">{q.title ?? (q as any).name ?? "Untitled"}</span>
                  <span className="text-muted-foreground text-xs">✓</span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default QuestsPanel;

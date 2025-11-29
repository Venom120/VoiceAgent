"use client";

import React, { useState } from "react";

interface NPC {
  role?: string;
  attitude?: string;
  alive?: boolean;
  location?: string;
  description?: string;
}

interface NPCPanelProps {
  npcs?: Record<string, NPC> | null;
}

export function NPCPanel({ npcs }: NPCPanelProps) {
  const npcList = npcs ? Object.entries(npcs) : [];
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggleExpanded = (name: string) => {
    setExpanded(prev => ({ ...prev, [name]: !prev[name] }));
  };

  return (
    <div className="pointer-events-auto relative w-64 rounded-md border border-input/30 bg-background/80 p-4 shadow-md max-h-96 overflow-y-auto">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">NPCs</h3>
        <div className="text-sm text-muted-foreground">{npcList.length} known</div>
      </div>

      <div className="mt-3 text-sm space-y-2">
        {npcList.length === 0 ? (
          <div className="italic text-muted-foreground">No known NPCs</div>
        ) : (
          npcList.map(([name, npc]) => (
            <div key={name} className="rounded-sm border p-2">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="font-semibold">{name}</div>
                  {npc.role && <div className="text-xs text-muted-foreground">Role: {npc.role}</div>}
                </div>
                <button
                  onClick={() => toggleExpanded(name)}
                  className="ml-2 text-muted-foreground hover:text-foreground flex-shrink-0"
                >
                  <svg
                    className={`w-4 h-4 transition-transform ${expanded[name] ? 'rotate-180' : ''}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
              </div>
              {expanded[name] && (
                <div className="mt-2 text-xs text-muted-foreground">
                  {npc.attitude && <div>Attitude: {npc.attitude}</div>}
                  {npc.alive !== undefined && <div>Alive: {npc.alive ? 'Yes' : 'No'}</div>}
                  {npc.location && <div>Location: {npc.location}</div>}
                  {npc.description && <div className="mt-1">{npc.description}</div>}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default NPCPanel;
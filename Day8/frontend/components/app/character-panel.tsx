"use client";

import React, { useState } from "react";
import { cn } from "@/lib/utils";

interface AttributeMap {
  [key: string]: number | string;
}

interface PlayerDetails {
  level?: number;
  xp?: number;
  bio?: string;
  [key: string]: any;
}

interface PlayerState {
  name: string;
  class?: string;
  hp: number;
  status?: string;
  attributes?: AttributeMap;
  inventory?: Array<{ name: string; qty?: number; desc?: string; durability?: number; weight?: number; value?: number }>;
  details?: PlayerDetails;
}

interface CharacterPanelProps {
  player?: PlayerState;
}

export function CharacterPanel({ player }: CharacterPanelProps) {
  const p: PlayerState = player ?? {
    name: 'Adventurer',
    hp: 0,
    status: 'Unknown',
    inventory: [],
    attributes: {},
    details: {},
  };

  const [selectedItem, setSelectedItem] = useState<{ name: string; qty?: number; desc?: string; durability?: number; weight?: number; value?: number } | null>(null);

  return (
    <div className="pointer-events-auto relative w-64 rounded-md border border-input/30 bg-background/80 p-4 shadow-md">
      <div className="flex items-start justify-between">
        <h3 className="text-lg font-semibold">{p.name} — {p.class}</h3>
        <div className="text-sm text-muted-foreground text-right">
          {p.details?.level != null && <div>Level {p.details.level}</div>}
          {p.details?.xp != null && <div>{p.details.xp} XP</div>}
        </div>
      </div>
      <div className="mt-2 text-sm">
        {p.details?.bio && <div className="mb-2 text-sm italic text-muted-foreground">{p.details.bio}</div>}
        <div className="flex items-center justify-between">
          <span className="font-mono">HP</span>
          <span className="font-bold">{p.hp} ({p.status ?? 'Unknown'})</span>
        </div>

        <div className="mt-3">
          <div className="text-xs text-muted-foreground">Attributes</div>
          <ul className="mt-1 space-y-1">
            {Object.entries(p.attributes || {}).map(([k, v]) => (
              <li key={k} className="flex justify-between text-sm">
                <span>{k}</span>
                <span className="font-mono">{v}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-3">
          <div className="text-xs text-muted-foreground">Inventory</div>
          {(!p.inventory || p.inventory.length === 0) ? (
            <div className="mt-1 text-sm italic text-muted-foreground">(empty)</div>
          ) : (
            <ul className="mt-1 space-y-1">
              {p.inventory!.map((it, i) => (
                <li key={i} className="flex justify-between text-sm">
                  <button
                    onClick={() => setSelectedItem(it)}
                    className="text-left hover:text-primary cursor-pointer underline decoration-dotted"
                  >
                    {it.name}
                  </button>
                  <span className="font-mono">{it.qty ?? 1}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Debug: Raw player data */}
        {/* <div className="mt-3 border-t pt-2">
          <div className="text-xs text-muted-foreground">Debug: Player Data</div>
          <pre className="mt-1 text-xs bg-muted p-1 rounded overflow-auto max-h-20">
            {JSON.stringify(p, null, 2)}
          </pre>
        </div> */}
      </div>

      {/* Inventory Item Modal */}
      {selectedItem && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-background border border-input rounded-lg p-6 max-w-md w-full mx-4">
            <div className="flex items-start justify-between mb-4">
              <h4 className="text-lg font-semibold">{selectedItem.name}</h4>
              <button
                onClick={() => setSelectedItem(null)}
                className="text-muted-foreground hover:text-foreground"
              >
                ✕
              </button>
            </div>
            <div className="space-y-2 text-sm">
              {selectedItem.desc && (
                <div>
                  <div className="font-medium">Description</div>
                  <div className="text-muted-foreground">{selectedItem.desc}</div>
                </div>
              )}
              {selectedItem.qty != null && (
                <div className="flex justify-between">
                  <span>Quantity</span>
                  <span className="font-mono">{selectedItem.qty}</span>
                </div>
              )}
              {selectedItem.durability != null && (
                <div className="flex justify-between">
                  <span>Durability</span>
                  <span className="font-mono">{selectedItem.durability}</span>
                </div>
              )}
              {selectedItem.weight != null && (
                <div className="flex justify-between">
                  <span>Weight</span>
                  <span className="font-mono">{selectedItem.weight}</span>
                </div>
              )}
              {selectedItem.value != null && (
                <div className="flex justify-between">
                  <span>Value</span>
                  <span className="font-mono">{selectedItem.value}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CharacterPanel;

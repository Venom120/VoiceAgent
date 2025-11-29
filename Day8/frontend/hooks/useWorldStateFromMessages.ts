"use client";

// allow reading NEXT_PUBLIC_* injected env vars without adding node types in this workspace
declare const process: any;

import { useEffect, useState } from "react";
import { useDataChannel } from "@livekit/components-react";

export interface PlayerState {
  name: string;
  class?: string;
  hp: number;
  status?: string;
  attributes?: Record<string, number | string>;
  inventory?: Array<{ name: string; qty?: number; desc?: string }>;
  details?: Record<string, any>;
}

export interface WorldState {
  player: PlayerState;
  npcs?: Record<string, any>;
  locations?: Record<string, any>;
  events?: any[];
  quests?: { active?: any[]; completed?: any[] };
}

// Listen for world_state data messages from backend (via LiveKit data channel).
// The backend sends updated world_state after each function-tool call.
export function useWorldStateFromMessages() {
  const [state, setState] = useState<WorldState | null>(null);

  // Subscribe to LiveKit data channel messages with topic "world_state"
  // The livekit hook may return either the latest message object or an observable/message stream.
  const worldStateMessage = useDataChannel("world_state");

  useEffect(() => {
    if (!worldStateMessage) return;

    let sub: any = null;

    // If the hook returned an observable (messageObservable), subscribe to updates
    // or if it's an rxjs observable directly, subscribe to it.
    try {
      // Case 1: provided an object that contains a `messageObservable` (LiveKit internals)
      // or a `message` field that itself is an observable.
      const maybeObs = (worldStateMessage as any).messageObservable ?? (worldStateMessage as any).message;
      if (maybeObs && typeof maybeObs.subscribe === "function") {
        sub = maybeObs.subscribe((msg: any) => {
          handleIncomingMessage(msg);
        });
        return () => sub && sub.unsubscribe && sub.unsubscribe();
      }

      // Case 2: the hook returned a single/latest message object with a payload
      if ((worldStateMessage as any).payload) {
        handleIncomingMessage(worldStateMessage as any);
      }
    } catch (e) {
      console.warn("useWorldStateFromMessages: failed to subscribe to data channel:", e);
    }

    function handleIncomingMessage(msg: any) {
      try {
        const payload = msg.payload ?? msg;
        // payload may already be a string or ArrayBuffer
        let text = "";
        if (typeof payload === "string") text = payload;
        else if (payload instanceof ArrayBuffer || ArrayBuffer.isView(payload)) {
          const decoder = new TextDecoder();
          text = decoder.decode(payload instanceof ArrayBuffer ? payload : payload.buffer);
        } else if (payload && payload.data) {
          // some shapes put the raw bytes on .data
          const decoder = new TextDecoder();
          text = decoder.decode(payload.data);
        }

        if (!text) return;
        const parsed = JSON.parse(text) as WorldState;
        console.log("🌍 Received world_state from backend (data channel):", parsed);
        const normalized = normalizeWorldState(parsed);
        setState(normalized);
      } catch (err) {
        console.error("Failed to parse world_state data message:", err, msg);
      }
    }

    return () => sub && sub.unsubscribe && sub.unsubscribe();
  }, [worldStateMessage]);
  // No HTTP polling fallback: rely solely on LiveKit data-channel broadcasts for authoritative state.
  // If you need a pull-based backup later, reintroduce a small polling effect here.

  return state;
}

// Helper: normalize parsed world state into the shape the UI expects
function normalizeWorldState(raw: any): WorldState {
  if (!raw) return raw;
  const out: WorldState = { ...(raw as WorldState) };

  // normalize quests: accept either { active: [], completed: [] } or a map { name: { ... } }
  if (out.quests && !Array.isArray((out.quests as any).active)) {
    const qObj = out.quests as Record<string, any>;
    const active: any[] = [];
    const completed: any[] = [];
    for (const [k, v] of Object.entries(qObj)) {
      // skip if already has active/completed keys
      if (k === 'active' || k === 'completed') continue;
      const quest = { ...(v as any), title: (v && (v.title ?? v.name)) ?? k, id: k };
      if ((v && (v.status ?? '').toLowerCase()) === 'completed') completed.push(quest);
      else active.push(quest);
    }
    out.quests = { active, completed } as any;
  }

  // ensure player has defaults
  out.player = {
    name: out.player?.name ?? 'Adventurer',
    hp: out.player?.hp ?? 0,
    status: out.player?.status ?? 'Unknown',
    inventory: out.player?.inventory ?? [],
    attributes: out.player?.attributes ?? {},
    details: out.player?.details ?? {},
  } as any;

  return out;
}

export default useWorldStateFromMessages;

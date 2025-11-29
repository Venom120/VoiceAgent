"use client";

import React from "react";
import QuestsPanel from "./quests-panel";
import NPCPanel from "./npc-panel";

interface LeftPanelProps {
  quests?: any;
  npcs?: any;
}

export function LeftPanel({ quests, npcs }: LeftPanelProps) {
  return (
    <div className="flex flex-col space-y-4 p-4">
      <QuestsPanel quests={quests} />
      <NPCPanel npcs={npcs} />
    </div>
  );
}

export default LeftPanel;
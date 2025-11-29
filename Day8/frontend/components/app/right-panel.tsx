"use client";

import React from "react";
import CharacterPanel from "./character-panel";

interface RightPanelProps {
  player?: any;
}

export function RightPanel({ player }: RightPanelProps) {
  return (
    <div className="p-4">
      <CharacterPanel player={player} />
    </div>
  );
}

export default RightPanel;
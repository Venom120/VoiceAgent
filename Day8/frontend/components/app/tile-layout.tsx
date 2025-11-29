"use client";

import React, { useMemo, useState, useEffect } from 'react';
import { Track } from 'livekit-client';
import { AnimatePresence, motion } from 'motion/react';
import {
  BarVisualizer,
  type TrackReference,
  VideoTrack,
  useLocalParticipant,
  useTracks,
  useVoiceAssistant,
  useDataChannel,
} from '@livekit/components-react';
import { cn } from '@/lib/utils';
import CharacterPanel from '@/components/app/character-panel';
import QuestsPanel from '@/components/app/quests-panel';
import LeftPanel from '@/components/app/left-panel';
import RightPanel from '@/components/app/right-panel';

const MotionContainer = motion.create('div');

const ANIMATION_TRANSITION = {
  type: 'spring',
  stiffness: 675,
  damping: 75,
  mass: 1,
};

const classNames = {
  // GRID
  // 2 Columns x 3 Rows
  grid: [
    'h-full w-full',
    'grid gap-x-2 place-content-center',
    'grid-cols-[1fr_1fr] grid-rows-[90px_1fr_90px]',
  ],
  // Agent
  // chatOpen: true,
  // hasSecondTile: true
  // layout: Column 1 / Row 1
  // align: x-end y-center
  agentChatOpenWithSecondTile: ['col-start-1 row-start-1', 'self-center justify-self-end'],
  // Agent
  // chatOpen: true,
  // hasSecondTile: false
  // layout: Column 1 / Row 1 / Column-Span 2
  // align: x-center y-center
  agentChatOpenWithoutSecondTile: ['col-start-1 row-start-1', 'col-span-2', 'place-content-center'],
  // Agent
  // chatOpen: false
  // layout: Column 1 / Row 1 / Column-Span 2 / Row-Span 3
  // align: x-center y-center
  agentChatClosed: ['col-start-1 row-start-1', 'col-span-2 row-span-3', 'place-content-center'],
  // Second tile
  // chatOpen: true,
  // hasSecondTile: true
  // layout: Column 2 / Row 1
  // align: x-start y-center
  secondTileChatOpen: ['col-start-2 row-start-1', 'self-center justify-self-start'],
  // Second tile
  // chatOpen: false,
  // hasSecondTile: false
  // layout: Column 2 / Row 2
  // align: x-end y-end
  secondTileChatClosed: ['col-start-2 row-start-3', 'place-content-end'],
};

export function useLocalTrackRef(source: Track.Source) {
  const { localParticipant } = useLocalParticipant();
  const publication = localParticipant.getTrackPublication(source);
  const trackRef = useMemo<TrackReference | undefined>(
    () => (publication ? { source, participant: localParticipant, publication } : undefined),
    [source, publication, localParticipant]
  );
  return trackRef;
}

interface TileLayoutProps {
  chatOpen: boolean;
}

export function TileLayout({ chatOpen }: TileLayoutProps) {
  const {
    state: agentState,
    audioTrack: agentAudioTrack,
    videoTrack: agentVideoTrack,
  } = useVoiceAssistant();
  const [screenShareTrack] = useTracks([Track.Source.ScreenShare]);
  const cameraTrack: TrackReference | undefined = useLocalTrackRef(Track.Source.Camera);

  const isCameraEnabled = cameraTrack && !cameraTrack.publication.isMuted;
  const isScreenShareEnabled = screenShareTrack && !screenShareTrack.publication.isMuted;
  const hasSecondTile = isCameraEnabled || isScreenShareEnabled;

  const animationDelay = chatOpen ? 0 : 0.15;
  const isAvatar = agentVideoTrack !== undefined;
  const videoWidth = agentVideoTrack?.publication.dimensions?.width ?? 0;
  const videoHeight = agentVideoTrack?.publication.dimensions?.height ?? 0;

  const [worldState, setWorldState] = useState(null);
  const { message: worldStateMessage } = useDataChannel("world_state");

  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  useEffect(() => {
    console.log("TileLayout: useDataChannel returned", worldStateMessage);
    if (!worldStateMessage) return;

    // parse the message directly since useDataChannel handles subscription internally
    handleIncomingMessage(worldStateMessage);

    function handleIncomingMessage(msg) {
      let text = "";
      try {
        const decoder = new TextDecoder();
        const payload = msg.payload ?? msg;
        if (payload instanceof Uint8Array) {
          text = decoder.decode(payload);
        } else if (payload instanceof ArrayBuffer) {
          text = decoder.decode(payload);
        } else if (typeof payload === "string") {
          text = payload;
        } else {
          console.warn("Unknown payload type:", typeof payload, payload);
          text = String(payload);
        }
        text = text.trim().replace(/^\ufeff/g, ''); // remove BOM and trim
        console.log("🌍 TileLayout received world_state from backend (data channel):", text);
        const parsed = JSON.parse(text);
        setWorldState(parsed);
      } catch (err) {
        console.error("TileLayout: failed to parse world_state data message:", err, "Text was:", text);
      }
    }
  }, [worldStateMessage]);

  return (
    <>
      {/* Mobile toggle buttons placed outside the pointer-events-none container so they're clickable */}
      <button
        onClick={() => setLeftOpen(!leftOpen)}
        aria-label="Open left panel"
        className="md:hidden fixed left-2 bottom-2 z-100 pointer-events-auto bg-background/80 border border-input/30 rounded-full p-2 shadow-md"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </button>

      <button
        onClick={() => setRightOpen(!rightOpen)}
        aria-label="Open right panel"
        className="md:hidden fixed right-2 bottom-2 z-100 pointer-events-auto bg-background/80 border border-input/30 rounded-full p-2 shadow-md"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      <div className="pointer-events-none fixed inset-x-0 top-8 bottom-32 z-50 md:top-12 md:bottom-40">
        <div className="relative mx-auto h-full max-w-2xl px-4 md:px-0">
          <div className={cn(classNames.grid)}>
            {/* Agent */}
            <div
              className={cn([
                'grid',
                !chatOpen && classNames.agentChatClosed,
                chatOpen && hasSecondTile && classNames.agentChatOpenWithSecondTile,
                chatOpen && !hasSecondTile && classNames.agentChatOpenWithoutSecondTile,
              ])}
            >
              <AnimatePresence mode="popLayout">
                {!isAvatar && (
                  // Audio Agent
                  <MotionContainer
                    key="agent"
                    layoutId="agent"
                    initial={{
                      opacity: 0,
                      scale: 0,
                    }}
                    animate={{
                      opacity: 1,
                      scale: chatOpen ? 1 : 5,
                    }}
                    transition={{
                      ...ANIMATION_TRANSITION,
                      delay: animationDelay,
                    }}
                    className={cn(
                      'bg-background/60 aspect-square h-[90px] rounded-md border border-transparent transition-[border,drop-shadow]',
                      chatOpen && 'border-input/50 drop-shadow-lg/10 delay-200'
                    )}
                  >
                    <BarVisualizer
                      barCount={5}
                      state={agentState}
                      options={{ minHeight: 5 }}
                      trackRef={agentAudioTrack}
                      className={cn('flex h-full items-center justify-center gap-1')}
                    >
                      <span
                        className={cn([
                          'bg-muted min-h-2.5 w-2.5 rounded-full',
                          'origin-center transition-colors duration-250 ease-linear',
                          'data-[lk-highlighted=true]:bg-foreground data-[lk-muted=true]:bg-muted',
                        ])}
                      />
                    </BarVisualizer>
                  </MotionContainer>
                )}

                {isAvatar && (
                  // Avatar Agent
                  <MotionContainer
                    key="avatar"
                    layoutId="avatar"
                    initial={{
                      scale: 1,
                      opacity: 1,
                      maskImage:
                        'radial-gradient(circle, rgba(0, 0, 0, 1) 0, rgba(0, 0, 0, 1) 20px, transparent 20px)',
                      filter: 'blur(20px)',
                    }}
                    animate={{
                      maskImage:
                        'radial-gradient(circle, rgba(0, 0, 0, 1) 0, rgba(0, 0, 0, 1) 500px, transparent 500px)',
                      filter: 'blur(0px)',
                      borderRadius: chatOpen ? 6 : 12,
                    }}
                    transition={{
                      ...ANIMATION_TRANSITION,
                      delay: animationDelay,
                      maskImage: {
                        duration: 1,
                      },
                      filter: {
                        duration: 1,
                      },
                    }}
                    className={cn(
                      'overflow-hidden bg-black drop-shadow-xl/80',
                      chatOpen ? 'h-[90px]' : 'h-auto w-full'
                    )}
                  >
                    <VideoTrack
                      width={videoWidth}
                      height={videoHeight}
                      trackRef={agentVideoTrack}
                      className={cn(chatOpen && 'size-[90px] object-cover')}
                    />
                  </MotionContainer>
                )}
              </AnimatePresence>
            </div>

            <div
              className={cn([
                'grid',
                chatOpen && classNames.secondTileChatOpen,
                !chatOpen && classNames.secondTileChatClosed,
              ])}
            >
              {/* Camera & Screen Share or Character Panel */}
              <AnimatePresence>
                {((cameraTrack && isCameraEnabled) || (screenShareTrack && isScreenShareEnabled)) && (
                  <MotionContainer
                    key="camera"
                    layout="position"
                    layoutId="camera"
                    initial={{
                      opacity: 0,
                      scale: 0,
                    }}
                    animate={{
                      opacity: 1,
                      scale: 1,
                    }}
                    exit={{
                      opacity: 0,
                      scale: 0,
                    }}
                    transition={{
                      ...ANIMATION_TRANSITION,
                      delay: animationDelay,
                    }}
                    className="drop-shadow-lg/20"
                  >
                    <VideoTrack
                      trackRef={cameraTrack || screenShareTrack}
                      width={(cameraTrack || screenShareTrack)?.publication.dimensions?.width ?? 0}
                      height={(cameraTrack || screenShareTrack)?.publication.dimensions?.height ?? 0}
                      className="bg-muted aspect-square w-[90px] rounded-md object-cover"
                    />
                  </MotionContainer>
                )}

                {/* If no camera/screen share, show the character panel (parsed from WORLD_UPDATE messages) */}
                {(!cameraTrack && !screenShareTrack) && (
                  // Render the panels directly without motion to avoid layout-origin animations
                  <div key="panels" className="relative">
                    {/* Left Panel Toggle Button (Mobile) */}
                    <button
                      onClick={() => setLeftOpen(!leftOpen)}
                      className="md:hidden fixed left-2 top-2 z-60 bg-background/80 border border-input/30 rounded-full p-2 shadow-md"
                    >
                      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </button>

                    {/* Right Panel Toggle Button (Mobile) */}
                    <button
                      onClick={() => setRightOpen(!rightOpen)}
                      className="md:hidden fixed right-2 top-2 z-60 bg-background/80 border border-input/30 rounded-full p-2 shadow-md"
                    >
                      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                      </svg>
                    </button>

                    {/* Left Panel */}
                    <div
                      className={cn(
                        "fixed left-0 top-20 h-auto w-80 bg-transparent z-50 transition-transform duration-300 ease-in-out md:translate-x-0",
                        leftOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
                      )}
                    >
                      <LeftPanel quests={worldState?.quests} npcs={worldState?.npcs} />
                    </div>

                    {/* Right Panel */}
                    <div
                      className={cn(
                        "fixed right-0 top-20 h-auto w-80 bg-transparent z-50 transition-transform duration-300 ease-in-out md:translate-x-0",
                        rightOpen ? "translate-x-0" : "translate-x-full md:translate-x-0"
                      )}
                    >
                      <RightPanel player={worldState?.player} />
                    </div>
                  </div>
                )}
              </AnimatePresence>
            </div>
          </div>
        </div>
      </div>
      </>
  );
}

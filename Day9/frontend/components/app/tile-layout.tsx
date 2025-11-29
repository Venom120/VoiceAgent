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
import CurrentProducts from '@/components/app/current-products';
import LastOrder from '@/components/app/last-order';

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

  // Shopping state from backend
  const [shoppingState, setShoppingState] = useState(null);
  const { message: shoppingStateMessage } = useDataChannel("shopping_state");

  useEffect(() => {
    console.log("TileLayout: useDataChannel returned", shoppingStateMessage);
    if (!shoppingStateMessage) return;

    // Parse the message from backend
    handleIncomingMessage(shoppingStateMessage);

    function handleIncomingMessage(msg: any) {
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
        console.log("🛍️ TileLayout received shopping_state from backend (data channel):", text);
        const parsed = JSON.parse(text);
        setShoppingState(parsed);
      } catch (err) {
        console.error("TileLayout: failed to parse shopping_state data message:", err, "Text was:", text);
      }
    }
  }, [shoppingStateMessage]);

  return (
    <>
      {/* Shopping Panels - products on the left, last order on the right */}
      {shoppingState && (
        <> 
          <div className="pointer-events-auto fixed left-4 top-20 bottom-40 z-40 w-80 md:left-12">
            <div className="h-full overflow-y-auto">
              <CurrentProducts products={shoppingState.current_products ?? []} />
            </div>
          </div>

          <div className="pointer-events-auto fixed right-4 top-20 bottom-40 z-40 w-80 md:right-12">
            <div className="h-full overflow-y-auto">
              <LastOrder order={shoppingState.last_order ?? null} />
            </div>
          </div>
        </>
      )}

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
              {/* Camera & Screen Share */}
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
              </AnimatePresence>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

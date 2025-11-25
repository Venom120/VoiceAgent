'use client';

import { AnimatePresence, type HTMLMotionProps, motion } from 'motion/react';
import { type ReceivedChatMessage } from '@livekit/components-react';
import { ChatEntry } from '@/components/livekit/chat-entry';

const MotionContainer = motion.create('div');
const MotionChatEntry = motion.create(ChatEntry);

const CONTAINER_MOTION_PROPS = {
  variants: {
    hidden: {
      opacity: 0,
    },
    visible: {
      opacity: 1,
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: {
    duration: 0.3,
    ease: 'easeOut',
  },
};

const MESSAGE_MOTION_PROPS = {
  variants: {
    hidden: {
      opacity: 0,
      translateY: 10,
    },
    visible: {
      opacity: 1,
      translateY: 0,
    },
  },
  initial: 'hidden',
  animate: 'visible',
  exit: 'hidden',
  transition: {
    duration: 0.2,
    ease: 'easeOut',
  },
  layout: true,
};

interface ChatTranscriptProps {
  hidden?: boolean;
  messages?: ReceivedChatMessage[];
}

export function ChatTranscript({
  hidden = false,
  messages = [],
  ...props
}: ChatTranscriptProps & Omit<HTMLMotionProps<'div'>, 'ref'>) {
  console.log('💬 ChatTranscript render:', { hidden, messageCount: messages.length });
  
  if (hidden) {
    return null;
  }
  
  return (
    <MotionContainer {...CONTAINER_MOTION_PROPS} {...props}>
      <AnimatePresence initial={false} mode="popLayout">
        {messages.map(({ id, timestamp, from, message, editTimestamp }: ReceivedChatMessage) => {
          const locale = navigator?.language ?? 'en-US';
          const messageOrigin = from?.isLocal ? 'local' : 'remote';
          const hasBeenEdited = !!editTimestamp;

          console.log('📝 Rendering message:', { id, message, messageOrigin });

          return (
            <MotionChatEntry
              key={id}
              locale={locale}
              timestamp={timestamp}
              message={message}
              messageOrigin={messageOrigin}
              hasBeenEdited={hasBeenEdited}
              {...MESSAGE_MOTION_PROPS}
            />
          );
        })}
      </AnimatePresence>
    </MotionContainer>
  );
}

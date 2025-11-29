import * as React from 'react';
import { cn } from '@/lib/utils';

export interface ChatEntryProps extends React.HTMLAttributes<HTMLLIElement> {
  /** The locale to use for the timestamp. */
  locale: string;
  /** The timestamp of the message. */
  timestamp: number;
  /** The message to display. */
  message: string;
  /** The origin of the message. */
  messageOrigin: 'local' | 'remote';
  /** The sender's name. */
  name?: string;
  /** Whether the message has been edited. */
  hasBeenEdited?: boolean;
}

export const ChatEntry = ({
  name,
  locale,
  timestamp,
  message,
  messageOrigin,
  hasBeenEdited = false,
  className,
  ...props
}: ChatEntryProps) => {
  const time = new Date(timestamp);
  const title = time.toLocaleTimeString(locale, { timeStyle: 'full' });
  
  const isGameMaster = messageOrigin === 'remote';
  const displayName = isGameMaster ? '🎲 Game Master' : '⚔️ You';

  return (
    <li
      title={title}
      data-lk-message-origin={messageOrigin}
      className={cn('group flex w-full flex-col gap-0.5', className)}
      {...props}
    >
      <header
        className={cn(
          'text-muted-foreground flex items-center gap-2 text-sm font-medium',
          messageOrigin === 'local' ? 'flex-row-reverse' : 'text-left'
        )}
      >
        <strong className={isGameMaster ? 'text-purple-600 dark:text-purple-400' : 'text-blue-600 dark:text-blue-400'}>
          {name || displayName}
        </strong>
        <span className="font-mono text-xs opacity-0 transition-opacity ease-linear group-hover:opacity-100">
          {hasBeenEdited && '*'}
          {time.toLocaleTimeString(locale, { timeStyle: 'short' })}
        </span>
      </header>
      <span
        className={cn(
          'max-w-[80%] rounded-[20px] px-4 py-2 shadow-sm',
          messageOrigin === 'local' 
            ? 'bg-blue-600 text-white ml-auto' 
            : 'bg-purple-100 dark:bg-purple-900/40 text-foreground border border-purple-200 dark:border-purple-700 mr-auto'
        )}
      >
        {/** Preserve explicit newlines encoded as \n by rendering them as <br/> */}
        {message.split('\n').map((line, i) => (
          <React.Fragment key={i}>
            {line}
            {i < message.split('\n').length - 1 && <br />}
          </React.Fragment>
        ))}
      </span>
    </li>
  );
};

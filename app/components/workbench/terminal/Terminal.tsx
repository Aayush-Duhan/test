import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { Terminal as XTerm } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';
import { forwardRef, memo, useEffect, useImperativeHandle, useRef } from 'react';
import type { Theme } from '~/lib/stores/theme';
import { createScopedLogger } from '~/utils/logger';
import { getTerminalTheme } from './theme';

const logger = createScopedLogger('Terminal');

export interface TerminalRef {
  reloadStyles: () => void;
}

export interface TerminalProps {
  className?: string;
  theme: Theme;
  readonly?: boolean;
  onTerminalReady?: (terminal: XTerm) => void;
  onTerminalResize?: (cols: number, rows: number) => void;
}

export const Terminal = memo(
  forwardRef<TerminalRef, TerminalProps>(({ className, theme, readonly, onTerminalReady, onTerminalResize }, ref) => {
    const terminalElementRef = useRef<HTMLDivElement>(null);
    const terminalRef = useRef<XTerm>();

    useEffect(() => {
      const element = terminalElementRef.current!;
      let isMounted = true;

      const fitAddon = new FitAddon();
      const webLinksAddon = new WebLinksAddon();

      const terminal = new XTerm({
        cursorBlink: true,
        convertEol: false,
        disableStdin: readonly,
        theme: getTerminalTheme(readonly ? { cursor: '#00000000' } : {}),
        fontSize: 12,
        fontFamily: 'Menlo, courier-new, courier, monospace',
      });

      terminalRef.current = terminal;

      terminal.loadAddon(fitAddon);
      terminal.loadAddon(webLinksAddon);
      terminal.open(element);

      // Wait for terminal to be fully initialized
      setTimeout(() => {
        if (!isMounted || terminalRef.current !== terminal) {
          return;
        }

        if (element.offsetWidth > 0 && element.offsetHeight > 0) {
          try {
            fitAddon.fit();
          } catch (error) {
            logger.debug('Terminal fit skipped', error);
          }

          onTerminalResize?.(terminal.cols, terminal.rows);
        }
      }, 0);

      const resizeObserver = new ResizeObserver(() => {
        if (!isMounted || terminalRef.current !== terminal) {
          return;
        }

        if (element.offsetWidth > 0 && element.offsetHeight > 0) {
          try {
            fitAddon.fit();
          } catch (error) {
            logger.debug('Terminal fit skipped', error);
          }

          onTerminalResize?.(terminal.cols, terminal.rows);
        }
      });

      resizeObserver.observe(element);

      logger.info('Attach terminal');

      onTerminalReady?.(terminal);

      return () => {
        isMounted = false;
        resizeObserver.disconnect();
        terminal.dispose();
      };
    }, []);

    useEffect(() => {
      const terminal = terminalRef.current;

      if (!terminal) {
        return;
      }

      // we render a transparent cursor in case the terminal is readonly
      terminal.options.theme = getTerminalTheme(readonly ? { cursor: '#00000000' } : {});

      terminal.options.disableStdin = readonly;
    }, [theme, readonly]);

    useImperativeHandle(ref, () => {
      return {
        reloadStyles: () => {
          const terminal = terminalRef.current!;
          terminal.options.theme = getTerminalTheme(readonly ? { cursor: '#00000000' } : {});
        },
      };
    }, []);

    return <div className={className} ref={terminalElementRef} onWheel={(e) => e.stopPropagation()} />;
  }),
);

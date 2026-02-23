import { atom, type WritableAtom } from 'nanostores';
import type { ITerminal } from '~/types/terminal';
import { coloredText } from '~/utils/terminal';

const BACKEND_HOST = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
const BACKEND_PORT = '8000';

interface TerminalSession {
  terminal: ITerminal;
  ws: WebSocket;
}

export class TerminalStore {
  #terminals: TerminalSession[] = [];

  // Agent terminal state
  #agentTerminal: ITerminal | null = null;
  #agentWs: WebSocket | null = null;

  showTerminal: WritableAtom<boolean> = import.meta.hot?.data.showTerminal ?? atom(false);
  agentRunId: WritableAtom<string | null> = import.meta.hot?.data.agentRunId ?? atom(null);

  constructor() {
    if (import.meta.hot) {
      import.meta.hot.data.showTerminal = this.showTerminal;
      import.meta.hot.data.agentRunId = this.agentRunId;
    }
  }

  toggleTerminal(value?: boolean) {
    this.showTerminal.set(value !== undefined ? value : !this.showTerminal.get());
  }

  attachTerminal(terminal: ITerminal) {
    const cols = terminal.cols ?? 80;
    const rows = terminal.rows ?? 24;
    const wsUrl = `ws://${BACKEND_HOST}:${BACKEND_PORT}/ws/terminal?cols=${cols}&rows=${rows}`;

    terminal.write('\x1b[90mConnecting to terminal...\x1b[0m\r\n');

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        terminal.write('\x1b[2J\x1b[H'); // clear screen and move cursor home
      };

      ws.onmessage = (event) => {
        terminal.write(event.data);
      };

      ws.onerror = () => {
        terminal.write(coloredText.red('\r\n⚠ Terminal connection error\r\n'));
      };

      ws.onclose = (event) => {
        terminal.write(`\r\n\x1b[90m─ Terminal disconnected (${event.code})\x1b[0m\r\n`);
        // Remove from tracked sessions
        this.#terminals = this.#terminals.filter((s) => s.ws !== ws);
      };

      // Forward user keystrokes to the PTY
      terminal.onData((data) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(data);
        }
      });

      this.#terminals.push({ terminal, ws });
    } catch (error: any) {
      terminal.write(coloredText.red(`Failed to connect: ${error.message}\r\n`));
    }
  }

  onTerminalResize(cols: number, rows: number) {
    for (const { ws } of this.#terminals) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'resize', cols, rows }));
      }
    }
  }

  // -------------------------------------------------------------------
  // Agent Terminal (WebSocket-backed)
  // -------------------------------------------------------------------

  connectAgentTerminal(terminal: ITerminal, runId: string) {
    this.disconnectAgentTerminal();

    this.#agentTerminal = terminal;
    this.agentRunId.set(runId);

    const wsUrl = `ws://${BACKEND_HOST}:${BACKEND_PORT}/ws/terminal/${runId}`;

    terminal.write(`\x1b[90mConnecting to agent run ${runId}...\x1b[0m\r\n`);

    try {
      const ws = new WebSocket(wsUrl);
      this.#agentWs = ws;

      ws.onopen = () => {
        terminal.write(`\x1b[32m✓ Connected to agent terminal\x1b[0m\r\n\r\n`);
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          const stream = msg.stream as string;
          const data = msg.data as string;

          if (stream === 'stderr') {
            terminal.write(`\x1b[31m${data}\x1b[0m`);
          } else if (stream === 'system') {
            terminal.write(`\x1b[90m${data}\x1b[0m`);
          } else {
            terminal.write(data);
          }
        } catch {
          terminal.write(event.data);
        }
      };

      ws.onerror = () => {
        terminal.write(coloredText.red('\n⚠ WebSocket error\n'));
      };

      ws.onclose = (event) => {
        terminal.write(`\r\n\x1b[90m─ Connection closed (${event.code})\x1b[0m\r\n`);
        this.#agentWs = null;
      };
    } catch (error: any) {
      terminal.write(coloredText.red(`Failed to connect: ${error.message}\n`));
    }
  }

  disconnectAgentTerminal() {
    if (this.#agentWs) {
      this.#agentWs.close();
      this.#agentWs = null;
    }
    this.#agentTerminal = null;
    this.agentRunId.set(null);
  }

  writeToAgentTerminal(data: string) {
    if (this.#agentTerminal) {
      this.#agentTerminal.write(data);
    }
  }
}

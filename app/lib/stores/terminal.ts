import type { WebContainer, WebContainerProcess } from '@webcontainer/api';
import { atom, type WritableAtom } from 'nanostores';
import type { ITerminal } from '~/types/terminal';
import { newShellProcess } from '~/utils/shell';
import { coloredText } from '~/utils/terminal';

export class TerminalStore {
  #webcontainer: Promise<WebContainer>;
  #terminals: Array<{ terminal: ITerminal; process: WebContainerProcess }> = [];

  // Agent terminal state
  #agentTerminal: ITerminal | null = null;
  #agentWs: WebSocket | null = null;
  #agentRunId: WritableAtom<string | null> = atom(null);

  showTerminal: WritableAtom<boolean> = import.meta.hot?.data.showTerminal ?? atom(false);
  agentRunId: WritableAtom<string | null> = import.meta.hot?.data.agentRunId ?? atom(null);

  constructor(webcontainerPromise: Promise<WebContainer>) {
    this.#webcontainer = webcontainerPromise;

    if (import.meta.hot) {
      import.meta.hot.data.showTerminal = this.showTerminal;
      import.meta.hot.data.agentRunId = this.agentRunId;
    }
  }

  toggleTerminal(value?: boolean) {
    this.showTerminal.set(value !== undefined ? value : !this.showTerminal.get());
  }

  async attachTerminal(terminal: ITerminal) {
    try {
      const shellProcess = await newShellProcess(await this.#webcontainer, terminal);
      this.#terminals.push({ terminal, process: shellProcess });
    } catch (error: any) {
      terminal.write(coloredText.red('Failed to spawn shell\n\n') + error.message);
      return;
    }
  }

  onTerminalResize(cols: number, rows: number) {
    for (const { process } of this.#terminals) {
      process.resize({ cols, rows });
    }
  }

  // -------------------------------------------------------------------
  // Agent Terminal (WebSocket-backed)
  // -------------------------------------------------------------------

  /**
   * Connect a terminal to the agent's WebSocket output stream.
   * This replaces the WebContainer shell for agent-driven terminal display.
   */
  connectAgentTerminal(terminal: ITerminal, runId: string) {
    // Disconnect any existing agent terminal
    this.disconnectAgentTerminal();

    this.#agentTerminal = terminal;
    this.agentRunId.set(runId);

    const backendHost = window.location.hostname;
    const backendPort = '8000';
    const wsUrl = `ws://${backendHost}:${backendPort}/ws/terminal/${runId}`;

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
            // Stderr in red
            terminal.write(`\x1b[31m${data}\x1b[0m`);
          } else if (stream === 'system') {
            // System messages in dim
            terminal.write(`\x1b[90m${data}\x1b[0m`);
          } else {
            terminal.write(data);
          }
        } catch {
          // Raw text fallback
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

  /**
   * Disconnect the agent terminal WebSocket.
   */
  disconnectAgentTerminal() {
    if (this.#agentWs) {
      this.#agentWs.close();
      this.#agentWs = null;
    }
    this.#agentTerminal = null;
    this.agentRunId.set(null);
  }

  /**
   * Write directly to the agent terminal (used by SSE event handler).
   */
  writeToAgentTerminal(data: string) {
    if (this.#agentTerminal) {
      this.#agentTerminal.write(data);
    }
  }
}

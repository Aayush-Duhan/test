/**
 * Agent store — manages AI agent orchestration runs.
 *
 * Connects to the backend's SSE stream for agent lifecycle events
 * and coordinates with the TerminalStore for real-time output display.
 */

import { atom, type WritableAtom } from 'nanostores';

export type AgentRunStatus = 'idle' | 'running' | 'paused' | 'finished' | 'failed' | 'cancelled';

export interface ToolTraceEntry {
    tool: string;
    args: Record<string, unknown>;
    exitCode: number | null;
    success: boolean;
    duration: number;
    timestamp: number;
}

export interface AgentDecisionEntry {
    decision: Record<string, unknown>;
    rawResponse?: string;
    timestamp: number;
}

const BACKEND_BASE = `http://${window.location.hostname}:8000`;

export class AgentStore {
    runId: WritableAtom<string | null> = atom(null);
    status: WritableAtom<AgentRunStatus> = atom('idle');
    toolTraces: WritableAtom<ToolTraceEntry[]> = atom([]);
    decisions: WritableAtom<AgentDecisionEntry[]> = atom([]);
    guidance: WritableAtom<string | null> = atom(null);
    error: WritableAtom<string | null> = atom(null);

    #abortController: AbortController | null = null;

    /**
     * Start a new agent run. Returns the run ID from the response header.
     *
     * @param messages  Chat messages to seed the agent with.
     * @param onEvent   Optional callback invoked for every SSE event.
     */
    async startRun(
        messages: Array<{ role: string; content?: string | null }>,
        onEvent?: (event: Record<string, unknown>) => void,
    ): Promise<string | null> {
        // Reset state
        this.status.set('running');
        this.toolTraces.set([]);
        this.decisions.set([]);
        this.guidance.set(null);
        this.error.set(null);

        this.#abortController = new AbortController();

        try {
            const resp = await fetch(`${BACKEND_BASE}/api/agent/run`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                credentials: 'include',
                body: JSON.stringify({ messages }),
                signal: this.#abortController.signal,
            });

            if (!resp.ok) {
                const detail = await resp.text();
                this.error.set(`Agent run failed: ${resp.status} ${detail}`);
                this.status.set('failed');
                return null;
            }

            const runId = resp.headers.get('X-Agent-Run-Id');
            this.runId.set(runId);

            // Process SSE stream
            const reader = resp.body?.getReader();
            const decoder = new TextDecoder();

            if (!reader) {
                this.error.set('No response body');
                this.status.set('failed');
                return null;
            }

            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();

                if (done) {
                    break;
                }

                buffer += decoder.decode(value, { stream: true });

                // Process complete SSE lines
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) {
                        continue;
                    }

                    const dataStr = line.slice(6).trim();

                    if (dataStr === '[DONE]') {
                        if (this.status.get() === 'running') {
                            this.status.set('finished');
                        }
                        break;
                    }

                    try {
                        const event = JSON.parse(dataStr);
                        this.#handleEvent(event);
                        onEvent?.(event);
                    } catch {
                        // Skip unparseable events
                    }
                }
            }

            return runId;
        } catch (err: any) {
            if (err.name === 'AbortError') {
                this.status.set('cancelled');
            } else {
                this.error.set(err.message);
                this.status.set('failed');
            }
            return null;
        }
    }

    /**
     * Pause the current run.
     */
    async pauseRun(): Promise<boolean> {
        const runId = this.runId.get();

        if (!runId) {
            return false;
        }

        const resp = await fetch(`${BACKEND_BASE}/api/agent/${runId}/pause`, {
            method: 'POST',
            credentials: 'include',
        });

        if (resp.ok) {
            const data: { guidance?: string; success: boolean } = await resp.json();
            this.status.set('paused');
            this.guidance.set(data.guidance || null);
            return data.success;
        }

        return false;
    }

    /**
     * Resume a paused run.
     */
    async resumeRun(): Promise<boolean> {
        const runId = this.runId.get();

        if (!runId) {
            return false;
        }

        const resp = await fetch(`${BACKEND_BASE}/api/agent/${runId}/resume`, {
            method: 'POST',
            credentials: 'include',
        });

        if (resp.ok) {
            const data: { success: boolean } = await resp.json();
            this.status.set('running');
            this.guidance.set(null);
            return data.success;
        }

        return false;
    }

    /**
     * Cancel the current run.
     */
    async cancelRun(): Promise<boolean> {
        const runId = this.runId.get();

        // Abort the SSE fetch
        this.#abortController?.abort();

        if (!runId) {
            this.status.set('idle');
            return true;
        }

        const resp = await fetch(`${BACKEND_BASE}/api/agent/${runId}/cancel`, {
            method: 'POST',
            credentials: 'include',
        });

        this.status.set('cancelled');
        return resp.ok;
    }

    /**
     * Handle an SSE event from the agent orchestrator.
     */
    #handleEvent(event: Record<string, unknown>) {
        const type = event.type as string;

        switch (type) {
            case 'tool-start': {
                // A new tool is starting
                break;
            }
            case 'tool-end': {
                const trace: ToolTraceEntry = {
                    tool: event.tool as string,
                    args: {},
                    exitCode: (event.exitCode as number) ?? null,
                    success: event.success as boolean,
                    duration: event.duration as number,
                    timestamp: Date.now(),
                };
                this.toolTraces.set([...this.toolTraces.get(), trace]);
                break;
            }
            case 'agent-decision': {
                const entry: AgentDecisionEntry = {
                    decision: event.decision as Record<string, unknown>,
                    rawResponse: event.rawResponse as string | undefined,
                    timestamp: Date.now(),
                };
                this.decisions.set([...this.decisions.get(), entry]);
                break;
            }
            case 'agent-pause': {
                this.status.set('paused');
                this.guidance.set((event.guidance as string) || null);
                break;
            }
            case 'agent-finish': {
                this.status.set('finished');
                break;
            }
            case 'agent-error': {
                this.error.set((event.error as string) || 'Unknown error');
                this.status.set('failed');
                break;
            }
        }
    }
}

export const agentStore = new AgentStore();

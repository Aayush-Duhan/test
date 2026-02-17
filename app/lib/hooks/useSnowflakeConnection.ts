import { useCallback, useEffect, useState } from 'react';

export interface SnowflakeConnectPayload {
  account: string;
  user: string;
  role: string;
  warehouse: string;
  database: string;
  schema: string;
  authenticator?: string;
}

interface SnowflakeModelDefaults {
  model: string;
  cortexFunction: string;
}

interface SnowflakeStatusResponse {
  connected: boolean;
  expiresAt?: string;
  sessionId?: string;
  modelDefaults?: SnowflakeModelDefaults;
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as { detail?: unknown };

    if (typeof data.detail === 'string') {
      return data.detail;
    }
  } catch {
    // ignore invalid JSON and fall back to status text
  }

  return response.statusText || 'Request failed';
}

export function useSnowflakeConnection() {
  const [connected, setConnected] = useState(false);
  const [expiresAt, setExpiresAt] = useState<string | undefined>(undefined);
  const [modelDefaults, setModelDefaults] = useState<SnowflakeModelDefaults | undefined>(undefined);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | undefined>(undefined);

  const refreshStatus = useCallback(async () => {
    const response = await fetch('/api/snowflake/status', {
      credentials: 'include',
    });

    if (!response.ok) {
      throw new Error(await parseError(response));
    }

    const data: SnowflakeStatusResponse = await response.json();
    setConnected(Boolean(data.connected));
    setExpiresAt(data.expiresAt);
    setModelDefaults(data.modelDefaults);

    return data;
  }, []);

  useEffect(() => {
    let active = true;

    refreshStatus()
      .then(() => {
        if (!active) {
          return;
        }

        setError(undefined);
      })
      .catch((refreshError: unknown) => {
        if (!active) {
          return;
        }

        setError(refreshError instanceof Error ? refreshError.message : 'Unable to check Snowflake status');
      });

    return () => {
      active = false;
    };
  }, [refreshStatus]);

  const connect = useCallback(async (payload: SnowflakeConnectPayload) => {
    setIsBusy(true);
    setError(undefined);

    try {
      const response = await fetch('/api/snowflake/connect', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(await parseError(response));
      }

      await refreshStatus();
    } catch (connectError) {
      const message = connectError instanceof Error ? connectError.message : 'Unable to connect to Snowflake';
      setConnected(false);
      setError(message);
      throw connectError;
    } finally {
      setIsBusy(false);
    }
  }, [refreshStatus]);

  const disconnect = useCallback(async () => {
    setIsBusy(true);
    setError(undefined);

    try {
      const response = await fetch('/api/snowflake/disconnect', {
        method: 'POST',
        credentials: 'include',
      });

      if (!response.ok) {
        throw new Error(await parseError(response));
      }

      setConnected(false);
      setExpiresAt(undefined);
      setModelDefaults(undefined);
    } catch (disconnectError) {
      const message = disconnectError instanceof Error ? disconnectError.message : 'Unable to disconnect from Snowflake';
      setError(message);
      throw disconnectError;
    } finally {
      setIsBusy(false);
    }
  }, []);

  return {
    connected,
    expiresAt,
    modelDefaults,
    isBusy,
    error,
    refreshStatus,
    connect,
    disconnect,
  };
}

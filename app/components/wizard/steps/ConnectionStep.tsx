import React, { useState } from 'react';
import { CheckCircle, Loader2, AlertCircle } from 'lucide-react';
import styles from '../SetupWizard.module.scss';

interface ConnectionStepProps {
    connected: boolean;
    isBusy: boolean;
    error?: string;
    onConnect: (payload: {
        account: string;
        user: string;
        role: string;
        warehouse: string;
        database: string;
        schema: string;
        authenticator: string;
    }) => Promise<void>;
    onDisconnect: () => Promise<void>;
}

export function ConnectionStep({ connected, isBusy, error, onConnect, onDisconnect }: ConnectionStepProps) {
    const [form, setForm] = useState({
        account: '',
        user: '',
        role: '',
        warehouse: '',
        database: '',
        schema: '',
        authenticator: 'externalbrowser',
    });

    const update = (field: string, value: string) => {
        setForm((prev) => ({ ...prev, [field]: value }));
    };

    const handleConnect = async () => {
        await onConnect(form);
    };

    return (
        <div className={styles.stepContent}>
            <h2 className={styles.stepTitle}>Snowflake Connection</h2>
            <p className={styles.stepDescription}>Connect to your Snowflake account to execute migrations.</p>

            {connected ? (
                <>
                    <div className={`${styles.connectionStatus} ${styles.connected}`}>
                        <CheckCircle size={18} />
                        <span>Connected to Snowflake</span>
                    </div>
                    <div style={{ marginTop: '1rem' }}>
                        <button
                            className={`${styles.navBtn} ${styles.navBtnBack}`}
                            onClick={onDisconnect}
                            disabled={isBusy}
                            type="button"
                        >
                            Disconnect
                        </button>
                    </div>
                </>
            ) : (
                <>
                    <div className={styles.connectionForm}>
                        <div className={`${styles.connectionField} ${styles.fullWidth}`}>
                            <label className={styles.connectionLabel}>Account</label>
                            <input
                                className={styles.connectionInput}
                                value={form.account}
                                onChange={(e) => update('account', e.target.value)}
                                placeholder="org-account"
                            />
                        </div>
                        <div className={styles.connectionField}>
                            <label className={styles.connectionLabel}>User</label>
                            <input
                                className={styles.connectionInput}
                                value={form.user}
                                onChange={(e) => update('user', e.target.value)}
                                placeholder="username"
                            />
                        </div>
                        <div className={styles.connectionField}>
                            <label className={styles.connectionLabel}>Role</label>
                            <input
                                className={styles.connectionInput}
                                value={form.role}
                                onChange={(e) => update('role', e.target.value)}
                                placeholder="SYSADMIN"
                            />
                        </div>
                        <div className={styles.connectionField}>
                            <label className={styles.connectionLabel}>Warehouse</label>
                            <input
                                className={styles.connectionInput}
                                value={form.warehouse}
                                onChange={(e) => update('warehouse', e.target.value)}
                                placeholder="COMPUTE_WH"
                            />
                        </div>
                        <div className={styles.connectionField}>
                            <label className={styles.connectionLabel}>Database</label>
                            <input
                                className={styles.connectionInput}
                                value={form.database}
                                onChange={(e) => update('database', e.target.value)}
                                placeholder="MY_DB"
                            />
                        </div>
                        <div className={styles.connectionField}>
                            <label className={styles.connectionLabel}>Schema</label>
                            <input
                                className={styles.connectionInput}
                                value={form.schema}
                                onChange={(e) => update('schema', e.target.value)}
                                placeholder="PUBLIC"
                            />
                        </div>
                        <div className={styles.connectionField}>
                            <label className={styles.connectionLabel}>Auth</label>
                            <input
                                className={styles.connectionInput}
                                value={form.authenticator}
                                onChange={(e) => update('authenticator', e.target.value)}
                                placeholder="externalbrowser"
                            />
                        </div>
                    </div>

                    {error && (
                        <div className={`${styles.connectionStatus} ${styles.disconnected}`}>
                            <AlertCircle size={16} />
                            <span>{error}</span>
                        </div>
                    )}

                    <div style={{ marginTop: '1rem' }}>
                        <button
                            className={`${styles.navBtn} ${styles.navBtnNext}`}
                            onClick={handleConnect}
                            disabled={isBusy || !form.account || !form.user}
                            type="button"
                        >
                            {isBusy ? (
                                <>
                                    <Loader2 size={16} className="animate-spin" /> Connecting…
                                </>
                            ) : (
                                'Connect'
                            )}
                        </button>
                    </div>
                </>
            )}
        </div>
    );
}

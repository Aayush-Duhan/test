import React from 'react';
import { CheckCircle, AlertCircle, FileText, Table2, Database, Snowflake } from 'lucide-react';
import styles from '../SetupWizard.module.scss';
import type { WizardFile } from './UploadStep';

const LANGUAGE_LABELS: Record<string, string> = {
    teradata: 'Teradata',
    oracle: 'Oracle',
    netezza: 'Netezza',
    sqlserver: 'SQL Server',
};

interface SummaryStepProps {
    language: string;
    files: WizardFile[];
    mappingFile: { name: string } | null;
    connected: boolean;
}

export function SummaryStep({ language, files, mappingFile, connected }: SummaryStepProps) {
    return (
        <div className={styles.stepContent}>
            <h2 className={styles.stepTitle}>Review & Start</h2>
            <p className={styles.stepDescription}>Review your migration configuration before starting.</p>

            <div className={styles.summaryCard}>
                <div className={styles.summaryRow}>
                    <span className={styles.summaryLabel}>
                        <Database size={14} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />
                        Source Language
                    </span>
                    <span className={styles.summaryValue}>{LANGUAGE_LABELS[language] || language}</span>
                </div>

                <div className={styles.summaryRow}>
                    <span className={styles.summaryLabel}>
                        <FileText size={14} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />
                        Source Files
                    </span>
                    <span className={styles.summaryValue}>
                        {files.length} file{files.length !== 1 ? 's' : ''}
                    </span>
                </div>

                <div className={styles.summaryRow}>
                    <span className={styles.summaryLabel}>
                        <Table2 size={14} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />
                        Schema Mapping
                    </span>
                    <span className={styles.summaryValue}>
                        {mappingFile ? (
                            <span className={`${styles.summaryBadge} ${styles.success}`}>
                                <CheckCircle size={12} />
                                {mappingFile.name}
                            </span>
                        ) : (
                            <span className={`${styles.summaryBadge} ${styles.warning}`}>Skipped</span>
                        )}
                    </span>
                </div>

                <div className={styles.summaryRow}>
                    <span className={styles.summaryLabel}>
                        <Snowflake size={14} style={{ display: 'inline', marginRight: 6, verticalAlign: -2 }} />
                        Snowflake
                    </span>
                    <span className={styles.summaryValue}>
                        {connected ? (
                            <span className={`${styles.summaryBadge} ${styles.success}`}>
                                <CheckCircle size={12} />
                                Connected
                            </span>
                        ) : (
                            <span className={`${styles.summaryBadge} ${styles.error}`}>
                                <AlertCircle size={12} />
                                Not Connected
                            </span>
                        )}
                    </span>
                </div>
            </div>
        </div>
    );
}

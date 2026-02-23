import React, { useState, useCallback } from 'react';
import { Check, ChevronLeft, ChevronRight, Rocket } from 'lucide-react';
import { LanguageStep } from './steps/LanguageStep';
import { UploadStep, type WizardFile } from './steps/UploadStep';
import { SchemaMappingStep } from './steps/SchemaMappingStep';
import { ConnectionStep } from './steps/ConnectionStep';
import { SummaryStep } from './steps/SummaryStep';
import styles from './SetupWizard.module.scss';

const STEPS = [
    { id: 'language', label: 'Language' },
    { id: 'upload', label: 'Files' },
    { id: 'schema', label: 'Schema' },
    { id: 'connection', label: 'Connect' },
    { id: 'summary', label: 'Review' },
];

export interface WizardConfig {
    language: string;
    files: WizardFile[];
    mappingFile: { name: string; size: number; content: string } | null;
}

interface SetupWizardProps {
    snowflakeConnected: boolean;
    snowflakeBusy: boolean;
    snowflakeError?: string;
    onSnowflakeConnect: (payload: {
        account: string;
        user: string;
        role: string;
        warehouse: string;
        database: string;
        schema: string;
        authenticator: string;
    }) => Promise<void>;
    onSnowflakeDisconnect: () => Promise<void>;
    onComplete: (config: WizardConfig) => void;
}

export function SetupWizard({
    snowflakeConnected,
    snowflakeBusy,
    snowflakeError,
    onSnowflakeConnect,
    onSnowflakeDisconnect,
    onComplete,
}: SetupWizardProps) {
    const [step, setStep] = useState(0);
    const [language, setLanguage] = useState('teradata');
    const [files, setFiles] = useState<WizardFile[]>([]);
    const [mappingFile, setMappingFile] = useState<{ name: string; size: number; content: string } | null>(null);

    const canNext = useCallback(() => {
        switch (step) {
            case 0: return language !== '';
            case 1: return files.length > 0;
            case 2: return true; // optional
            case 3: return snowflakeConnected;
            case 4: return snowflakeConnected && files.length > 0;
            default: return false;
        }
    }, [step, language, files, snowflakeConnected]);

    const goNext = useCallback(() => {
        if (step < STEPS.length - 1) setStep(step + 1);
    }, [step]);

    const goBack = useCallback(() => {
        if (step > 0) setStep(step - 1);
    }, [step]);

    const handleStart = useCallback(() => {
        onComplete({ language, files, mappingFile });
    }, [language, files, mappingFile, onComplete]);

    return (
        <div className={styles.wizard}>
            {/* Step indicator */}
            <div className={styles.stepIndicator}>
                {STEPS.map((s, i) => (
                    <React.Fragment key={s.id}>
                        <div
                            className={`${styles.stepDot} ${i === step ? styles.active : ''} ${i < step ? styles.completed : ''}`}
                            title={s.label}
                        >
                            {i < step ? <Check size={14} /> : i + 1}
                        </div>
                        {i < STEPS.length - 1 && (
                            <div className={`${styles.stepLine} ${i < step ? styles.completed : ''}`} />
                        )}
                    </React.Fragment>
                ))}
            </div>

            {/* Step content */}
            {step === 0 && <LanguageStep selected={language} onSelect={setLanguage} />}
            {step === 1 && <UploadStep files={files} onFilesChange={setFiles} />}
            {step === 2 && <SchemaMappingStep mappingFile={mappingFile} onMappingFileChange={setMappingFile} />}
            {step === 3 && (
                <ConnectionStep
                    connected={snowflakeConnected}
                    isBusy={snowflakeBusy}
                    error={snowflakeError}
                    onConnect={onSnowflakeConnect}
                    onDisconnect={onSnowflakeDisconnect}
                />
            )}
            {step === 4 && (
                <SummaryStep
                    language={language}
                    files={files}
                    mappingFile={mappingFile}
                    connected={snowflakeConnected}
                />
            )}

            {/* Navigation */}
            <div className={styles.navButtons}>
                <div>
                    {step > 0 && (
                        <button className={`${styles.navBtn} ${styles.navBtnBack}`} onClick={goBack} type="button">
                            <ChevronLeft size={16} /> Back
                        </button>
                    )}
                </div>

                <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
                    {step === 2 && !mappingFile && (
                        <button className={styles.skipBtn} onClick={goNext} type="button">
                            Skip
                        </button>
                    )}

                    {step < STEPS.length - 1 ? (
                        <button
                            className={`${styles.navBtn} ${styles.navBtnNext}`}
                            onClick={goNext}
                            disabled={!canNext()}
                            type="button"
                        >
                            Next <ChevronRight size={16} />
                        </button>
                    ) : (
                        <button
                            className={`${styles.navBtn} ${styles.navBtnStart}`}
                            onClick={handleStart}
                            disabled={!canNext()}
                            type="button"
                        >
                            <Rocket size={16} /> Start Migration
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}

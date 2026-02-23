import React from 'react';
import { Database, Table2, Server, HardDrive } from 'lucide-react';
import styles from '../SetupWizard.module.scss';

const LANGUAGES = [
    { id: 'teradata', name: 'Teradata', desc: 'Teradata SQL & BTEQ', icon: Database },
    { id: 'oracle', name: 'Oracle', desc: 'Oracle PL/SQL', icon: Server },
    { id: 'netezza', name: 'Netezza', desc: 'IBM Netezza SQL', icon: HardDrive },
    { id: 'sqlserver', name: 'SQL Server', desc: 'T-SQL / SSMS', icon: Table2 },
];

interface LanguageStepProps {
    selected: string;
    onSelect: (id: string) => void;
}

export function LanguageStep({ selected, onSelect }: LanguageStepProps) {
    return (
        <div className={styles.stepContent}>
            <h2 className={styles.stepTitle}>Source Language</h2>
            <p className={styles.stepDescription}>Select the database platform you're migrating from.</p>
            <div className={styles.languageGrid}>
                {LANGUAGES.map((lang) => {
                    const Icon = lang.icon;
                    return (
                        <button
                            key={lang.id}
                            className={`${styles.languageCard} ${selected === lang.id ? styles.selected : ''}`}
                            onClick={() => onSelect(lang.id)}
                            type="button"
                        >
                            <div className={styles.languageIcon}>
                                <Icon size={20} />
                            </div>
                            <div>
                                <div className={styles.languageName}>{lang.name}</div>
                                <div className={styles.languageDesc}>{lang.desc}</div>
                            </div>
                        </button>
                    );
                })}
            </div>
        </div>
    );
}

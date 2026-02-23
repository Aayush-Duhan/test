import React, { useCallback, useRef, useState } from 'react';
import { Table2, FileText, X } from 'lucide-react';
import styles from '../SetupWizard.module.scss';

interface SchemaMappingStepProps {
    mappingFile: { name: string; size: number; content: string } | null;
    onMappingFileChange: (file: { name: string; size: number; content: string } | null) => void;
}

export function SchemaMappingStep({ mappingFile, onMappingFileChange }: SchemaMappingStepProps) {
    const [dragOver, setDragOver] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    const readFile = useCallback(
        async (file: File) => {
            const content = await file.text();
            onMappingFileChange({ name: file.name, size: file.size, content });
        },
        [onMappingFileChange],
    );

    const handleDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            setDragOver(false);
            if (e.dataTransfer.files.length > 0) {
                readFile(e.dataTransfer.files[0]);
            }
        },
        [readFile],
    );

    return (
        <div className={styles.stepContent}>
            <h2 className={styles.stepTitle}>Schema Mapping</h2>
            <p className={styles.stepDescription}>
                Upload a CSV crosswalk file to map source schemas to Snowflake targets.
                <br />
                <span style={{ opacity: 0.6 }}>This step is optional — you can skip it.</span>
            </p>

            {mappingFile ? (
                <div className={styles.fileChip} style={{ maxWidth: 400 }}>
                    <FileText size={16} style={{ flexShrink: 0, opacity: 0.5 }} />
                    <span className={styles.fileChipName}>{mappingFile.name}</span>
                    <span className={styles.fileChipSize}>{(mappingFile.size / 1024).toFixed(1)} KB</span>
                    <button
                        className={styles.fileChipRemove}
                        onClick={() => onMappingFileChange(null)}
                        type="button"
                    >
                        <X size={14} />
                    </button>
                </div>
            ) : (
                <div
                    className={`${styles.dropzone} ${dragOver ? styles.dragOver : ''}`}
                    onClick={() => inputRef.current?.click()}
                    onDragOver={(e) => {
                        e.preventDefault();
                        setDragOver(true);
                    }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={handleDrop}
                >
                    <Table2 size={32} className={styles.dropzoneIcon} />
                    <div className={styles.dropzoneText}>
                        Drop your CSV crosswalk, or <span className={styles.dropzoneAccent}>browse</span>
                    </div>
                    <div className={styles.dropzoneHint}>.csv files — columns: source_db, source_schema, target_db, target_schema</div>
                    <input
                        ref={inputRef}
                        type="file"
                        accept=".csv"
                        style={{ display: 'none' }}
                        onChange={(e) => {
                            if (e.target.files?.[0]) {
                                readFile(e.target.files[0]);
                                e.target.value = '';
                            }
                        }}
                    />
                </div>
            )}
        </div>
    );
}

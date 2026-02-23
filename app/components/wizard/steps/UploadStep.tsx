import React, { useCallback, useRef, useState } from 'react';
import { Upload, FileText, X } from 'lucide-react';
import styles from '../SetupWizard.module.scss';

export interface WizardFile {
    name: string;
    size: number;
    content: string;
}

interface UploadStepProps {
    files: WizardFile[];
    onFilesChange: (files: WizardFile[]) => void;
}

function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function UploadStep({ files, onFilesChange }: UploadStepProps) {
    const [dragOver, setDragOver] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    const readFiles = useCallback(
        async (fileList: FileList) => {
            const newFiles: WizardFile[] = [];
            const existingNames = new Set(files.map((f) => f.name));

            for (let i = 0; i < fileList.length; i++) {
                const file = fileList[i];
                if (existingNames.has(file.name)) continue;

                const content = await file.text();
                newFiles.push({ name: file.name, size: file.size, content });
            }

            if (newFiles.length > 0) {
                onFilesChange([...files, ...newFiles]);
            }
        },
        [files, onFilesChange],
    );

    const handleDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            setDragOver(false);
            if (e.dataTransfer.files.length > 0) {
                readFiles(e.dataTransfer.files);
            }
        },
        [readFiles],
    );

    const handleInputChange = useCallback(
        (e: React.ChangeEvent<HTMLInputElement>) => {
            if (e.target.files && e.target.files.length > 0) {
                readFiles(e.target.files);
                e.target.value = '';
            }
        },
        [readFiles],
    );

    const removeFile = useCallback(
        (name: string) => {
            onFilesChange(files.filter((f) => f.name !== name));
        },
        [files, onFilesChange],
    );

    return (
        <div className={styles.stepContent}>
            <h2 className={styles.stepTitle}>Upload Source Files</h2>
            <p className={styles.stepDescription}>Add your SQL source files to migrate.</p>

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
                <Upload size={32} className={styles.dropzoneIcon} />
                <div className={styles.dropzoneText}>
                    Drag & drop files here, or <span className={styles.dropzoneAccent}>browse</span>
                </div>
                <div className={styles.dropzoneHint}>.sql, .bteq, .txt files</div>
                <input
                    ref={inputRef}
                    type="file"
                    multiple
                    accept=".sql,.bteq,.txt,.ddl,.dml,.prc"
                    style={{ display: 'none' }}
                    onChange={handleInputChange}
                />
            </div>

            {files.length > 0 && (
                <div className={styles.fileList}>
                    {files.map((f) => (
                        <div key={f.name} className={styles.fileChip}>
                            <FileText size={16} style={{ flexShrink: 0, opacity: 0.5 }} />
                            <span className={styles.fileChipName}>{f.name}</span>
                            <span className={styles.fileChipSize}>{formatSize(f.size)}</span>
                            <button className={styles.fileChipRemove} onClick={() => removeFile(f.name)} type="button">
                                <X size={14} />
                            </button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

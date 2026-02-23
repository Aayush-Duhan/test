'use client';

import { useState } from 'react';

interface Language {
  id: string;
  name: string;
}

const languages: Language[] = [
  { id: 'Teradata', name: 'Teradata' },
  { id: 'Oracle', name: 'Oracle' },
  { id: 'SqlServer', name: 'SQL Server' },
  { id: 'BigQuery', name: 'Google BigQuery' },
  { id: 'Redshift', name: 'Amazon Redshift' },
  { id: 'Databricks', name: 'Databricks SQL' },
  { id: 'Greenplum', name: 'Greenplum' },
  { id: 'Sybase', name: 'Sybase IQ' },
  { id: 'Postgresql', name: 'PostgreSQL' },
  { id: 'Netezza', name: 'Netezza' },
  { id: 'Spark', name: 'Spark SQL' },
  { id: 'Vertica', name: 'Vertica' },
  { id: 'Hive', name: 'Hive' },
  { id: 'Db2', name: 'IBM DB2' },
];

interface LanguageSelectorProps {
  selectedLanguage?: string;
  onLanguageChange?: (language: Language) => void;
}

export function LanguageSelector({ selectedLanguage = 'Oracle', onLanguageChange }: LanguageSelectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [selected, setSelected] = useState(languages.find((l) => l.id === selectedLanguage) || languages[0]);

  const handleSelect = (language: Language) => {
    setSelected(language);
    setIsOpen(false);
    onLanguageChange?.(language);
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 text-neutral-400 hover:text-white hover:bg-neutral-800"
        style={{ backgroundColor: '#262626' }}
      >
        <span>{selected.name}</span>
        <svg
          className={`w-3.5 h-3.5 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div
            className="absolute left-0 mt-2 z-50 min-w-[200px] rounded-xl shadow-xl overflow-hidden"
            style={{
              backgroundColor: '#171717',
              border: '1px solid #404040',
              maxHeight: '200px',
              overflowY: 'auto',
            }}
          >
            <div className="p-1">
              {languages.map((language) => (
                <button
                  type="button"
                  key={language.id}
                  onClick={() => handleSelect(language)}
                  className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-left text-xs transition-all duration-150"
                  style={{
                    backgroundColor: selected.id === language.id ? '#262626' : 'transparent',
                    color: selected.id === language.id ? '#ffffff' : '#a0a0a5',
                  }}
                >
                  <span>{language.name}</span>
                  {selected.id === language.id && (
                    <svg className="w-4 h-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export type { Language };

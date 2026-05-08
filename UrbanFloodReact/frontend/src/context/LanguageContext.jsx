import { createContext, useContext, useState, useMemo } from 'react';

const LanguageContext = createContext();

LanguageContext.displayName = 'LanguageContext';

export function LanguageProvider({ children }) {
    const [lang, setLang] = useState('en');
    const toggle = () => setLang(l => l === 'en' ? 'kn' : 'en');
    const value = useMemo(() => ({ lang, toggle }), [lang]);
    return (
        <LanguageContext.Provider value={value}>
            {children}
        </LanguageContext.Provider>
    );
}

export function useLanguage() {
    return useContext(LanguageContext);
}

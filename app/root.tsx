import { useStore } from '@nanostores/react';
import { Routes, Route } from 'react-router-dom';
import { useEffect } from 'react';
import { Header } from './components/header/Header';

import { themeStore } from './lib/stores/theme';
import Index from './routes/_index';

import './index.css';
import { SidebarProvider, SidebarTrigger } from './components/ui/sidebar';
import { SessionSidebar } from './components/ui/SessionSidebar';

function ThemeInjector() {
  const theme = useStore(themeStore);

  useEffect(() => {
    document.querySelector('html')?.setAttribute('data-theme', theme);
  }, [theme]);

  return null;
}

function StyleInjector() {
  useEffect(() => {
    // Add favicon
    const faviconLink = document.createElement('link');
    faviconLink.rel = 'icon';
    faviconLink.href = '/EY.svg';
    faviconLink.type = 'image/svg+xml';
    document.head.appendChild(faviconLink);

    // Add Google Fonts
    const fontLink1 = document.createElement('link');
    fontLink1.rel = 'preconnect';
    fontLink1.href = 'https://fonts.googleapis.com';
    document.head.appendChild(fontLink1);

    const fontLink2 = document.createElement('link');
    fontLink2.rel = 'preconnect';
    fontLink2.href = 'https://fonts.gstatic.com';
    fontLink2.crossOrigin = 'anonymous';
    document.head.appendChild(fontLink2);

    const fontLink3 = document.createElement('link');
    fontLink3.rel = 'stylesheet';
    fontLink3.href = 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap';
    document.head.appendChild(fontLink3);

    // Theme initialization script
    const themeScript = document.createElement('script');
    themeScript.textContent = `
      function setTutorialKitTheme() {
        let theme = localStorage.getItem('bolt_theme');
        if (!theme) {
          theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        }
        document.querySelector('html')?.setAttribute('data-theme', theme);
      }
      setTutorialKitTheme();
    `;
    document.head.appendChild(themeScript);
  }, []);

  return null;
}

export default function App() {
  return (
    <>
      <StyleInjector />
      <ThemeInjector />
      <div className="flex h-full w-full flex-col overflow-hidden">
        <Header />
        <SidebarProvider
          defaultOpen={false}
          className="flex-1 min-h-0 [--sidebar:#0b0c10] [--sidebar-foreground:#ffffff] [--sidebar-border:#1f2025] [--sidebar-accent:#161820] [--sidebar-accent-foreground:#ffffff] bg-[#07080c]"
        >
          <SidebarTrigger className="fixed left-3 top-[56px] z-40 md:hidden border border-[#1f2025] bg-[#0f1118] text-white shadow-lg hover:bg-[#171a23] hover:text-white" />
          <div className="relative flex min-h-0 flex-1 bg-[#07080c]">
            <SessionSidebar />
            <main className="h-full min-h-0 min-w-0 flex-1 overflow-hidden">
              <Routes>
                <Route path="/" element={<Index />} />
                <Route path="/chat/:id" element={<Index />} />
              </Routes>
            </main>
          </div>
        </SidebarProvider>
      </div>
    </>
  );
}

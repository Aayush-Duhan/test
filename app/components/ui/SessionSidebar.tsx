'use client';

import * as React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { ChevronRight, FolderOpen, Grid3X3 } from 'lucide-react';
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  useSidebar,
} from '~/components/ui/sidebar';
import { db, type ChatHistoryItem } from '~/lib/persistence/useChatHistory';
import { getAll } from '~/lib/persistence';

interface SessionSidebarProps {
  selectedSessionId?: string | null;
  reloadKey?: number;
}

const SIDEBAR_HOVER_OPEN_DELAY_MS = 100;
const SIDEBAR_HOVER_CLOSE_DELAY_MS = 180;

export function SessionSidebar({ selectedSessionId = null, reloadKey = 0 }: SessionSidebarProps) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { isMobile, setOpen: setSidebarOpen } = useSidebar();
  const [isSidebarHovered, setIsSidebarHovered] = React.useState(false);
  const [sessionsOpen, setSessionsOpen] = React.useState(false);
  const hoverTimerRef = React.useRef<number | null>(null);
  const isDashboard = pathname === '/';
  const isSessionsPage = pathname.startsWith('/chat/');
  const activeSessionId = selectedSessionId ?? (isSessionsPage ? pathname.split('/chat/')[1] ?? null : null);

  const [sessions, setSessions] = React.useState<ChatHistoryItem[]>([]);
  const [loading, setLoading] = React.useState(false);

  const loadSessions = React.useCallback(async () => {
    if (!db) {
      setSessions([]);
      return;
    }

    setLoading(true);

    try {
      const raw = await getAll(db);
      raw.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
      setSessions(raw);
    } catch {
      setSessions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadSessions();
  }, [loadSessions, reloadKey]);

  const clearHoverTimer = React.useCallback(() => {
    if (hoverTimerRef.current !== null) {
      window.clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
  }, []);

  React.useEffect(() => {
    if (isMobile) {
      clearHoverTimer();
    } else {
      clearHoverTimer();

      const delay = isSidebarHovered ? SIDEBAR_HOVER_OPEN_DELAY_MS : SIDEBAR_HOVER_CLOSE_DELAY_MS;

      hoverTimerRef.current = window.setTimeout(() => {
        setSidebarOpen(isSidebarHovered);
        hoverTimerRef.current = null;
      }, delay);
    }

    return () => {
      clearHoverTimer();
    };
  }, [clearHoverTimer, isMobile, isSidebarHovered, setSidebarOpen]);

  const handleSidebarMouseEnter = React.useCallback(() => {
    if (!isMobile) {
      setIsSidebarHovered(true);
    }
  }, [isMobile]);

  const handleSidebarMouseLeave = React.useCallback(() => {
    if (!isMobile) {
      setIsSidebarHovered(false);
    }
  }, [isMobile]);

  return (
    <>
      <Sidebar
        collapsible="icon"
        onMouseEnter={handleSidebarMouseEnter}
        onMouseLeave={handleSidebarMouseLeave}
        className="top-[var(--header-height)] bottom-0 h-auto [--sidebar-width:16rem] border-r border-[#1f2025] bg-[#0b0c10] text-white"
      >
        <SidebarHeader className="border-[#1f2025] p-2">
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                onClick={() => navigate('/')}
                isActive={isDashboard}
                className="h-8 text-white hover:text-white group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:size-8"
              >
                <Grid3X3 className="size-4 text-white" />
                <span className="font-medium text-white group-data-[collapsible=icon]:hidden">Dashboard</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>

          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton
                onClick={() => navigate('/')}
                isActive={isSessionsPage}
                className="h-8 text-white hover:text-white group-data-[collapsible=icon]:justify-center group-data-[collapsible=icon]:size-8"
              >
                <FolderOpen className="size-4 text-white" />
                <span className="font-medium text-white group-data-[collapsible=icon]:hidden">Sessions</span>
                <ChevronRight
                  onClick={(e) => {
                    e.stopPropagation();
                    setSessionsOpen((prev) => !prev);
                  }}
                  className={`ml-auto size-4 cursor-pointer text-white/60 transition-transform hover:text-white group-data-[collapsible=icon]:hidden ${sessionsOpen ? 'rotate-90' : ''}`}
                />
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>

        <SidebarContent className="min-h-0 px-0">
          {sessionsOpen && (
            <SidebarGroup className="p-0">
              <SidebarGroupContent>
                <SidebarMenuSub className="max-h-64 overflow-y-auto">
                  {loading && (
                    <SidebarMenuSubItem>
                      <p className="px-2 py-1 text-xs text-white/60">Loading sessions...</p>
                    </SidebarMenuSubItem>
                  )}
                  {sessions.map((session) => {
                    const active = session.id === activeSessionId || session.urlId === activeSessionId;

                    return (
                      <SidebarMenuSubItem key={session.id}>
                        <SidebarMenuSubButton
                          asChild
                          isActive={active}
                          className="text-white hover:text-white data-[active=true]:text-white"
                        >
                          <button
                            type="button"
                            onClick={() => navigate(`/chat/${session.urlId || session.id}`)}
                            className="w-full text-left text-white"
                          >
                            <span>{session.description || session.urlId || `Session ${session.id}`}</span>
                          </button>
                        </SidebarMenuSubButton>
                      </SidebarMenuSubItem>
                    );
                  })}
                </SidebarMenuSub>
              </SidebarGroupContent>
            </SidebarGroup>
          )}
        </SidebarContent>
      </Sidebar>
    </>
  );
}

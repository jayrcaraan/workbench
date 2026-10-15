"use client";

import React, { createContext, useContext } from "react";
import { CopilotKit } from "@copilotkit/react-core";
import "@copilotkit/react-core/v2/styles.css";
import { useSessionStore } from "@/lib/sessions";

export const AGENT_NAME = "sandbox_agent";

type Store = ReturnType<typeof useSessionStore>;
const SessionsContext = createContext<Store | null>(null);
export const useSessions = () => {
  const s = useContext(SessionsContext);
  if (!s) throw new Error("useSessions outside Providers");
  return s;
};

/**
 * One CopilotKit thread per session. Switching sessions remounts the chat on that thread, so its messages
 * and published apps come back; its sandbox keeps running independently of the others.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  const store = useSessionStore();
  if (!store.sessions || !store.activeId) return null;
  return (
    <SessionsContext.Provider value={store}>
      <CopilotKit
        key={store.activeId}
        runtimeUrl="/api/copilotkit"
        agent={AGENT_NAME}
        threadId={store.activeId}
        showDevConsole={false}
        enableInspector={false}
      >
        {children}
      </CopilotKit>
    </SessionsContext.Provider>
  );
}

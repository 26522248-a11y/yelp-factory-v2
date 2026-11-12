import { create } from "zustand";
import { persist } from "zustand/middleware";

type Theme = "dark" | "light";

interface UiStore {
  theme: Theme;
  sidebarCollapsed: boolean;
  commandOpen: boolean;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  toggleSidebar: () => void;
  setCommandOpen: (v: boolean) => void;
}

export const useUi = create<UiStore>()(
  persist(
    (set, get) => ({
      theme: "dark",
      sidebarCollapsed: false,
      commandOpen: false,
      setTheme: (theme) => {
        document.documentElement.classList.toggle("light", theme === "light");
        document.documentElement.classList.toggle("dark", theme === "dark");
        set({ theme });
      },
      toggleTheme: () => get().setTheme(get().theme === "dark" ? "light" : "dark"),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      setCommandOpen: (commandOpen) => set({ commandOpen }),
    }),
    { name: "yfcp-ui", partialize: (s) => ({ theme: s.theme, sidebarCollapsed: s.sidebarCollapsed }) }
  )
);

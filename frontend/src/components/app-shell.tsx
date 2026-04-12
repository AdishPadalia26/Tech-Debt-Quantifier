"use client";

import { useMemo } from "react";
import { usePathname } from "next/navigation";

import { AppSidebar } from "@/components/app-sidebar";
import { HeaderAuth } from "@/components/HeaderAuth";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";

const TITLES: Record<string, string> = {
  "/": "Analyzer",
  "/portfolio": "Portfolio",
  "/import": "Repository Import",
  "/debug": "Debug Console",
};

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const title = useMemo(() => {
    if (pathname.startsWith("/scans/")) return "Scan Detail";
    if (pathname.startsWith("/repositories/")) return "Repository Detail";
    return TITLES[pathname] ?? "Tech Debt Quantifier";
  }, [pathname]);

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur">
          <div className="flex items-center gap-2">
            <SidebarTrigger />
            <span className="text-sm text-muted-foreground">{title}</span>
          </div>
          <HeaderAuth />
        </header>
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}

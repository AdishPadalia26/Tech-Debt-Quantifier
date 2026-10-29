"use client";

import Link from "next/link";
import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { BarChart3, FolderGit2, Home, ShieldCheck } from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";

const navItems = [
  { title: "Analyzer", url: "/", icon: Home },
  { title: "Portfolio", url: "/portfolio", icon: BarChart3 },
  { title: "Import", url: "/import", icon: FolderGit2 },
  // Internal tooling — not part of the product surface.
  ...(process.env.NODE_ENV === "development"
    ? [{ title: "Debug", url: "/debug", icon: ShieldCheck }]
    : []),
];

export function AppSidebar() {
  const pathname = usePathname();
  const { collapsed, setMobileOpen } = useSidebar();

  // Close the mobile drawer after navigating.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname, setMobileOpen]);

  return (
    <Sidebar variant="inset" collapsible="icon">
      <SidebarHeader>
        <div className="flex items-center gap-3 px-2 py-1">
          <svg
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            aria-label="Tech Debt Quantifier"
            className="shrink-0 text-primary"
          >
            <rect x="3" y="3" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
            <rect
              x="13"
              y="3"
              width="8"
              height="8"
              rx="1.5"
              stroke="currentColor"
              strokeWidth="1.5"
              opacity="0.5"
            />
            <rect
              x="3"
              y="13"
              width="8"
              height="8"
              rx="1.5"
              stroke="currentColor"
              strokeWidth="1.5"
              opacity="0.5"
            />
            <path
              d="M13 17h8M17 13v8"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
          {!collapsed && (
            <div className="min-w-0">
              <p className="text-sm font-semibold tracking-tight text-foreground">TDQ</p>
              <p className="text-xs text-muted-foreground">Tech Debt Quantifier</p>
            </div>
          )}
        </div>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Navigation</SidebarGroupLabel>
          <SidebarMenu>
            {navItems.map((item) => {
              const isActive =
                item.url === "/" ? pathname === item.url : pathname.startsWith(item.url);
              return (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton asChild isActive={isActive}>
                    <Link href={item.url}>
                      <item.icon className="size-4 shrink-0" />
                      {!collapsed && <span>{item.title}</span>}
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

    </Sidebar>
  );
}

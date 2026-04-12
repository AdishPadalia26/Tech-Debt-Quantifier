"use client";

import * as React from "react";
import { PanelLeft } from "lucide-react";
import { Slot } from "@radix-ui/react-slot";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type SidebarContextValue = {
  collapsed: boolean;
  mobileOpen: boolean;
  setCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
  setMobileOpen: React.Dispatch<React.SetStateAction<boolean>>;
  toggleSidebar: () => void;
};

const SidebarContext = React.createContext<SidebarContextValue | null>(null);

function useSidebar() {
  const context = React.useContext(SidebarContext);
  if (!context) {
    throw new Error("useSidebar must be used within SidebarProvider");
  }
  return context;
}

function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = React.useState(false);
  const [mobileOpen, setMobileOpen] = React.useState(false);

  const toggleSidebar = React.useCallback(() => {
    if (typeof window !== "undefined" && window.innerWidth < 768) {
      setMobileOpen((open) => !open);
      return;
    }
    setCollapsed((value) => !value);
  }, []);

  return (
    <SidebarContext.Provider
      value={{ collapsed, mobileOpen, setCollapsed, setMobileOpen, toggleSidebar }}
    >
      <div className="min-h-screen bg-background md:flex">{children}</div>
    </SidebarContext.Provider>
  );
}

function Sidebar({
  className,
  children,
}: React.HTMLAttributes<HTMLDivElement> & {
  collapsible?: "icon";
  variant?: "inset";
}) {
  const { collapsed, mobileOpen, setMobileOpen } = useSidebar();

  return (
    <>
      <div
        className={cn(
          "fixed inset-0 z-30 bg-black/50 backdrop-blur-sm md:hidden",
          mobileOpen ? "block" : "hidden"
        )}
        onClick={() => setMobileOpen(false)}
      />
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 flex h-screen w-72 flex-col border-r border-border bg-[#131210] transition-transform duration-300 md:translate-x-0",
          collapsed ? "md:w-20" : "md:w-72",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
          className
        )}
      >
        {children}
      </aside>
    </>
  );
}

function SidebarHeader({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("border-b border-border p-3", className)} {...props} />;
}

function SidebarContent({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex-1 overflow-y-auto p-3", className)} {...props} />;
}

function SidebarFooter({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("border-t border-border p-3", className)} {...props} />;
}

function SidebarGroup({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("mb-6 space-y-2", className)} {...props} />;
}

function SidebarGroupLabel({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  const { collapsed } = useSidebar();
  return (
    <div
      className={cn(
        "px-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground",
        collapsed && "md:hidden",
        className
      )}
      {...props}
    />
  );
}

function SidebarMenu({
  className,
  ...props
}: React.HTMLAttributes<HTMLUListElement>) {
  return <ul className={cn("space-y-1", className)} {...props} />;
}

function SidebarMenuItem({
  className,
  ...props
}: React.LiHTMLAttributes<HTMLLIElement>) {
  return <li className={cn("list-none", className)} {...props} />;
}

function SidebarMenuButton({
  className,
  asChild = false,
  isActive = false,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  asChild?: boolean;
  isActive?: boolean;
}) {
  const { collapsed, setMobileOpen } = useSidebar();
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      className={cn(
        "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
        isActive && "bg-muted text-foreground",
        collapsed && "md:justify-center md:px-0",
        className
      )}
      onClick={() => setMobileOpen(false)}
      {...props}
    />
  );
}

function SidebarTrigger({
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { toggleSidebar } = useSidebar();
  return (
    <Button
      variant="ghost"
      size="icon"
      className={cn("text-muted-foreground hover:text-foreground", className)}
      onClick={toggleSidebar}
      {...props}
    >
      <PanelLeft className="size-4" />
      <span className="sr-only">Toggle sidebar</span>
    </Button>
  );
}

function SidebarInset({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  const { collapsed } = useSidebar();
  return (
    <div
      className={cn(
        "flex min-h-screen flex-1 flex-col transition-[margin] duration-300",
        collapsed ? "md:ml-20" : "md:ml-72",
        className
      )}
      {...props}
    />
  );
}

export {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
  useSidebar,
};

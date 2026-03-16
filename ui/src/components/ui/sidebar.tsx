"use client"

// Minimal sidebar stub — app uses custom AppSidebar component
import * as React from "react"
import { cn } from "@/lib/utils"

export function SidebarProvider({ children, className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex min-h-screen w-full", className)} {...props}>{children}</div>
}

export function Sidebar({ children, className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <aside className={cn("flex flex-col", className)} {...props}>{children}</aside>
}

export function SidebarHeader({ children, className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-2 p-2", className)} {...props}>{children}</div>
}

export function SidebarContent({ children, className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-1 flex-col gap-2 overflow-auto p-2", className)} {...props}>{children}</div>
}

export function SidebarFooter({ children, className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-2 p-2", className)} {...props}>{children}</div>
}

export function SidebarGroup({ children, className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1", className)} {...props}>{children}</div>
}

export function SidebarGroupLabel({ children, className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-2 text-xs font-medium text-muted-foreground", className)} {...props}>{children}</div>
}

export function SidebarGroupContent({ children, className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("", className)} {...props}>{children}</div>
}

export function SidebarMenu({ children, className, ...props }: React.HTMLAttributes<HTMLUListElement>) {
  return <ul className={cn("flex flex-col gap-1", className)} {...props}>{children}</ul>
}

export function SidebarMenuItem({ children, className, ...props }: React.HTMLAttributes<HTMLLIElement>) {
  return <li className={cn("", className)} {...props}>{children}</li>
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function SidebarMenuButton({ children, className, isActive, asChild, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { isActive?: boolean; asChild?: boolean }) {
  return (
    <button
      className={cn(
        "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-accent hover:text-accent-foreground",
        isActive && "bg-accent text-accent-foreground font-medium",
        className
      )}
      {...props}
    >
      {children}
    </button>
  )
}

export function SidebarInset({ children, className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return <main className={cn("flex flex-1 flex-col", className)} {...props}>{children}</main>
}

export function SidebarTrigger({ className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={cn("", className)} {...props} />
}

export function SidebarRail({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("", className)} {...props} />
}

export function useSidebar() {
  return { state: 'expanded' as const, open: true, setOpen: () => {}, isMobile: false, toggleSidebar: () => {} }
}

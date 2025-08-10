import * as React from "react"

export const ScrollArea = ({ children, className }: { children: React.ReactNode; className?: string }) => (
  <div className={`overflow-y-auto ${className}`}>{children}</div>
)

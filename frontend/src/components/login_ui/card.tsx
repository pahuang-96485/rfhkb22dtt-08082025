import * as React from "react"

export const Card = ({ children, className }: { children: React.ReactNode; className?: string }) => (
  <div className={`border rounded-xl shadow-sm bg-white ${className}`}>{children}</div>
)

export const CardContent = ({ children, className }: { children: React.ReactNode; className?: string }) => (
  <div className={`p-4 ${className}`}>{children}</div>
)

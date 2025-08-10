// src/components/login_ui/input.tsx
import * as React from "react"

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, ...props }, ref) => {
  return (
    <input
      ref={ref}
      className={`
        px-4 py-2
        border rounded-md
        outline-none focus:ring-2 focus:ring-blue-500
        text-gray-900            
        placeholder-gray-400   
        ${className}
      `}
      {...props}
    />
  )
})

Input.displayName = "Input"

export { Input }
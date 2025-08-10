import * as React from "react"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "ghost"
  size?: "default" | "icon"
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = "", variant = "default", size = "default", ...props }, ref) => {
    let variantClass = ""
    if (variant === "ghost") {
      variantClass = "bg-transparent text-blue-600 hover:underline"
    } else {
      variantClass = "bg-blue-500 text-white hover:bg-blue-600"
    }

    let sizeClass = ""
    if (size === "icon") {
      sizeClass = "p-2 w-10 h-10"
    } else {
      sizeClass = "px-4 py-2"
    }

    return (
      <button
        ref={ref}
        className={`${sizeClass} ${variantClass} rounded-md font-medium ${className}`}
        {...props}
      />
    )
  }
)

Button.displayName = "Button"

export { Button }

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary: "bg-accent text-white hover:bg-accent-hover",
        secondary: "bg-bg text-text border border-border hover:bg-panel",
        ghost: "hover:bg-panel text-text",
        destructive: "border border-border bg-bg text-danger hover:bg-danger-bg",
        destructiveFilled: "bg-danger text-white hover:bg-danger/90",
      },
      size: {
        default: "h-[36px] px-4 py-2 md:h-[36px] max-md:h-[44px]",
        sm: "h-[32px] px-3 text-xs md:h-[32px] max-md:h-[44px]",
        lg: "h-[40px] px-6 md:h-[40px] max-md:h-[44px]",
        icon: "h-[36px] w-[36px] max-md:h-[44px] max-md:w-[44px]",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };

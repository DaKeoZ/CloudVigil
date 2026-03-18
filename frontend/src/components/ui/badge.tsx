import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset transition-colors",
  {
    variants: {
      variant: {
        online:  "bg-emerald-500/10 text-emerald-400 ring-emerald-500/20",
        offline: "bg-slate-700/50   text-slate-400  ring-slate-700/50",
        default: "bg-slate-800      text-slate-300  ring-slate-700/50",
        warning: "bg-amber-500/10   text-amber-400  ring-amber-500/20",
        danger:  "bg-red-500/10     text-red-400    ring-red-500/20",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };

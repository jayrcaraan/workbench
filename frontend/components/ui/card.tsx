import React from "react";

/** shadcn-style card primitives. Plain div/CSS so they stay dependency-free. */
type DivProps = React.HTMLAttributes<HTMLDivElement>;
const cx = (...c: (string | false | undefined)[]) => c.filter(Boolean).join(" ");

export function Card({ className, ...p }: DivProps) {
  return <div className={cx("card", className)} {...p} />;
}
export function CardHeader({ className, ...p }: DivProps) {
  return <div className={cx("card-header", className)} {...p} />;
}
export function CardTitle({ className, ...p }: DivProps) {
  return <div className={cx("card-title", className)} {...p} />;
}
export function CardDescription({ className, ...p }: DivProps) {
  return <div className={cx("card-description", className)} {...p} />;
}
/** Top-right slot of a header (buttons, badges, menus). */
export function CardAction({ className, ...p }: DivProps) {
  return <div className={cx("card-action", className)} {...p} />;
}
export function CardContent({ className, ...p }: DivProps) {
  return <div className={cx("card-content", className)} {...p} />;
}
export function CardFooter({ className, ...p }: DivProps) {
  return <div className={cx("card-footer", className)} {...p} />;
}

type Tone = "default" | "secondary" | "outline" | "success" | "warning" | "destructive";
export function Badge({ tone = "secondary", className, ...p }: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) {
  return <span className={cx("badge", `badge-${tone}`, className)} {...p} />;
}

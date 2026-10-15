import React from "react";
import "./globals.css";
import { Providers } from "./providers";

export const metadata = {
  title: "Workbench",
  description: "Describe an app; an agent builds and hosts it in an isolated sandbox.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}

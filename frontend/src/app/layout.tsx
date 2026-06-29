import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { PostHogProvider } from "@/components/PostHogProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "AgriTwin Dashboard",
  description: "AI Greenhouse Digital Twin Platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider>
      <html lang="id" className="dark" suppressHydrationWarning>
        <body
          className="min-h-screen bg-gray-950 text-gray-200 antialiased"
          suppressHydrationWarning
        >
          <PostHogProvider>{children}</PostHogProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}

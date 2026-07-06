import type { Metadata, Viewport } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { PostHogProvider } from "@/components/PostHogProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "Cahyo AgriTwin Dashboard",
  description: "AI Greenhouse Digital Twin Platform",
  manifest: "/manifest.json",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Cahyo AgriTwin",
  },
};

export const viewport: Viewport = {
  themeColor: "#1b5e20",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider>
      <html lang="id" className="dark" suppressHydrationWarning>
        <head>
          <link rel="apple-touch-icon" href="/icon.svg" />
        </head>
        <body
          className="min-h-screen bg-gray-950 text-gray-200 antialiased"
          suppressHydrationWarning
        >
          <PostHogProvider>{children}</PostHogProvider>
          {/* Register service worker untuk PWA offline support */}
          <script dangerouslySetInnerHTML={{
            __html: `if('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js')`
          }} />
        </body>
      </html>
    </ClerkProvider>
  );
}

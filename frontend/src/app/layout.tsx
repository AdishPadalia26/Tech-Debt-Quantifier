import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { HeaderAuth } from "@/components/HeaderAuth";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "Tech Debt Quantifier",
  description: "Turn technical debt into business decisions",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <div className="flex justify-end p-4 bg-gray-900 border-b border-gray-800">
          <HeaderAuth />
        </div>
        {children}
      </body>
    </html>
  );
}

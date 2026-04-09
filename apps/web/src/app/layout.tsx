import type { Metadata } from "next";
import { DM_Serif_Display, DM_Serif_Text, Libre_Franklin, Geist_Mono } from "next/font/google";
import "./globals.css";

const dmSerifDisplay = DM_Serif_Display({
  weight: "400",
  style: ["normal", "italic"],
  variable: "--font-dm-serif-display",
  subsets: ["latin"],
});

const dmSerifText = DM_Serif_Text({
  weight: "400",
  style: ["normal", "italic"],
  variable: "--font-dm-serif-text",
  subsets: ["latin"],
});

const libreFranklin = Libre_Franklin({
  variable: "--font-libre-franklin",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "InnovateUS Feedback",
  description: "Post-course feedback tool for InnovateUS",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${dmSerifDisplay.variable} ${dmSerifText.variable} ${libreFranklin.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}

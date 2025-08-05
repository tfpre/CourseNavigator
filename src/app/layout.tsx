import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Cornell Course Navigator',
  description: 'AI-powered course discovery with graph algorithms',
  keywords: ['cornell', 'courses', 'graph algorithms', 'AI', 'education'],
  authors: [{ name: 'Cornell CS Student' }],
  openGraph: {
    title: 'Cornell Course Navigator',
    description: 'AI-powered course discovery with graph algorithms',
    type: 'website',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <div className="min-h-screen bg-gray-50">
          {children}
        </div>
      </body>
    </html>
  );
}
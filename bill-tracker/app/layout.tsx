import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {
  title: 'Bill tracker',
  description:
    'A simple place to track business bills, due dates, and payment status.',
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

import './globals.css'
import type { Metadata } from 'next'
import { Space_Grotesk } from 'next/font/google'

const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-space-grotesk',
})

export const metadata: Metadata = {
  title: 'Antibiotic AI CDSS | FYP Project',
  description: 'Clinical Decision Support System for Antibiotic Recommendations',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={`${spaceGrotesk.variable} min-h-screen bg-gray-50 font-sans antialiased`}>
        {children}
      </body>
    </html>
  )
}

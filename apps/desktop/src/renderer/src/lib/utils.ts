import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** shadcn/ui class helper. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

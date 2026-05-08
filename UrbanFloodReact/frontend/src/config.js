/** config.js — single source of truth for API URL */
// Default to the GCP backend URL for production builds. During local development
// set `VITE_API_URL` when running `npm run dev` to point to a local backend.
export const API_URL = import.meta.env.VITE_API_URL ?? 'https://urbanflood-backend-244754524479.asia-south1.run.app';

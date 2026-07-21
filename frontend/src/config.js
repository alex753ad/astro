export const API_BASE = import.meta.env.VITE_API_URL || 'https://astro-production-abcc.up.railway.app/api/v1';
export const BACKEND_BASE = API_BASE.replace('/api/v1', '');

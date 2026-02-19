import axios from 'axios';

const API_URL = 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
  timeout: 120000, // 2 min — some endpoints (geocoding, simulation) are slow
});

export default api;
export { API_URL };

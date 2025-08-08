/**
 * API service for communicating with the tarsy-bot backend
 */

import axios from 'axios';
import { AlertResponse } from '../types';

// Configure axios defaults
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor
api.interceptors.request.use(
  (config) => {
    console.log(`API Request: ${config.method?.toUpperCase()} ${config.url}`);
    return config;
  },
  (error) => {
    console.error('API Request Error:', error);
    return Promise.reject(error);
  }
);

// Response interceptor
api.interceptors.response.use(
  (response) => {
    console.log(`API Response: ${response.status} ${response.config.url}`);
    return response;
  },
  (error) => {
    console.error('API Response Error:', error);
    return Promise.reject(error);
  }
);

export class ApiService {
  /**
   * Submit an alert for processing (flexible data structure)
   */
  static async submitAlert(alertData: Record<string, any>): Promise<AlertResponse> {
    try {
      const response = await api.post<AlertResponse>('/alerts', alertData);
      return response.data;
    } catch (error) {
      console.error('Error submitting alert:', error);
      throw new Error('Failed to submit alert');
    }
  }


  /**
   * Get supported alert types for the development/testing web interface dropdown.
   * 
   * NOTE: These alert types are used only for dropdown selection in this
   * development/testing interface. In production, external clients (like Alert Manager)
   * can submit any alert type. The system analyzes all alert types using the provided
   * runbook and all available MCP tools.
   */
  static async getAlertTypes(): Promise<string[]> {
    try {
      const response = await api.get<string[]>('/alert-types');
      return response.data;
    } catch (error) {
      console.error('Error getting alert types:', error);
      throw new Error('Failed to get alert types');
    }
  }

  /**
   * Health check
   */
  static async healthCheck(): Promise<{ status: string; message?: string }> {
    try {
      const response = await api.get('/health');
      return response.data;
    } catch (error) {
      console.error('Health check failed:', error);
      throw new Error('Backend is not available');
    }
  }
}

export default ApiService; 
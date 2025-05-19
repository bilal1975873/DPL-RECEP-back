import axios from 'axios';
import type { Visitor } from '../types';

const API_URL = 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const visitorService = {
  async createVisitor(visitor: Visitor) {
    const response = await api.post<Visitor>('/visitors/', visitor);
    return response.data;
  },

  async getVisitors() {
    const response = await api.get<Visitor[]>('/visitors/');
    return response.data;
  },

  async getVisitorByCNIC(cnic: string) {
    const response = await api.get<Visitor>('/visitors/' + cnic);
    return response.data;
  },

  async updateVisitor(cnic: string, visitor: Partial<Visitor>) {
    const response = await api.put<Visitor>('/visitors/' + cnic, visitor);
    return response.data;
  },

  async deleteVisitor(cnic: string) {
    await api.delete('/visitors/' + cnic);
  },
  async processMessage(message: string, currentStep: string, visitorInfo: Partial<Visitor>) {
    const response = await api.post('/process-message/', {
      message,
      current_step: currentStep,
      visitor_info: visitorInfo,
    });
    return {
      response: response.data.response,
      nextStep: response.data.next_step,
      visitorInfo: response.data.visitor_info,
    };
  },
};
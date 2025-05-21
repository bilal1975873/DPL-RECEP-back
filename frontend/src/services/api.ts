import axios from 'axios';
import type { Visitor, ChatState } from '../types';

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
    const response = await api.get<Visitor>(`/visitors/${cnic}`);
    return response.data;
  },

  async updateVisitor(cnic: string, visitor: Partial<Visitor>) {
    const response = await api.put<Visitor>(`/visitors/${cnic}`, visitor);
    return response.data;
  },

  async deleteVisitor(cnic: string) {
    await api.delete(`/visitors/${cnic}`);
  },

  async processMessage(
    message: string,
    currentStep: string,
    visitorInfo: ChatState['visitorInfo']
  ) {
    const response = await api.post<{
      response: string;
      next_step: string;
      visitor_info: ChatState['visitorInfo'];
    }>('/process-message/', {
      message,
      current_step: currentStep,
      visitor_info: {
        ...visitorInfo,
        employee_selection_mode: visitorInfo.employee_selection_mode || false,
        employee_matches: visitorInfo.employee_matches || [],
        visitor_type: visitorInfo.type || visitorInfo.visitor_type,
        visitor_name: visitorInfo.full_name || visitorInfo.visitor_name,
        visitor_cnic: visitorInfo.cnic || visitorInfo.visitor_cnic,
        visitor_phone: visitorInfo.phone || visitorInfo.visitor_phone,
        visitor_email: visitorInfo.email,
        host_confirmed: visitorInfo.host,
        host_email: visitorInfo.host_email,
        host_requested: visitorInfo.host_requested,
        purpose: visitorInfo.purpose,
        scheduled_meeting: visitorInfo.scheduled_meeting,
      },
    });

    return {
      response: response.data.response,
      nextStep: response.data.next_step,
      visitorInfo: response.data.visitor_info,
    };
  },
};
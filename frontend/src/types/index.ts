export interface Visitor {
  type: 'guest' | 'vendor' | 'prescheduled';
  full_name: string;
  cnic: string | null;
  phone: string;
  email?: string;
  host: string;
  host_email?: string;
  purpose: string;
  entry_time: string;
  exit_time?: string;
  is_group_visit: boolean;
  group_id?: string;
  total_members: number;
  group_members: GroupMember[];
  scheduled_time?: string;
  scheduled_meeting?: {
    scheduled_time: string;
    purpose: string;
    original_event: Record<string, unknown>;
  };
}

export interface GroupMember {
  name: string;
  cnic: string;
  phone: string;
}

export interface Message {
  type: 'user' | 'bot';
  content: string;
  timestamp: Date;
}

export interface ChatState {
  messages: Message[];
  currentStep: string;
  visitorInfo: Partial<Visitor> & {
    registration_completed?: boolean;
    employee_selection_mode?: boolean;
    employee_matches?: Array<{
      displayName: string;
      email: string;
      department: string;
      jobTitle: string;
      id: string;
    }>;
    visitor_type?: string;
    visitor_name?: string;
    visitor_cnic?: string;
    visitor_phone?: string;
    visitor_email?: string;
    host_requested?: string;
    host_confirmed?: string;
    host_email?: string;
    purpose?: string;
    verification_status?: string;
    supplier?: string;
    group_id?: string;
    is_group_visit?: boolean;
    total_members?: number;
    scheduled_meeting?: {
      scheduled_time: string;
      purpose: string;
      original_event: Record<string, unknown>;
    };
  };
  isLoading: boolean;
}
export interface Visitor {
  type: 'guest' | 'vendor';
  full_name: string;
  cnic: string;
  phone: string;
  host: string;
  purpose: string;
  entry_time: string;
  exit_time?: string;
  is_group_visit: boolean;
  group_id?: string;
  total_members: number;
  group_members: GroupMember[];
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
    employee_matches?: unknown[];
  };
  isLoading: boolean;
}
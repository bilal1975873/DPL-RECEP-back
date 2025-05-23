import { useState } from 'react';
import { ChatContainer } from './components/ChatContainer';
import { visitorService } from './services/api';
import type { ChatState } from './types';
import dplLogo from '../DPL_LOGO_tagline.png';

const INITIAL_STATE: ChatState = {
  messages: [
    {
      type: 'bot',
      content: 'Welcome to DPL! I am your AI receptionist. Please select your visitor type:\n\n1. I am here as a guest\n2. I am a vendor\n3. I am here for a pre-scheduled meeting',
      timestamp: new Date(),
    },
  ],
  currentStep: 'visitor_type',
  visitorInfo: {},
  isLoading: false,
};

function App() {
  const [state, setState] = useState<ChatState>(INITIAL_STATE);

  const resetChat = () => {
    setState(INITIAL_STATE);
  };

  const handleSend = async (message: string) => {
    // If in completed state, reset the chat for new visitor
    if (state.currentStep === 'complete' && !state.isLoading) {
      resetChat();
      return;
    }

    // Add user message
    setState(prev => ({
      ...prev,
      messages: [
        ...prev.messages,
        { type: 'user', content: message, timestamp: new Date() },
      ],
      isLoading: true,
    }));

    try {
      // Process the message using AI
      const { response, nextStep, visitorInfo } = await visitorService.processMessage(
        message,
        state.currentStep,
        state.visitorInfo
      );
      
      // Check if registration is completed
      if (visitorInfo?.registration_completed) {
        // Add final message and update state
        setState(prev => ({
          ...prev,
          messages: [
            ...prev.messages,
            { type: 'bot', content: response, timestamp: new Date() },
            { 
              type: 'bot', 
              content: 'Type ok to start a new registration.', 
              timestamp: new Date() 
            },
          ],
          currentStep: 'complete',
          visitorInfo: { ...prev.visitorInfo, ...visitorInfo },
          isLoading: false,
        }));
        return;
      }

      // Normal message flow
      setState(prev => ({
        ...prev,
        messages: [
          ...prev.messages,
          { type: 'bot', content: response, timestamp: new Date() },
        ],
        currentStep: nextStep || prev.currentStep,
        visitorInfo: { ...prev.visitorInfo, ...visitorInfo },
        isLoading: false,
      }));
    } catch (error) {
      console.error('Error processing message:', error);
      setState(prev => ({
        ...prev,
        messages: [
          ...prev.messages,
          { 
            type: 'bot', 
            content: 'Sorry, I encountered an error. Please try again.', 
            timestamp: new Date() 
          },
        ],
        isLoading: false,
      }));
    }
  };

  return (
    <div className="fixed inset-0 w-screen h-screen bg-black overflow-hidden">
      {/* Background grid animation */}
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute inset-0 bg-grid transform -skew-y-12"></div>
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-red-900/5 to-black"></div>
      </div>

      {/* Side decorative elements */}
      <div className="fixed top-0 right-0 w-1/3 h-screen bg-gradient-to-l from-red-900/10 to-transparent pointer-events-none"></div>
      <div className="fixed top-0 left-0 w-1/3 h-screen bg-gradient-to-r from-red-900/10 to-transparent pointer-events-none"></div>

      {/* Main content */}
      <div className="relative z-10 container mx-auto px-4 min-h-screen flex flex-col">
        {/* Logo */}
        <div className="flex justify-center mb-8 pt-8">
          <img src={dplLogo} alt="DPL Logo" className="h-16 md:h-20" />
        </div>

        {/* Chat interface */}
        <div className="flex-1 flex flex-col">
          <ChatContainer
            messages={state.messages}
            isLoading={state.isLoading}
            onSend={handleSend}
          />
        </div>

        {/* Footer bar */}
        <div className="h-1 w-full bg-gradient-to-r from-red-900/20 via-red-600/40 to-red-900/20 fixed bottom-0 left-0"></div>
      </div>

      {/* Corner accents */}
      <div className="fixed top-0 right-0 w-32 h-32 bg-gradient-to-bl from-red-500/10 to-transparent"></div>
      <div className="fixed top-0 left-0 w-32 h-32 bg-gradient-to-br from-red-500/10 to-transparent"></div>
    </div>
  );
}

export default App;
import { useState } from 'react';
import { ChatContainer } from './components/ChatContainer';
import { visitorService } from './services/api';
import type { ChatState } from './types';
import logo from './assets/react.svg';

const fallbackLogo = (
  <div className="h-10 w-10 rounded-full bg-primary-100 flex items-center justify-center shadow">
    <span className="text-primary-700 font-bold text-lg">DPL</span>
  </div>
);

const INITIAL_STATE: ChatState = {
  messages: [
    {
      type: 'bot',
      content: 'Welcome to DPL! I am your AI receptionist. Please select your visitor type:',
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
              content: 'Click anywhere to start a new registration.', 
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

  const handleVisitorType = (type: string) => {
    handleSend(type);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-900 via-primary-700 to-black flex items-center justify-center p-4 relative">
      <div className="absolute inset-0 bg-white/10 backdrop-blur-sm z-0" />
      <div className="w-full max-w-2xl bg-white/90 rounded-3xl shadow-2xl overflow-hidden z-10 border border-primary-100">
        <div className="flex items-center gap-3 bg-primary-900 p-4">
          {logo ? (
            <img src={logo} alt="DPL Logo" className="h-10 w-10 rounded-full bg-white p-1 shadow" />
          ) : fallbackLogo}
          <h1 className="text-white text-2xl font-bold text-center flex-1">DPL AI Receptionist</h1>
        </div>
        <div className="p-6">
          {state.currentStep === 'visitor_type' && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
              <button
                onClick={() => handleVisitorType('guest')}
                className="btn-primary text-lg py-3"
              >
                I am a Guest
              </button>
              <button
                onClick={() => handleVisitorType('vendor')}
                className="btn-primary text-lg py-3"
              >
                I am a Vendor
              </button>
              <button
                onClick={() => handleVisitorType('3')}
                className="btn-primary text-lg py-3"
              >
                Pre-scheduled Meeting
              </button>
            </div>
          )}
          <div className="space-y-4">
            <ChatContainer
              messages={state.messages}
              onSend={handleSend}
              isLoading={state.isLoading}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
// src/app/page.tsx
"use client";

import { Suspense, useState } from "react";
import { useAuth } from "@/auth/AuthContext";
import LoginSignupForm from "@/auth/LoginSignupForm";
import Chat from "@/components/chat";
import VoiceCapture from "@/components/voice-capture";

export default function Home() {
  const { user } = useAuth();         
  const [showVoice, setShowVoice] = useState(false);


  if (!user) {
    return <LoginSignupForm />;
  }


  return (
    <div className="bg-gray-50 min-h-screen flex items-center justify-center p-4">
      <div className="w-[440px] shadow-lg border rounded-md bg-white m-4">
        <Suspense fallback={<div>Loading chat interface...</div>}>
          {showVoice ? (
            <VoiceCapture onClose={() => setShowVoice(false)} />
          ) : (
            <Chat onMicClick={() => setShowVoice(true)} />
          )}
        </Suspense>
      </div>
    </div>
  );
}
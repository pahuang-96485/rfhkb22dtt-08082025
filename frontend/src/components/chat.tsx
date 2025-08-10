// src/components/chat.tsx
"use client";

import { useEnsureRegeneratorRuntime } from "@/app/hook/useEnsureRegeneratorRuntime";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/card";
import { ScrollArea } from "@/components/scroll-area";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import Bubble from "./chat/message";
import SendForm from "./chat/chat-form";
import LZString from "lz-string";
import { useAuth } from "@/auth/AuthContext";

interface ChatProps {
  onMicClick: () => void; // callback to open voice capture
}

export default function Chat({ onMicClick }: ChatProps) {
  const { user, logout } = useAuth();
  if (!user) {
    return <div>Loading user information…</div>;
  }

  const token = user.token;

  const searchParams = useSearchParams();
  const share = searchParams.get("share");


  const [sessionId, setSessionId] = useState<string>(() => {
    const saved = localStorage.getItem("session_id");
    if (saved) return saved;
    const newId = crypto.randomUUID();
    localStorage.setItem("session_id", newId);
    return newId;
  });


  const [messages, setMessages] = useState<{ id: string; role: string; content: string }[]>(
    share
      ? JSON.parse(LZString.decompressFromEncodedURIComponent(share) || "[]")
      : [
          {
            id: "initialai",
            role: "assistant",
            content: `Hello ${user?.fname || "there"}, I'm your medical assistant. How can I help you today?`,
          },
        ]
  );

  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement | null>(null);

  useEnsureRegeneratorRuntime();


  useEffect(() => {
    if (scrollAreaRef.current) {
      scrollAreaRef.current.scrollTo({
        top: scrollAreaRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [messages]);


  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!input.trim()) return;

    const userMessage = {
      id: Date.now().toString(),
      role: "user",
      content: input,
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const res = await fetch(process.env.NEXT_PUBLIC_SCHEDULE_TOOL_CHAT!, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          message: input,
          context: {
            session_id: sessionId,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            input_mode: "text",
          }
        }),
      });

      const data: {
        reply: string;
      } = await res.json();

 
      const botMessage = {
        id: Date.now().toString(),
        role: "assistant",
        content: data.reply,   
      };
      setMessages((prev) => [...prev, botMessage]);
    } catch (err) {
      console.error("Chat API error:", err);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: "assistant",
          content: "Error: Unable to reach assistant.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }


  const handleLogout = () => {
    localStorage.removeItem("session_id");
    setSessionId("");
    logout();
  };

  return (
    <Card className="w-full max-w-md md:max-w-lg lg:max-w-xl h-[550px] sm:h-[750px]">
      <CardHeader className="py-2 sm:py-3">
        <div className="flex flex-row items-start justify-between">
          {/* The title and the logout button are on the same line */}
          <div>
            <CardTitle className="text-lg">CDSS Bot</CardTitle>
            <CardDescription className="leading-3">Scheduling Helper</CardDescription>
          </div>
          <button
            onClick={handleLogout}
            className="
              text-blue-600 bg-blue-50 border border-blue-100
              rounded-md px-3 py-1 text-sm hover:bg-blue-100
              transition whitespace-nowrap
            "
          >
            Logout
          </button>
        </div>
      </CardHeader>

      <CardContent className="flex-grow overflow-hidden p-0">
        <ScrollArea
          ref={scrollAreaRef}
          className="h-[400px] sm:h-[600px] overflow-y-auto w-full space-y-4 px-4"
        >
          {messages.map((msg) => (
            <Bubble key={msg.id} message={msg} />
          ))}
          {isLoading && <div className="text-gray-500 italic">Bot is typing...</div>}
        </ScrollArea>
      </CardContent>

      <CardFooter className="mt-auto border-t p-4">
        <SendForm
          input={input}
          handleSubmit={handleSubmit}
          isLoading={isLoading}
          handleInputChange={(e) => setInput(e.target.value)}
          onMicClick={onMicClick}
        />
      </CardFooter>
    </Card>
  );
}